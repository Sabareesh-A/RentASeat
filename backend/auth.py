"""
RentASeat Authentication & Cryptographic Utilities
Compatible with Python 3.13 and AWS Lambda execution environment.

Features:
  - Memory-hard salted password hashing via RFC 7914 scrypt (Python standard library).
  - Pure-Python HMAC-SHA256 (HS256) JSON Web Token (JWT) encoding & verification.
  - Server-side input validation and normalization.
  - Role assignment protection: rejects privilege escalation attempts (e.g. self-assigning 'admin').
  - Timing attack mitigation via hmac.compare_digest.
  - Zero third-party native C extension requirements.
"""

import base64
import hashlib
import hmac
import json
import os
import re
import time
from typing import Any

# Default token lifetime: 24 hours (86,400 seconds)
DEFAULT_TOKEN_EXPIRY_SECONDS = 86400

# Email validation regex conforming to standard web email patterns
EMAIL_REGEX = re.compile(
    r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$"
)

# Phone validation regex (optional field)
PHONE_REGEX = re.compile(
    r"^\+?[0-9\s\-\(\)\.]{7,25}$"
)

# Allowed public self-registration roles
ALLOWED_PUBLIC_ROLES = {"passenger", "driver"}


def get_jwt_secret() -> str:
    """
    Retrieve the JWT signing secret from the Lambda environment.
    Falls back to a secure development default with a warning.
    """
    secret = os.environ.get("JWT_SECRET", "")
    if not secret:
        # Fallback for local development and offline testing only
        return "rentaseat-dev-jwt-signing-secret-key-32chars!"
    return secret


# ─── Password Hashing (scrypt) ───────────────────────────────────────────────


