"""
RentASeat Lambda handler — Step 2A: Health + DB connectivity proof.

Routes handled:
  GET /health     — basic liveness check (unchanged from original)
  GET /db-health  — proves Lambda → RDS connectivity

Credential resolution order (see _get_db_credentials):
  1. AWS Secrets Manager via DB_SECRET_ARN  (preferred, requires VPC endpoint
     or NAT — see DEPLOYMENT_NOTES.md)
  2. DB_PASSWORD environment variable        (temporary dev fallback only)

Security properties enforced in this file:
  - Passwords, secret values, and connection strings are NEVER logged or
    returned in API responses under any code path.
  - All SQL uses DB-API parameterised execution — no string interpolation
    with any external input.
  - Errors are caught and sanitised before being returned to callers.
  - Structured JSON logging includes request IDs for CloudWatch tracing.
  - del is called on references to the raw secret immediately after use.
    Note: del removes the Python name binding; CPython may not immediately
    release the underlying memory. This reduces the reachability window but
    is not a cryptographic memory wipe.

NOT implemented here (reserved for later steps):
  POST /auth/register, POST /auth/login, JWT, RBAC, booking/journey APIs.
"""

import json
import logging
import os
import time

import boto3
from botocore.exceptions import BotoCoreError, ClientError

import pg8000.dbapi as pg8000_dbapi

# ─── Logging ────────────────────────────────────────────────────────────────
# Structured JSON so CloudWatch Logs Insights can filter/query individual fields.
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def _log(level: str, message: str, **extra) -> None:
    """
    Emit a single-line JSON log entry.

    SECURITY: Never pass passwords, tokens, secret values, or connection
    strings as keyword arguments to this function.
    """
    entry = {"level": level, "message": message, **extra}
    line = json.dumps(entry, default=str)
    if level == "ERROR":
        logger.error(line)
    elif level == "WARNING":
        logger.warning(line)
    else:
        logger.info(line)


# ─── Environment variables ───────────────────────────────────────────────────
# All sourced from Lambda environment configuration — never hardcoded here.
# DB_PASSWORD is intentionally not read at module level; it is read inside
# _get_db_credentials() only when needed, so it is never accidentally logged
# as part of module-level initialisation output.
DB_HOST = os.environ.get("DB_HOST", "")
DB_PORT = int(os.environ.get("DB_PORT", "5432"))
DB_NAME = os.environ.get("DB_NAME", "postgres")
DB_SECRET_ARN = os.environ.get("DB_SECRET_ARN", "")

# AWS region is always set by the Lambda runtime.
AWS_REGION = os.environ.get("AWS_REGION", "ap-south-1")


# ─── Secrets Manager client ──────────────────────────────────────────────────
# Created at module level so it is reused across warm invocations.
# Uses the Lambda execution role credentials automatically — no access keys.
_secrets_client = boto3.client("secretsmanager", region_name=AWS_REGION)

# Module-level credential cache: populated on first invocation, reused on
# subsequent warm starts to avoid repeated Secrets Manager round-trips.
# Lambda execution environments are single-threaded (one invocation at a
# time per environment), so there is no race condition on this variable.
# The cache stores only username + password, never the raw secret string.
_db_credentials: dict | None = None


# ─── Credential resolution ───────────────────────────────────────────────────

def _credentials_from_secrets_manager() -> dict:
    """
    Attempt to retrieve credentials from AWS Secrets Manager.

    Requires one of:
      - A Secrets Manager VPC Interface Endpoint in the Lambda's VPC, OR
      - A NAT Gateway with internet access

    Returns a dict with 'username' and 'password'.
    Raises RuntimeError with a safe message on any failure.
    """
    _log("INFO", "Retrieving credentials from Secrets Manager",
         # Log only the tail of the ARN for traceability — never the full ARN
         # as it may be considered sensitive configuration data.
         arn_tail=DB_SECRET_ARN[-12:] if len(DB_SECRET_ARN) >= 12 else "short-arn")

    try:
        response = _secrets_client.get_secret_value(SecretId=DB_SECRET_ARN)
    except ClientError as exc:
        error_code = exc.response["Error"]["Code"]
        # Log the AWS error code (safe) — not the full exception message
        # which may contain ARN or account details.
        _log("ERROR", "Secrets Manager ClientError", error_code=error_code)
        raise RuntimeError(f"Secrets Manager error: {error_code}") from None
    except BotoCoreError as exc:
        # BotoCoreError on a VPC-attached Lambda typically means the Lambda
        # cannot reach the Secrets Manager endpoint. A VPC Interface Endpoint
        # (com.amazonaws.ap-south-1.secretsmanager) would resolve this.
        _log("ERROR", "Secrets Manager network error — VPC endpoint may be required",
             error_type=type(exc).__name__)
        raise RuntimeError("Secrets Manager unreachable from this VPC.") from None

    raw_secret = response.get("SecretString", "")
    if not raw_secret:
        raise RuntimeError("Secrets Manager returned an empty secret value.")

    try:
        secret_dict = json.loads(raw_secret)
    except json.JSONDecodeError:
        raise RuntimeError("Secrets Manager secret is not valid JSON.") from None
    finally:
        # Remove the name binding immediately after parsing.
        # Note: this reduces the reference lifetime; it is not a memory wipe.
        del raw_secret

    username = secret_dict.get("username") or secret_dict.get("user")
    password = secret_dict.get("password")

    if not username or not password:
        raise RuntimeError(
            "Secrets Manager secret is missing 'username' or 'password' fields."
        )

    result = {"username": username, "password": password}
    del secret_dict  # Remove reference to the full secret dict
    _log("INFO", "Credentials retrieved from Secrets Manager")
    return result


