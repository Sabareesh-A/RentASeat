#!/usr/bin/env bash
# build.sh — Package the RentASeat Lambda function for deployment.
#
# Produces: backend/rentaseat-lambda.zip
#
# IMPORTANT:
#   All four dependencies (pg8000, scramp, python-dateutil, asn1crypto) are
#   pure-Python — no native extensions. The zip produced on macOS is identical
#   to one produced on Linux and is safe to deploy directly to Lambda x86_64.
#
# boto3/botocore are intentionally excluded — the Lambda runtime provides them.
#
# Usage:
#   cd /path/to/rideAseat/backend
#   chmod +x build.sh
#   ./build.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="${SCRIPT_DIR}/package"
ZIP_FILE="${SCRIPT_DIR}/rentaseat-lambda.zip"

# ── Resolve Python interpreter ───────────────────────────────────────────────
# Prefer python3.13 to match the Lambda runtime exactly.
# Fall back to python3 if python3.13 is not available.
# Never use bare `pip` which may map to a different Python version or Python 2.
if command -v python3.13 &>/dev/null; then
  PYTHON="python3.13"
elif command -v python3 &>/dev/null; then
  PYTHON="python3"
  PY_VERSION="$($PYTHON --version 2>&1)"
  echo "==> WARNING: python3.13 not found, using: ${PY_VERSION}"
  echo "    The zip will still work because all dependencies are pure Python."
else
  echo "==> ERROR: No Python 3 interpreter found. Install Python 3.13."
  exit 1
fi

echo "==> Using interpreter: $($PYTHON --version)"

# ── Clean previous build ─────────────────────────────────────────────────────
echo "==> Cleaning previous build..."
rm -rf "${BUILD_DIR}" "${ZIP_FILE}"
mkdir -p "${BUILD_DIR}"

# ── Install dependencies ─────────────────────────────────────────────────────
echo "==> Installing dependencies into package/..."
"${PYTHON}" -m pip install \
  --quiet \
  --requirement "${SCRIPT_DIR}/requirements.txt" \
  --target "${BUILD_DIR}" \
  --no-compile

# Strip __pycache__ directories — Lambda recompiles .py files on first import,
# so cached bytecode from the build machine is unnecessary weight in the zip.
#
# NOTE: .dist-info directories are intentionally KEPT.
# pg8000 uses importlib.metadata at runtime to locate its scramp dependency.
# Stripping .dist-info causes:
#   "No package metadata was found for scramp"
# and a Runtime.ImportModuleError on Lambda cold start.
echo "==> Stripping __pycache__..."
find "${BUILD_DIR}" -type d -name "__pycache__" | xargs rm -rf 2>/dev/null || true

# ── Copy Lambda handler ──────────────────────────────────────────────────────
echo "==> Copying Lambda handler..."
cp "${SCRIPT_DIR}/lambda_function.py" "${BUILD_DIR}/lambda_function.py"

# ── Create deployment zip ────────────────────────────────────────────────────
echo "==> Creating deployment zip..."
cd "${BUILD_DIR}"
zip -r -q "${ZIP_FILE}" .
cd "${SCRIPT_DIR}"

ZIP_SIZE="$(du -sh "${ZIP_FILE}" | cut -f1)"
echo ""
echo "==> Build complete."
echo "    Zip : ${ZIP_FILE}"
echo "    Size: ${ZIP_SIZE}"
echo ""

# ── Verify required packages and metadata are present ────────────────────────
# Uses Python's zipfile module for reliable cross-platform path matching.
# 'unzip -l | grep' is avoided: macOS BSD unzip output format causes
# grep patterns to produce false negatives on directory entries.
# The zip path is passed to Python via _VERIFY_ZIP env var (heredocs
# do not receive shell variables as arguments directly).
echo "==> Verifying package contents..."
_VERIFY_ZIP="${ZIP_FILE}" "${PYTHON}" - <<'PYEOF'
import os
import sys
import zipfile

zip_path = os.environ["_VERIFY_ZIP"]

with zipfile.ZipFile(zip_path) as z:
    names = z.namelist()

all_ok = True

# ── Check top-level package directories ─────────────────────────────────────
packages = {
    "pg8000":     "pg8000/",
    "scramp":     "scramp/",
    "dateutil":   "dateutil/",
    "asn1crypto": "asn1crypto/",
}
for label, prefix in packages.items():
    found = any(n == prefix or n.startswith(prefix) for n in names)
    if found:
        print(f"    [OK] {label}/ found")
    else:
        print(f"    [MISSING] {label}/ NOT found in zip — rebuild required")
        all_ok = False

# ── Check .dist-info directories ─────────────────────────────────────────────
# importlib.metadata resolves package metadata by reading these directories.
# If any are absent, Lambda raises:
#   Runtime.ImportModuleError: No package metadata was found for <pkg>
dist_prefixes = {
    "pg8000":          "pg8000-",
    "scramp":          "scramp-",
    "python_dateutil": "python_dateutil-",
    "asn1crypto":      "asn1crypto-",
}
for label, prefix in dist_prefixes.items():
    match = next(
        (n.split("/")[0] for n in names
         if n.startswith(prefix) and ".dist-info/" in n),
        None,
    )
    if match:
        print(f"    [OK] {match}/ found")
    else:
        print(f"    [MISSING] {label} .dist-info NOT found — Lambda will fail with ImportModuleError")
        all_ok = False

print()
if all_ok:
    print("==> All checks passed. Zip is ready for deployment.")
    sys.exit(0)
else:
    print("==> ERROR: Zip is missing required packages or metadata. Do not deploy.")
    sys.exit(1)
PYEOF

echo "==> Before deploying, review DEPLOYMENT_NOTES.md."
echo "    Confirm DB_PASSWORD is set in the Lambda console before invoking /db-health."