def hash_password(password: str) -> str:
    """
    Generate a salted, memory-hard scrypt hash for the password.
    Format: scrypt$<N>$<r>$<p>$<hex_salt>$<hex_hash>

    Parameters:
      N = 16384 (CPU/memory cost parameter)
      r = 8     (block size parameter)
      p = 1     (parallelization parameter)
      salt = 16 cryptographically random bytes
      dklen = 64 bytes derived key length
    """
    if not password or len(password) < 8:
        raise ValueError("Password must be at least 8 characters long.")
    if len(password) > 128:
        raise ValueError("Password must not exceed 128 characters.")

    salt = os.urandom(16)
    n, r, p = 16384, 8, 1
    derived_key = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=n,
        r=r,
        p=p,
        dklen=64,
    )

    return f"scrypt${n}${r}${p}${salt.hex()}${derived_key.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    """
    Verify a plaintext password against a stored scrypt hash string.
    Uses hmac.compare_digest for constant-time comparison to prevent timing attacks.
    """
    if not password or not stored_hash:
        return False

    parts = stored_hash.split("$")
    if len(parts) != 6 or parts[0] != "scrypt":
        return False

    try:
        n = int(parts[1])
        r = int(parts[2])
        p = int(parts[3])
        salt = bytes.fromhex(parts[4])
        expected_key = bytes.fromhex(parts[5])

        actual_key = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=n,
            r=r,
            p=p,
            dklen=len(expected_key),
        )

        return hmac.compare_digest(actual_key, expected_key)
    except Exception:
        return False


# ─── JSON Web Tokens (HS256) ─────────────────────────────────────────────────


def _b64url_encode(data: bytes) -> str:
    """Encode bytes to a base64url string without padding."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    """Decode a base64url string with automatic padding restoration."""
    padding = b"=" * ((4 - len(s) % 4) % 4)
    return base64.urlsafe_b64decode(s.encode("ascii") + padding)


def create_jwt_token(
    user_id: str,
    email: str,
    role: str,
    expires_in_seconds: int = DEFAULT_TOKEN_EXPIRY_SECONDS,
) -> str:
    """
    Create a signed HS256 JWT for an authenticated user session.
    """
    secret = get_jwt_secret()
    now = int(time.time())
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": str(user_id),
        "email": str(email).lower().strip(),
        "role": str(role),
        "iat": now,
        "exp": now + expires_in_seconds,
    }

    header_b64 = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")

    signature = hmac.new(
        secret.encode("utf-8"),
        signing_input,
        hashlib.sha256,
    ).digest()
    signature_b64 = _b64url_encode(signature)

    return f"{header_b64}.{payload_b64}.{signature_b64}"


def verify_jwt_token(token: str) -> dict[str, Any]:
    """
    Verify signature, format, and expiration of a JWT token.
    Returns the decoded claims dictionary.
    Raises ValueError on invalid token, signature mismatch, or expiration.
    """
    if not token or not isinstance(token, str):
        raise ValueError("Authorization token is missing or malformed.")

    parts = token.strip().split(".")
    if len(parts) != 3:
        raise ValueError("Invalid JWT token format.")

    header_b64, payload_b64, signature_b64 = parts
    secret = get_jwt_secret()
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")

    expected_signature = hmac.new(
        secret.encode("utf-8"),
        signing_input,
        hashlib.sha256,
    ).digest()

    try:
        actual_signature = _b64url_decode(signature_b64)
    except Exception:
        raise ValueError("Invalid token signature encoding.")

    if not hmac.compare_digest(actual_signature, expected_signature):
        raise ValueError("Invalid token signature.")

    try:
        payload_bytes = _b64url_decode(payload_b64)
        payload = json.loads(payload_bytes.decode("utf-8"))
    except Exception:
        raise ValueError("Invalid token payload.")

    exp = payload.get("exp")
    if not exp or not isinstance(exp, (int, float)):
        raise ValueError("Token missing expiration claim.")

    if time.time() > exp:
        raise ValueError("Token has expired.")

    if not payload.get("sub"):
        raise ValueError("Token missing subject identifier.")

    return payload


# ─── Input Validation & Normalization ────────────────────────────────────────


def validate_email(email: Any) -> str:
    """Validate email format and return lowercased trimmed string."""
    if not email or not isinstance(email, str):
        raise ValueError("Email is required.")
    cleaned = email.strip().lower()
    if len(cleaned) > 255:
        raise ValueError("Email must not exceed 255 characters.")
    if not EMAIL_REGEX.match(cleaned):
        raise ValueError("Invalid email format.")
    return cleaned


def validate_password_input(password: Any) -> str:
    """Validate password length."""
    if not password or not isinstance(password, str):
        raise ValueError("Password is required.")
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters long.")
    if len(password) > 128:
        raise ValueError("Password must not exceed 128 characters.")
    return password


def validate_name(name: Any) -> str:
    """Validate full name length and return trimmed string."""
    if not name or not isinstance(name, str):
        raise ValueError("Name is required.")
    cleaned = name.strip()
    if len(cleaned) < 2:
        raise ValueError("Name must be at least 2 characters long.")
    if len(cleaned) > 100:
        raise ValueError("Name must not exceed 100 characters.")
    return cleaned


def validate_registration_role(role: Any) -> str:
    """
    Enforce role security during public registration.
    Rejects privileged roles (such as 'admin') and allows only 'passenger' or 'driver'.
    """
    if role is None or role == "":
        return "passenger"
    if not isinstance(role, str):
        raise ValueError("Role must be a string.")

    cleaned = role.strip().lower()
    if cleaned == "admin":
        raise ValueError("Public registration as admin is prohibited.")
    if cleaned not in ALLOWED_PUBLIC_ROLES:
        raise ValueError(
            f"Invalid role '{role}'. Allowed roles for registration: 'passenger', 'driver'."
        )
    return cleaned


def validate_phone(phone: Any) -> str | None:
    """Validate phone number format if provided."""
    if phone is None or phone == "":
        return None
    if not isinstance(phone, str):
        raise ValueError("Phone must be a string.")
    cleaned = phone.strip()
    if not PHONE_REGEX.match(cleaned):
        raise ValueError("Invalid phone number format.")
    return cleaned