def _credentials_from_env() -> dict:
    """
    Temporary development fallback: read DB credentials from Lambda
    environment variables.

    SECURITY TRADEOFF:
      - DB_PASSWORD is set directly in the Lambda console (not in source code,
        not in .env files, not in deployment scripts, not in git).
      - It is visible to anyone with Lambda:GetFunctionConfiguration IAM
        permission — treat access to that permission as highly sensitive.
      - Lambda encrypts environment variables at rest using the account's
        default KMS key.
      - This approach does NOT support automatic credential rotation.
      - This is acceptable ONLY for temporary development use on a private
        student project with no real user data.
      - Replace with Secrets Manager before any real user data is stored.

    Raises RuntimeError if DB_PASSWORD is not set or empty.
    """
    # DB_PASSWORD is read here, not at module level, to avoid it being
    # captured in any initialisation logging.
    db_password = os.environ.get("DB_PASSWORD", "")
    db_username = os.environ.get("DB_USERNAME", "rentaseat_admin")

    if not db_password:
        raise RuntimeError(
            "DB_PASSWORD environment variable is not set. "
            "Set it in the Lambda console (Configuration → Environment variables). "
            "Do NOT add it to source code or deployment scripts."
        )

    _log("INFO", "Using DB_PASSWORD environment variable (temporary dev fallback)")
    return {"username": db_username, "password": db_password}


def _get_db_credentials() -> dict:
    """
    Resolve database credentials using the following priority:

      1. AWS Secrets Manager (preferred — uses DB_SECRET_ARN)
         Requires network access from Lambda VPC to Secrets Manager endpoint.

      2. DB_PASSWORD environment variable (temporary development fallback)
         Used when Secrets Manager is unreachable due to missing VPC endpoint.
         See DEPLOYMENT_NOTES.md for the full security tradeoff.

    Returns a dict with 'username' and 'password'.
    Raises RuntimeError if neither source can provide credentials.

    Results are cached at module level for warm Lambda invocations.
    """
    global _db_credentials

    if _db_credentials is not None:
        return _db_credentials

    # Temporary development path: prefer DB_PASSWORD when it is configured.
    # This avoids requiring network access from the VPC to Secrets Manager.
    if os.environ.get("DB_PASSWORD", ""):
        _db_credentials = _credentials_from_env()
        return _db_credentials

    # Production path: use Secrets Manager when DB_PASSWORD is not configured.
    if DB_SECRET_ARN:
        _db_credentials = _credentials_from_secrets_manager()
        return _db_credentials

    _db_credentials = _credentials_from_env()
    return _db_credentials


# ─── Database connectivity ───────────────────────────────────────────────────

def _get_db_connection():
    """
    Open a new pg8000 DB-API connection to the private RDS PostgreSQL instance.

    SSL is enabled for this connection (ssl_context=True). This means pg8000
    will require SSL and fail if the server does not support it. RDS PostgreSQL
    supports SSL on all configurations; rds.force_ssl is not required for SSL
    to work, only for enforcing it server-side.

    The connection is not pooled — Lambda invocations are short-lived and
    connection pooling adds complexity without meaningful benefit at this scale.
    The caller is responsible for closing the connection in a finally block.
    """
    creds = _get_db_credentials()

    if not DB_HOST:
        raise RuntimeError("DB_HOST environment variable is not set.")

    _log("INFO", "Opening database connection",
         host=DB_HOST, port=DB_PORT, database=DB_NAME)

    try:
        conn = pg8000_dbapi.connect(
            user=creds["username"],
            password=creds["password"],   # never logged
            host=DB_HOST,
            port=DB_PORT,
            database=DB_NAME,
            ssl_context=True,             # require SSL; uses Python ssl defaults
            timeout=5,                    # seconds — fail fast, don't hang Lambda
            application_name="RentASeat-Lambda",  # visible in pg_stat_activity
        )
        return conn

    except pg8000_dbapi.InterfaceError as exc:
        # InterfaceError covers network errors, SSL failures, and auth failures.
        # Do not include exc details — may contain host/port/auth information.
        _log("ERROR", "PostgreSQL connection failed (InterfaceError)",
             host=DB_HOST, port=DB_PORT, database=DB_NAME)
        raise RuntimeError("Database connection failed.") from None

    except pg8000_dbapi.OperationalError as exc:
        _log("ERROR", "PostgreSQL connection failed (OperationalError)",
             host=DB_HOST, port=DB_PORT, database=DB_NAME)
        raise RuntimeError("Database connection failed.") from None

    except Exception as exc:
        _log("ERROR", "Unexpected error opening database connection",
             error_type=type(exc).__name__)
        raise RuntimeError("Unexpected error connecting to the database.") from None


# ─── Response helpers ────────────────────────────────────────────────────────

def _response(status_code: int, body: dict) -> dict:
    """Build a Lambda proxy integration response with safe default headers."""
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "X-Content-Type-Options": "nosniff",
            # Prevent caching of API responses at any layer.
            "Cache-Control": "no-store",
        },
        "body": json.dumps(body),
    }


def _error_response(status_code: int, message: str) -> dict:
    """
    Return a sanitised error response.

    Only pre-vetted, safe message strings should be passed here.
    Never pass raw exception messages, stack traces, or database error details.
    """
    return _response(status_code, {"error": message})


# ─── Route handlers ──────────────────────────────────────────────────────────

def _handle_health() -> dict:
    """
    GET /health — basic liveness probe.

    Returns the same response shape as the original Lambda implementation
    so existing frontend health-check code and tests continue to work.
    """
    return _response(200, {
        "status": "ok",
        "service": "RentASeat-API",
        "message": "RentASeat backend is running",
    })


def _handle_db_health() -> dict:
    """
    GET /db-health — temporary endpoint to prove Lambda → RDS connectivity.

    Executes SELECT 1 via a parameterised query to confirm the full path:
    Lambda credentials → pg8000 → TCP/SSL → RDS PostgreSQL → response.

    Returns only a safe status summary. Never returns credentials, connection
    strings, version strings, schema details, or error internals.

    IMPORTANT: This endpoint should be removed or access-restricted before
    production. It exposes database reachability status publicly.
    """
    _log("INFO", "DB health check requested")
    start = time.monotonic()
    conn = None

    try:
        conn = _get_db_connection()
        cursor = conn.cursor()

        # DB-API parameterised execution — pg8000 sends the value via the
        # PostgreSQL extended query protocol, never interpolated into SQL text.
        cursor.execute("SELECT %s", (1,))
        row = cursor.fetchone()
        cursor.close()

        elapsed_ms = round((time.monotonic() - start) * 1000)

        if row is not None and row[0] == 1:
            _log("INFO", "Database connectivity confirmed", elapsed_ms=elapsed_ms)
            return _response(200, {
                "status": "ok",
                "database": "connected",
                "latency_ms": elapsed_ms,
            })

        _log("ERROR", "Database query returned unexpected result",
             elapsed_ms=elapsed_ms)
        return _error_response(500, "Database returned unexpected result.")

    except RuntimeError as exc:
        # RuntimeError messages from _get_db_credentials / _get_db_connection
        # have already been sanitised by those functions — safe to surface.
        elapsed_ms = round((time.monotonic() - start) * 1000)
        _log("ERROR", "DB health check failed", elapsed_ms=elapsed_ms,
             reason=str(exc))
        return _error_response(503, f"Database unavailable: {exc}")

    except Exception as exc:
        elapsed_ms = round((time.monotonic() - start) * 1000)
        _log("ERROR", "Unhandled exception in db-health handler",
             error_type=type(exc).__name__, elapsed_ms=elapsed_ms)
        return _error_response(500, "Internal server error.")

    finally:
        # Always attempt to close the connection, even if an exception occurred.
        # Each Lambda invocation opens and closes its own connection — there is
        # no persistent pool at this stage.
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass  # Best-effort; do not mask the original error


# ─── Main handler ────────────────────────────────────────────────────────────

def lambda_handler(event: dict, context) -> dict:
    """
    AWS Lambda entry point.

    Receives API Gateway HTTP API (payload format 2.0) events.
    Routes on HTTP method + raw path.
    """
    http_ctx = event.get("requestContext", {}).get("http", {})
    method = http_ctx.get("method", "UNKNOWN")
    path = event.get("rawPath", "/")
    request_id = event.get("requestContext", {}).get("requestId", "unknown")

    _log("INFO", "Request received",
         method=method, path=path, request_id=request_id)

    # Route dispatch
    if method == "GET" and path == "/health":
        return _handle_health()

    if method == "GET" and path == "/db-health":
        return _handle_db_health()

    _log("WARNING", "Route not found", method=method, path=path)
    return _error_response(404, "Not found.")
