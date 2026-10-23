"""
RentASeat Lambda handler — Step 3: Health + Authentication (Register/Login/Me).

Routes handled:

  GET /health         — basic liveness check
  GET /db-health      — proves Lambda → RDS connectivity
  POST /auth/register — register new passenger/driver with password hashing & JWT
  POST /auth/login    — authenticate user & issue JWT
  GET /auth/me        — verify session & return current user profile

Credential resolution order (see _get_db_credentials):

  1. DB_PASSWORD environment variable
     Temporary development fallback.
     Used while Lambda is inside a VPC without a Secrets Manager
     VPC endpoint or NAT Gateway.

  2. AWS Secrets Manager via DB_SECRET_ARN
     Production path.
     Requires a Secrets Manager VPC Interface Endpoint or NAT Gateway.

Security properties enforced in this file:

  - Passwords, secret values, and connection strings are NEVER logged or
    returned in API responses under any code path.
  - Constant-time password verification via hashlib.scrypt and hmac.compare_digest.
  - Public registration rejects privilege escalation (e.g. self-assigning 'admin').
  - Generic authentication errors to prevent account enumeration.
  - All SQL uses DB-API parameterised execution (%s) — no string concatenation.
  - Errors are caught and sanitised before being returned to callers.
  - Payload size limits enforced on incoming request bodies (<= 64 KB).
  - Structured JSON logging includes request IDs for CloudWatch tracing.

NOT implemented here (reserved for Step 4):

  booking APIs
  journey APIs
"""


import base64
import datetime
import json
import logging
import os
import re
import sys
import time
from pathlib import Path

try:
    import boto3
    from botocore.exceptions import BotoCoreError, ClientError
except ImportError:
    boto3 = None
    BotoCoreError = Exception  # type: ignore
    ClientError = Exception    # type: ignore

# Ensure local modules (auth.py) and local dependencies (backend/package) resolve
_cur_dir = str(Path(__file__).resolve().parent)
_pkg_dir = str(Path(__file__).resolve().parent / "package")
for _p in (_cur_dir, _pkg_dir):
    if _p not in sys.path:
        sys.path.insert(0, _p)

try:
    import pg8000.dbapi as pg8000_dbapi
except ImportError:
    pg8000_dbapi = None

from auth import (
    DUMMY_PASSWORD_HASH,
    create_jwt_token,
    hash_password,
    validate_email,
    validate_name,
    validate_password_input,
    validate_phone,
    validate_registration_role,
    verify_jwt_token,
    verify_password,
)
from vehicles import (
    format_vehicle_row,
    validate_vehicle_payload,
)
from journeys import (
    DATE_REGEX,
    format_journey_row,
    validate_departure_date,
    validate_endpoints,
    validate_journey_payload,
)
from bookings import (
    ALLOWED_BOOKING_STATUSES,
    ALLOWED_PAYMENT_STATUSES,
    JOINED_BOOKING_SELECT,
    format_booking_row,
    generate_booking_reference,
    validate_booking_status,
    validate_create_booking_payload,
    validate_location_note,
    validate_payment_status,
    validate_seats_booked,
    validate_status_transition,
)


# ─── Logging ────────────────────────────────────────────────────────────────

# Structured JSON so CloudWatch Logs Insights can filter/query
# individual fields.
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def _log(level: str, message: str, **extra) -> None:
    """
    Emit a single-line JSON log entry.

    SECURITY:
    Never pass passwords, tokens, secret values, or connection strings
    as keyword arguments to this function.
    """

    entry = {
        "level": level,
        "message": message,
        **extra,
    }

    line = json.dumps(entry, default=str)

    if level == "ERROR":
        logger.error(line)
    elif level == "WARNING":
        logger.warning(line)
    else:
        logger.info(line)


# ─── Environment variables ─────────────────────────────────────────────────

# All sourced from Lambda environment configuration.
# Nothing sensitive is hardcoded in this file.

DB_HOST = os.environ.get("DB_HOST", "")
DB_PORT = int(os.environ.get("DB_PORT", "5432"))
DB_NAME = os.environ.get("DB_NAME", "postgres")
DB_SECRET_ARN = os.environ.get("DB_SECRET_ARN", "")

# AWS region is provided by the Lambda runtime.
AWS_REGION = os.environ.get("AWS_REGION", "ap-south-1")


# ─── Secrets Manager client ────────────────────────────────────────────────

# Created at module level so it can be reused across warm invocations.
# Uses the Lambda execution role credentials automatically.
# No AWS access keys are stored in the code.

_secrets_client = (
    boto3.client(
        "secretsmanager",
        region_name=AWS_REGION,
    )
    if boto3 is not None
    else None
)


# Module-level credential cache.
#
# Populated on first successful credential resolution and reused during
# subsequent warm Lambda invocations.
#
# The cache stores only username + password and never the raw JSON secret.

_db_credentials: dict | None = None


# ─── Credential resolution ─────────────────────────────────────────────────


def _credentials_from_secrets_manager() -> dict:
    """
    Retrieve database credentials from AWS Secrets Manager.

    Requires one of:

      - A Secrets Manager VPC Interface Endpoint in the Lambda VPC, OR
      - A NAT Gateway with internet access.

    Returns:
        dict containing 'username' and 'password'.

    Raises:
        RuntimeError with a safe message on failure.
    """

    _log(
        "INFO",
        "Retrieving credentials from Secrets Manager",
        # Log only the tail of the ARN for traceability.
        # Never log the complete ARN.
        arn_tail=(
            DB_SECRET_ARN[-12:]
            if len(DB_SECRET_ARN) >= 12
            else "short-arn"
        ),
    )

    if _secrets_client is None:
        raise RuntimeError("Secrets Manager client is not initialized.")

    try:
        response = _secrets_client.get_secret_value(
            SecretId=DB_SECRET_ARN
        )

    except ClientError as exc:
        error_code = exc.response["Error"]["Code"]

        # Log only the AWS error code.
        # Do not log the complete exception because it may contain
        # sensitive configuration information.
        _log(
            "ERROR",
            "Secrets Manager ClientError",
            error_code=error_code,
        )

        raise RuntimeError(
            f"Secrets Manager error: {error_code}"
        ) from None

    except BotoCoreError as exc:

        # A VPC-attached Lambda may reach this path when it cannot
        # reach the Secrets Manager endpoint.
        #
        # A VPC Interface Endpoint for:
        #
        # com.amazonaws.ap-south-1.secretsmanager
        #
        # or NAT Gateway connectivity would resolve this.

        _log(
            "ERROR",
            "Secrets Manager network error — "
            "VPC endpoint may be required",
            error_type=type(exc).__name__,
        )

        raise RuntimeError(
            "Secrets Manager unreachable from this VPC."
        ) from None

    raw_secret = response.get("SecretString", "")

    if not raw_secret:
        raise RuntimeError(
            "Secrets Manager returned an empty secret value."
        )

    try:
        secret_dict = json.loads(raw_secret)

    except json.JSONDecodeError:
        raise RuntimeError(
            "Secrets Manager secret is not valid JSON."
        ) from None

    finally:
        # Remove the name binding immediately after parsing.
        #
        # This is not a cryptographic memory wipe.
        del raw_secret

    username = (
        secret_dict.get("username")
        or secret_dict.get("user")
    )

    password = secret_dict.get("password")

    if not username or not password:
        raise RuntimeError(
            "Secrets Manager secret is missing "
            "'username' or 'password' fields."
        )

    result = {
        "username": username,
        "password": password,
    }

    # Remove reference to the complete secret dictionary.
    del secret_dict

    _log(
        "INFO",
        "Credentials retrieved from Secrets Manager",
    )

    return result


def _credentials_from_env() -> dict:
    """
    Temporary development fallback.

    Read database credentials from Lambda environment variables.

    SECURITY TRADEOFF:

      - DB_PASSWORD is configured directly in Lambda environment
        variables.

      - It is NOT stored in source code.

      - It is NOT stored in .env files.

      - It is NOT stored in deployment scripts.

      - It is visible to identities with permission to retrieve
        Lambda environment configuration.

      - Lambda encrypts environment variables at rest.

      - This approach does NOT provide automatic credential rotation.

      - This is acceptable ONLY for temporary development on a private
        student project with no real user data.

      - Replace this with Secrets Manager before production use.

    Raises:
        RuntimeError if DB_PASSWORD is missing.
    """

    # DB_PASSWORD is intentionally read here rather than at module level.
    # This prevents accidental exposure during module initialisation.

    db_password = os.environ.get(
        "DB_PASSWORD",
        "",
    )

    db_username = os.environ.get(
        "DB_USERNAME",
        "rentaseat_admin",
    )

    if not db_password:
        raise RuntimeError(
            "DB_PASSWORD environment variable is not set. "
            "Set it in the Lambda console under "
            "Configuration → Environment variables. "
            "Do NOT add it to source code or deployment scripts."
        )

    _log(
        "INFO",
        "Using DB_PASSWORD environment variable "
        "(temporary dev fallback)",
    )

    return {
        "username": db_username,
        "password": db_password,
    }


def _get_db_credentials() -> dict:
    """
    Resolve database credentials.

    Current development priority:

      1. DB_PASSWORD environment variable
         Temporary development path.

      2. AWS Secrets Manager via DB_SECRET_ARN
         Production path when DB_PASSWORD is not configured.

    DB_PASSWORD currently takes priority because the Lambda is inside
    a private VPC without a Secrets Manager VPC endpoint or NAT Gateway.

    Returns:
        dict containing 'username' and 'password'.

    Raises:
        RuntimeError if neither credential source is available.

    Credentials are cached for warm Lambda invocations.
    """

    global _db_credentials

    # Reuse credentials already resolved during this warm invocation
    # environment.

    if _db_credentials is not None:
        return _db_credentials

    # ─── Temporary development path ────────────────────────────────
    #
    # DB_PASSWORD avoids requiring network access from the Lambda VPC
    # to Secrets Manager.

    if os.environ.get("DB_PASSWORD", ""):

        _db_credentials = _credentials_from_env()

        return _db_credentials

    # ─── Production path ────────────────────────────────────────────
    #
    # Used when DB_PASSWORD is not configured.

    if DB_SECRET_ARN:

        _db_credentials = _credentials_from_secrets_manager()

        return _db_credentials

    # No DB_PASSWORD and no usable Secrets Manager configuration.

    _db_credentials = _credentials_from_env()

    return _db_credentials


# ─── Database connectivity ─────────────────────────────────────────────────


def _get_db_connection():
    """
    Open a new pg8000 DB-API connection to the private RDS PostgreSQL
    instance.

    SSL is enabled for this connection using ssl_context=True.

    RDS PostgreSQL supports SSL. Server-side SSL enforcement is separate
    and can be enabled with the rds.force_ssl parameter.

    The connection is not pooled.

    At this development scale, Lambda invocations are short-lived and
    connection pooling would add unnecessary complexity.

    The caller is responsible for closing the connection in a finally block.
    """

    creds = _get_db_credentials()

    if not DB_HOST:
        raise RuntimeError(
            "DB_HOST environment variable is not set."
        )

    _log(
        "INFO",
        "Opening database connection",
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME,
    )

    if pg8000_dbapi is None:
        raise RuntimeError("Database driver (pg8000) is not available.")

    try:
        conn = pg8000_dbapi.connect(
            user=creds["username"],
            password=creds["password"],  # Never logged.
            host=DB_HOST,
            port=DB_PORT,
            database=DB_NAME,

            # Require SSL for the PostgreSQL connection.
            ssl_context=True,

            # Fail quickly rather than allowing a connection attempt
            # to consume the entire Lambda timeout.
            timeout=5,

            # Helps identify application connections in PostgreSQL.
            application_name="RentASeat-Lambda",
        )

        return conn

    except pg8000_dbapi.InterfaceError:

        _log(
            "ERROR",
            "PostgreSQL connection failed (InterfaceError)",
            host=DB_HOST,
            port=DB_PORT,
            database=DB_NAME,
        )

        raise RuntimeError(
            "Database connection failed."
        ) from None

    except pg8000_dbapi.OperationalError:

        _log(
            "ERROR",
            "PostgreSQL connection failed (OperationalError)",
            host=DB_HOST,
            port=DB_PORT,
            database=DB_NAME,
        )

        raise RuntimeError(
            "Database connection failed."
        ) from None

    except Exception as exc:

        _log(
            "ERROR",
            "Unexpected error opening database connection",
            error_type=type(exc).__name__,
        )

        raise RuntimeError(
            "Unexpected error connecting to the database."
        ) from None


# ─── Response helpers ──────────────────────────────────────────────────────


def _response(status_code: int, body: dict) -> dict:
    """
    Build a Lambda proxy integration response with safe default headers.
    """

    return {
        "statusCode": status_code,

        "headers": {
            "Content-Type": "application/json",

            # Prevent MIME-type sniffing.
            "X-Content-Type-Options": "nosniff",

            # Prevent caching of API responses.
            "Cache-Control": "no-store",
        },

        "body": json.dumps(body),
    }


def _error_response(
    status_code: int,
    message: str,
) -> dict:
    """
    Return a sanitised error response.

    Only pre-vetted safe message strings should be passed here.

    Never return raw exception messages, stack traces, database errors,
    passwords, tokens, or other sensitive information.
    """

    return _response(
        status_code,
        {
            "error": message,
        },
    )


# ─── Health handler ─────────────────────────────────────────────────────────


def _handle_health() -> dict:
    """
    GET /health

    Basic application liveness check.

    Does not access the database.
    """

    return _response(
        200,
        {
            "status": "ok",
            "service": "RentASeat-API",
            "message": "RentASeat backend is running",
        },
    )


# ─── Database health handler ────────────────────────────────────────────────


def _handle_db_health() -> dict:
    """
    GET /db-health

    Temporary endpoint used to prove:

        Lambda
          ↓
        VPC
          ↓
        Security Group
          ↓
        RDS PostgreSQL
          ↓
        SQL query execution

    Executes a simple SELECT 1 query.

    The query contains no external input, so SQL injection is not possible
    through this endpoint.

    The result value itself is not used as the success criterion.

    Successful execution and fetch are sufficient to prove database
    connectivity.
    """

    _log(
        "INFO",
        "DB health check requested",
    )

    start = time.monotonic()

    conn = None
    cursor = None

    try:

        # Open connection to private RDS PostgreSQL.
        conn = _get_db_connection()

        # Create a cursor.
        cursor = conn.cursor()

        # Constant query.
        #
        # No user-controlled data is included.
        cursor.execute("SELECT 1")

        # Fetch the result to ensure the query completed successfully.
        cursor.fetchone()

        elapsed_ms = round(
            (time.monotonic() - start) * 1000
        )

        _log(
            "INFO",
            "Database connectivity confirmed",
            elapsed_ms=elapsed_ms,
        )

        return _response(
            200,
            {
                "status": "ok",
                "database": "connected",
                "latency_ms": elapsed_ms,
            },
        )

    except RuntimeError:

        elapsed_ms = round(
            (time.monotonic() - start) * 1000
        )

        _log(
            "ERROR",
            "DB health check failed",
            elapsed_ms=elapsed_ms,
        )

        return _error_response(
            503,
            "Database unavailable.",
        )

    except Exception as exc:

        elapsed_ms = round(
            (time.monotonic() - start) * 1000
        )

        _log(
            "ERROR",
            "Unhandled exception in db-health handler",
            error_type=type(exc).__name__,
            elapsed_ms=elapsed_ms,
        )

        return _error_response(
            500,
            "Internal server error.",
        )

    finally:

        # Always close the cursor.
        if cursor is not None:
            try:
                cursor.close()
            except Exception:
                pass

        # Always close the database connection.
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


# ─── Request Body Helper ────────────────────────────────────────────────────


def _parse_body(event: dict) -> dict:
    """
    Parse and validate incoming JSON request body.
    Enforces payload size limit of 64 KB (65,536 bytes).
    Handles base64-encoded bodies from API Gateway.
    """
    body_raw = event.get("body", "")

    if not body_raw:
        raise ValueError("Request body is empty.")

    # Protect against oversized payloads
    if len(body_raw) > 65536:
        raise ValueError("Request payload exceeds 64 KB limit.")

    if event.get("isBase64Encoded", False):
        try:
            body_bytes = base64.b64decode(body_raw)
            body_text = body_bytes.decode("utf-8")
        except Exception:
            raise ValueError("Malformed base64 request body.")
    else:
        body_text = body_raw

    try:
        data = json.loads(body_text)
    except json.JSONDecodeError:
        raise ValueError("Malformed JSON request body.")

    if not isinstance(data, dict):
        raise ValueError("JSON request body must be an object.")

    return data


# ─── Authentication Handlers ────────────────────────────────────────────────


def _handle_register(event: dict) -> dict:
    """
    POST /auth/register
    Register a new user (passenger or driver).
    Enforces server-side validation and scrypt password hashing.
    Generates and returns an initial JWT token.
    """
    try:
        body = _parse_body(event)
    except ValueError as exc:
        return _error_response(400, str(exc))

    try:
        name = validate_name(body.get("name"))
        email = validate_email(body.get("email"))
        password = validate_password_input(body.get("password"))
        role = validate_registration_role(body.get("role"))
        phone = validate_phone(body.get("phone"))
    except ValueError as exc:
        return _error_response(400, str(exc))

    conn = None
    cursor = None
    try:
        conn = _get_db_connection()
        cursor = conn.cursor()

        # Check for existing email (case-insensitive lookup)
        cursor.execute("SELECT id FROM users WHERE email = %s;", (email,))
        if cursor.fetchone():
            return _error_response(409, "An account with this email already exists.")

        # Hash password using scrypt
        pw_hash = hash_password(password)

        try:
            cursor.execute(
                """
                INSERT INTO users (name, email, password_hash, phone, role, status)
                VALUES (%s, %s, %s, %s, %s, 'active')
                RETURNING id, name, email, phone, role, status, avatar_url, rating, review_count, created_at;
                """,
                (name, email, pw_hash, phone, role),
            )
            row = cursor.fetchone()
            conn.commit()
        except Exception as insert_exc:
            conn.rollback()
            err_msg = str(insert_exc).lower()
            if "unique" in err_msg or "duplicate" in err_msg or "uq_users_email" in err_msg:
                return _error_response(409, "An account with this email already exists.")
            raise

        user_id = str(row[0])
        token = create_jwt_token(user_id=user_id, email=row[2], role=row[4])

        user_data = {
            "id": user_id,
            "name": row[1],
            "email": row[2],
            "phone": row[3] or "",
            "role": row[4],
            "status": row[5],
            "avatar": row[6] or "",
            "rating": float(row[7]) if row[7] is not None else 5.0,
            "reviews": int(row[8]) if row[8] is not None else 0,
            "createdAt": row[9].isoformat() if hasattr(row[9], "isoformat") else str(row[9]),
        }

        _log("INFO", "User registered successfully", user_id=user_id, role=row[4])

        return _response(
            201,
            {
                "success": True,
                "token": token,
                "user": user_data,
                "message": "Registration successful",
            },
        )
    except RuntimeError:
        return _error_response(503, "Database unavailable.")
    except Exception as exc:
        _log("ERROR", "Unhandled exception in register handler", error_type=type(exc).__name__)
        return _error_response(500, "Internal server error.")
    finally:
        if cursor is not None:
            try:
                cursor.close()
            except Exception:
                pass
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def _handle_login(event: dict) -> dict:
    """
    POST /auth/login
    Authenticate user credentials and return a signed JWT token.
    Uses constant-time password verification and generic error responses.
    """
    try:
        body = _parse_body(event)
    except ValueError as exc:
        return _error_response(400, str(exc))

    raw_email = body.get("email")
    password = body.get("password")

    if not raw_email or not password:
        return _error_response(400, "Email and password are required.")

    try:
        email = validate_email(raw_email)
    except ValueError:
        # Return generic error to prevent account enumeration
        return _error_response(401, "Invalid email or password.")

    conn = None
    cursor = None
    try:
        conn = _get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT id, name, email, password_hash, phone, role, status, avatar_url, rating, review_count, created_at
            FROM users
            WHERE email = %s;
            """,
            (email,),
        )
        row = cursor.fetchone()

        if not row:
            # Perform dummy scrypt computation to eliminate timing-based account enumeration
            verify_password(password, DUMMY_PASSWORD_HASH)
            return _error_response(401, "Invalid email or password.")

        user_id = str(row[0])
        name = row[1]
        stored_hash = row[3]
        phone = row[4]
        role = row[5]
        status = row[6]
        avatar_url = row[7]
        rating = row[8]
        review_count = row[9]
        created_at = row[10]

        if not verify_password(password, stored_hash):
            return _error_response(401, "Invalid email or password.")

        if status != "active":
            return _error_response(403, "Account is suspended or deactivated.")

        token = create_jwt_token(user_id=user_id, email=email, role=role)

        user_data = {
            "id": user_id,
            "name": name,
            "email": email,
            "phone": phone or "",
            "role": role,
            "status": status,
            "avatar": avatar_url or "",
            "rating": float(rating) if rating is not None else 5.0,
            "reviews": int(review_count) if review_count is not None else 0,
            "createdAt": created_at.isoformat() if hasattr(created_at, "isoformat") else str(created_at),
        }

        _log("INFO", "User logged in successfully", user_id=user_id, role=role)

        return _response(
            200,
            {
                "success": True,
                "token": token,
                "user": user_data,
                "message": "Login successful",
            },
        )
    except RuntimeError:
        return _error_response(503, "Database unavailable.")
    except Exception as exc:
        _log("ERROR", "Unhandled exception in login handler", error_type=type(exc).__name__)
        return _error_response(500, "Internal server error.")
    finally:
        if cursor is not None:
            try:
                cursor.close()
            except Exception:
                pass
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def _handle_get_me(event: dict) -> dict:
    """
    GET /auth/me
    Verify the JWT token and return the authenticated user's profile.
    """
    claims, auth_err = _extract_auth_claims(event)
    if auth_err:
        return auth_err

    user_id = claims.get("sub")
    conn = None
    cursor = None
    try:
        conn = _get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT id, name, email, phone, role, status, avatar_url, rating, review_count, created_at
            FROM users
            WHERE id = %s;
            """,
            (user_id,),
        )
        row = cursor.fetchone()

        if not row:
            return _error_response(404, "User not found.")

        if row[5] != "active":
            return _error_response(403, "Account is suspended or deactivated.")

        user_data = {
            "id": str(row[0]),
            "name": row[1],
            "email": row[2],
            "phone": row[3] or "",
            "role": row[4],
            "status": row[5],
            "avatar": row[6] or "",
            "rating": float(row[7]) if row[7] is not None else 5.0,
            "reviews": int(row[8]) if row[8] is not None else 0,
            "createdAt": row[9].isoformat() if hasattr(row[9], "isoformat") else str(row[9]),
        }

        return _response(200, {"success": True, "user": user_data})
    except RuntimeError:
        return _error_response(503, "Database unavailable.")
    except Exception as exc:
        _log("ERROR", "Unhandled exception in get_me handler", error_type=type(exc).__name__)
        return _error_response(500, "Internal server error.")
    finally:
        if cursor is not None:
            try:
                cursor.close()
            except Exception:
                pass
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


# ─── Authentication Helpers ─────────────────────────────────────────────────


def _extract_auth_claims(event: dict) -> tuple[dict | None, dict | None]:
    """
    Extract and cryptographically verify the Bearer JWT token from headers.
    Returns (claims, None) on success, or (None, error_response) on failure.
    Validates token signature and expiry without requiring a database connection.
    """
    headers = event.get("headers", {}) or {}
    auth_header = headers.get("authorization") or headers.get("Authorization") or ""

    if not auth_header.startswith("Bearer "):
        return None, _error_response(401, "Authorization Bearer token required.")

    token = auth_header[7:].strip()
    try:
        claims = verify_jwt_token(token)
    except ValueError as exc:
        return None, _error_response(401, f"Authentication failed: {exc}")

    if not claims.get("sub"):
        return None, _error_response(401, "Invalid token subject.")

    return claims, None


def _get_authenticated_user(event: dict, cursor) -> tuple[dict | None, dict | None]:
    """
    Authenticate the request via Bearer JWT and retrieve live user state from PostgreSQL.
    Returns (user_dict, None) on success, or (None, error_response) on failure.
    """
    claims, auth_err = _extract_auth_claims(event)
    if auth_err:
        return None, auth_err

    user_id = claims["sub"]
    cursor.execute(
        """
        SELECT id, name, email, phone, role, status
        FROM users
        WHERE id = %s;
        """,
        (user_id,),
    )
    row = cursor.fetchone()

    if not row:
        return None, _error_response(404, "User not found.")

    if row[5] != "active":
        return None, _error_response(403, "Account is suspended or deactivated.")

    user = {
        "id": str(row[0]),
        "name": row[1],
        "email": row[2],
        "phone": row[3] or "",
        "role": row[4],
        "status": row[5],
    }
    return user, None


# ─── Vehicle Regex & Handlers ───────────────────────────────────────────────

VEHICLE_PATH_REGEX = re.compile(r"^/vehicles/([a-zA-Z0-9_-]{1,64})$")


def _handle_create_vehicle(event: dict) -> dict:
    """
    POST /vehicles
    Register a new vehicle for the authenticated driver (or admin).
    """
    claims, auth_err = _extract_auth_claims(event)
    if auth_err:
        return auth_err

    try:
        body = _parse_body(event)
    except ValueError as exc:
        return _error_response(400, str(exc))

    conn = None
    cursor = None
    try:
        conn = _get_db_connection()
        cursor = conn.cursor()

        user, auth_err = _get_authenticated_user(event, cursor)
        if auth_err:
            return auth_err

        if user["role"] not in ("driver", "admin"):
            return _error_response(403, "Driver role required to register vehicles.")

        try:
            validated = validate_vehicle_payload(body, is_update=False)
        except ValueError as exc:
            return _error_response(400, str(exc))

        driver_id = user["id"]
        # Allow admin to assign vehicle to a specific driver if requested
        if user["role"] == "admin":
            specified_driver = body.get("driverId") or body.get("driver_id")
            if specified_driver:
                cursor.execute(
                    "SELECT id, role, status FROM users WHERE id = %s;",
                    (specified_driver,),
                )
                d_row = cursor.fetchone()
                if not d_row:
                    return _error_response(404, "Specified driver not found.")
                if d_row[1] != "driver":
                    return _error_response(400, "Specified user is not a driver.")
                driver_id = str(d_row[0])

        try:
            cursor.execute(
                """
                INSERT INTO vehicles (driver_id, registration_number, vehicle_type, model, colour, seating_capacity, image_url)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id, driver_id, registration_number, vehicle_type, model, colour, seating_capacity, image_url, created_at, updated_at;
                """,
                (
                    driver_id,
                    validated["registration_number"],
                    validated["vehicle_type"],
                    validated["model"],
                    validated["colour"],
                    validated["seating_capacity"],
                    validated["image_url"],
                ),
            )
            row = cursor.fetchone()
            conn.commit()
        except Exception as insert_exc:
            conn.rollback()
            err_msg = str(insert_exc).lower()
            if "unique" in err_msg or "duplicate" in err_msg or "uq_vehicles_registration" in err_msg:
                return _error_response(
                    409,
                    f"A vehicle with registration number '{validated['registration_number']}' already exists.",
                )
            raise

        vehicle_data = format_vehicle_row(row)
        _log("INFO", "Vehicle created successfully", vehicle_id=vehicle_data["id"], driver_id=driver_id)

        return _response(
            201,
            {
                "success": True,
                "vehicle": vehicle_data,
                "message": "Vehicle created successfully",
            },
        )
    except RuntimeError:
        return _error_response(503, "Database unavailable.")
    except Exception as exc:
        _log("ERROR", "Unhandled exception in create_vehicle handler", error_type=type(exc).__name__)
        return _error_response(500, "Internal server error.")
    finally:
        if cursor is not None:
            try:
                cursor.close()
            except Exception:
                pass
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def _handle_list_vehicles(event: dict) -> dict:
    """
    GET /vehicles
    List vehicles for the authenticated driver (or all/filtered for admin).
    """
    claims, auth_err = _extract_auth_claims(event)
    if auth_err:
        return auth_err

    conn = None
    cursor = None
    try:
        conn = _get_db_connection()
        cursor = conn.cursor()

        user, auth_err = _get_authenticated_user(event, cursor)
        if auth_err:
            return auth_err

        if user["role"] not in ("driver", "admin"):
            return _error_response(403, "Driver role required to view vehicles.")

        params = event.get("queryStringParameters") or {}
        target_driver = params.get("driverId") or params.get("driver_id")

        if user["role"] == "admin":
            if target_driver:
                cursor.execute(
                    """
                    SELECT id, driver_id, registration_number, vehicle_type, model, colour, seating_capacity, image_url, created_at, updated_at
                    FROM vehicles
                    WHERE driver_id = %s
                    ORDER BY created_at DESC;
                    """,
                    (target_driver,),
                )
            else:
                cursor.execute(
                    """
                    SELECT id, driver_id, registration_number, vehicle_type, model, colour, seating_capacity, image_url, created_at, updated_at
                    FROM vehicles
                    ORDER BY created_at DESC;
                    """
                )
        else:
            cursor.execute(
                """
                SELECT id, driver_id, registration_number, vehicle_type, model, colour, seating_capacity, image_url, created_at, updated_at
                FROM vehicles
                WHERE driver_id = %s
                ORDER BY created_at DESC;
                """,
                (user["id"],),
            )

        rows = cursor.fetchall()
        vehicles = [format_vehicle_row(r) for r in rows]

        return _response(
            200,
            {
                "success": True,
                "vehicles": vehicles,
            },
        )
    except RuntimeError:
        return _error_response(503, "Database unavailable.")
    except Exception as exc:
        _log("ERROR", "Unhandled exception in list_vehicles handler", error_type=type(exc).__name__)
        return _error_response(500, "Internal server error.")
    finally:
        if cursor is not None:
            try:
                cursor.close()
            except Exception:
                pass
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def _handle_get_vehicle(event: dict, vehicle_id: str) -> dict:
    """
    GET /vehicles/{id}
    Retrieve vehicle by ID, enforcing ownership or admin permission.
    """
    if not vehicle_id:
        return _error_response(400, "Vehicle ID is required.")

    claims, auth_err = _extract_auth_claims(event)
    if auth_err:
        return auth_err

    conn = None
    cursor = None
    try:
        conn = _get_db_connection()
        cursor = conn.cursor()

        user, auth_err = _get_authenticated_user(event, cursor)
        if auth_err:
            return auth_err

        cursor.execute(
            """
            SELECT id, driver_id, registration_number, vehicle_type, model, colour, seating_capacity, image_url, created_at, updated_at
            FROM vehicles
            WHERE id = %s;
            """,
            (vehicle_id,),
        )
        row = cursor.fetchone()

        if not row:
            return _error_response(404, "Vehicle not found.")

        # Enforce driver ownership or admin role
        if str(row[1]) != user["id"] and user["role"] != "admin":
            return _error_response(403, "You do not have permission to access this vehicle.")

        return _response(
            200,
            {
                "success": True,
                "vehicle": format_vehicle_row(row),
            },
        )
    except RuntimeError:
        return _error_response(503, "Database unavailable.")
    except Exception as exc:
        _log("ERROR", "Unhandled exception in get_vehicle handler", error_type=type(exc).__name__)
        return _error_response(500, "Internal server error.")
    finally:
        if cursor is not None:
            try:
                cursor.close()
            except Exception:
                pass
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def _handle_update_vehicle(event: dict, vehicle_id: str) -> dict:
    """
    PUT /vehicles/{id} or PATCH /vehicles/{id}
    Update vehicle fields, enforcing ownership or admin permission and journey capacity constraints.
    """
    if not vehicle_id:
        return _error_response(400, "Vehicle ID is required.")

    claims, auth_err = _extract_auth_claims(event)
    if auth_err:
        return auth_err

    try:
        body = _parse_body(event)
    except ValueError as exc:
        return _error_response(400, str(exc))

    conn = None
    cursor = None
    try:
        conn = _get_db_connection()
        cursor = conn.cursor()

        user, auth_err = _get_authenticated_user(event, cursor)
        if auth_err:
            return auth_err

        try:
            validated = validate_vehicle_payload(body, is_update=True)
        except ValueError as exc:
            return _error_response(400, str(exc))

        if not validated:
            return _error_response(400, "No valid fields provided to update.")

        cursor.execute(
            """
            SELECT id, driver_id, registration_number, vehicle_type, model, colour, seating_capacity, image_url
            FROM vehicles
            WHERE id = %s;
            """,
            (vehicle_id,),
        )
        existing = cursor.fetchone()

        if not existing:
            return _error_response(404, "Vehicle not found.")

        # Enforce driver ownership or admin role
        if str(existing[1]) != user["id"] and user["role"] != "admin":
            return _error_response(403, "You do not have permission to modify this vehicle.")

        # Check journey capacity constraint if seating_capacity is being reduced
        if "seating_capacity" in validated:
            new_capacity = validated["seating_capacity"]
            cursor.execute(
                """
                SELECT COALESCE(MAX(total_seats), 0)
                FROM journeys
                WHERE vehicle_id = %s AND status = 'active';
                """,
                (vehicle_id,),
            )
            max_row = cursor.fetchone()
            max_active_seats = max_row[0] if max_row else 0
            if new_capacity < max_active_seats:
                return _error_response(
                    409,
                    f"Cannot reduce seating capacity to {new_capacity}. An active journey requires {max_active_seats} seats.",
                )

        new_reg = validated.get("registration_number", existing[2])
        new_type = validated.get("vehicle_type", existing[3])
        new_model = validated.get("model", existing[4])
        new_colour = validated["colour"] if "colour" in validated else existing[5]
        new_capacity = validated.get("seating_capacity", existing[6])
        new_image = validated["image_url"] if "image_url" in validated else existing[7]

        try:
            cursor.execute(
                """
                UPDATE vehicles
                SET registration_number = %s,
                    vehicle_type = %s,
                    model = %s,
                    colour = %s,
                    seating_capacity = %s,
                    image_url = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                RETURNING id, driver_id, registration_number, vehicle_type, model, colour, seating_capacity, image_url, created_at, updated_at;
                """,
                (new_reg, new_type, new_model, new_colour, new_capacity, new_image, vehicle_id),
            )
            updated_row = cursor.fetchone()
            conn.commit()
        except Exception as update_exc:
            conn.rollback()
            err_msg = str(update_exc).lower()
            if "unique" in err_msg or "duplicate" in err_msg or "uq_vehicles_registration" in err_msg:
                return _error_response(
                    409,
                    f"A vehicle with registration number '{new_reg}' already exists.",
                )
            raise

        vehicle_data = format_vehicle_row(updated_row)
        _log("INFO", "Vehicle updated successfully", vehicle_id=vehicle_id)

        return _response(
            200,
            {
                "success": True,
                "vehicle": vehicle_data,
                "message": "Vehicle updated successfully",
            },
        )
    except RuntimeError:
        return _error_response(503, "Database unavailable.")
    except Exception as exc:
        _log("ERROR", "Unhandled exception in update_vehicle handler", error_type=type(exc).__name__)
        return _error_response(500, "Internal server error.")
    finally:
        if cursor is not None:
            try:
                cursor.close()
            except Exception:
                pass
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def _handle_delete_vehicle(event: dict, vehicle_id: str) -> dict:
    """
    DELETE /vehicles/{id}
    Delete a vehicle only if it has no associated journeys.
    Enforces ownership or admin permission.
    """
    if not vehicle_id:
        return _error_response(400, "Vehicle ID is required.")

    claims, auth_err = _extract_auth_claims(event)
    if auth_err:
        return auth_err

    conn = None
    cursor = None
    try:
        conn = _get_db_connection()
        cursor = conn.cursor()

        user, auth_err = _get_authenticated_user(event, cursor)
        if auth_err:
            return auth_err

        cursor.execute(
            """
            SELECT id, driver_id
            FROM vehicles
            WHERE id = %s;
            """,
            (vehicle_id,),
        )
        existing = cursor.fetchone()

        if not existing:
            return _error_response(404, "Vehicle not found.")

        # Enforce driver ownership or admin role
        if str(existing[1]) != user["id"] and user["role"] != "admin":
            return _error_response(403, "You do not have permission to delete this vehicle.")

        # Check for existing journeys associated with this vehicle
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM journeys
            WHERE vehicle_id = %s;
            """,
            (vehicle_id,),
        )
        count_row = cursor.fetchone()
        journey_count = count_row[0] if count_row else 0

        if journey_count > 0:
            return _error_response(
                409,
                f"Cannot delete vehicle because it is associated with {journey_count} existing journey(s).",
            )

        try:
            cursor.execute("DELETE FROM vehicles WHERE id = %s;", (vehicle_id,))
            conn.commit()
        except Exception as del_exc:
            conn.rollback()
            err_msg = str(del_exc).lower()
            if "foreign key" in err_msg or "restrict" in err_msg or "violates" in err_msg:
                return _error_response(
                    409,
                    "Cannot delete vehicle because related database records depend on it.",
                )
            raise

        _log("INFO", "Vehicle deleted successfully", vehicle_id=vehicle_id)

        return _response(
            200,
            {
                "success": True,
                "message": "Vehicle deleted successfully",
            },
        )
    except RuntimeError:
        return _error_response(503, "Database unavailable.")
    except Exception as exc:
        _log("ERROR", "Unhandled exception in delete_vehicle handler", error_type=type(exc).__name__)
        return _error_response(500, "Internal server error.")
    finally:
        if cursor is not None:
            try:
                cursor.close()
            except Exception:
                pass
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


# ─── Journey Regex & Handlers ───────────────────────────────────────────────

JOURNEY_PATH_REGEX = re.compile(r"^/journeys/([a-zA-Z0-9_-]{1,64})$")


def _handle_create_journey(event: dict) -> dict:
    """
    POST /journeys
    Publish a new journey for the authenticated driver.
    Enforces active-account status, driver/admin role, and vehicle ownership.
    """
    claims, auth_err = _extract_auth_claims(event)
    if auth_err:
        return auth_err

    try:
        body = _parse_body(event)
    except ValueError as exc:
        return _error_response(400, str(exc))

    try:
        validated = validate_journey_payload(body, is_update=False)
    except ValueError as exc:
        return _error_response(400, str(exc))

    conn = None
    cursor = None
    try:
        conn = _get_db_connection()
        cursor = conn.cursor()

        user, auth_err = _get_authenticated_user(event, cursor)
        if auth_err:
            return auth_err

        if user["role"] not in ("driver", "admin"):
            return _error_response(403, "Driver role required to publish journeys.")

        driver_id = user["id"]
        # Allow admin to assign journey to a specific driver if requested
        if user["role"] == "admin":
            specified_driver = body.get("driverId") or body.get("driver_id")
            if specified_driver:
                cursor.execute(
                    "SELECT id, role, status FROM users WHERE id = %s;",
                    (specified_driver,),
                )
                d_row = cursor.fetchone()
                if not d_row:
                    return _error_response(404, "Specified driver not found.")
                if d_row[1] != "driver":
                    return _error_response(400, "Specified user is not a driver.")
                driver_id = str(d_row[0])

        # Verify referenced vehicle exists and belongs to the driver
        cursor.execute(
            """
            SELECT id, driver_id, seating_capacity
            FROM vehicles
            WHERE id = %s;
            """,
            (validated["vehicle_id"],),
        )
        veh_row = cursor.fetchone()
        if not veh_row:
            return _error_response(404, "Referenced vehicle does not exist.")

        if str(veh_row[1]) != driver_id:
            return _error_response(403, "Vehicle does not belong to the journey driver.")

        veh_capacity = int(veh_row[2])
        if validated["total_seats"] > veh_capacity:
            return _error_response(
                400,
                f"Journey total seats ({validated['total_seats']}) cannot exceed vehicle seating capacity ({veh_capacity}).",
            )

        available_seats = validated["total_seats"]
        stops_json = json.dumps(validated["stops"])

        cursor.execute(
            """
            INSERT INTO journeys (
                driver_id, vehicle_id, origin, destination,
                departure_date, departure_time, arrival_time,
                total_seats, available_seats, price_per_seat,
                status, description, stops
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id;
            """,
            (
                driver_id,
                validated["vehicle_id"],
                validated["origin"],
                validated["destination"],
                validated["departure_date"],
                validated["departure_time"],
                validated["arrival_time"],
                validated["total_seats"],
                available_seats,
                validated["price_per_seat"],
                validated["status"],
                validated["description"],
                stops_json,
            ),
        )
        new_row = cursor.fetchone()
        journey_id = str(new_row[0])

        # Query full joined record with driver and vehicle
        cursor.execute(
            """
            SELECT
                j.id, j.driver_id, j.vehicle_id, j.origin, j.destination,
                j.departure_date, j.departure_time, j.arrival_time,
                j.total_seats, j.available_seats, j.price_per_seat,
                j.status, j.description, j.stops, j.created_at, j.updated_at,
                u.name, u.email, u.phone, u.role, u.avatar_url, u.rating, u.review_count,
                v.registration_number, v.vehicle_type, v.model, v.colour, v.seating_capacity, v.image_url
            FROM journeys j
            JOIN users u ON j.driver_id = u.id
            JOIN vehicles v ON j.vehicle_id = v.id
            WHERE j.id = %s;
            """,
            (journey_id,),
        )
        joined_row = cursor.fetchone()
        conn.commit()

        journey_data = format_journey_row(joined_row)
        _log("INFO", "Journey created successfully", journey_id=journey_id, driver_id=driver_id)

        return _response(
            201,
            {
                "success": True,
                "journey": journey_data,
                "message": "Journey created successfully",
            },
        )
    except RuntimeError:
        return _error_response(503, "Database unavailable.")
    except Exception as exc:
        _log("ERROR", "Unhandled exception in create_journey handler", error_type=type(exc).__name__)
        return _error_response(500, "Internal server error.")
    finally:
        if cursor is not None:
            try:
                cursor.close()
            except Exception:
                pass
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def _handle_list_journeys(event: dict) -> dict:
    """
    GET /journeys
    Search and list journeys with parameterised filtering.
    Publicly accessible (supports unauthenticated search) and supports driverId/status filtering.
    """
    params = event.get("queryStringParameters") or {}
    origin_param = params.get("origin") or params.get("from")
    dest_param = params.get("destination") or params.get("to")
    date_param = params.get("date") or params.get("departureDate") or params.get("departure_date")
    seats_param = params.get("seats") or params.get("availableSeats") or params.get("available_seats")
    driver_param = params.get("driverId") or params.get("driver_id")
    status_param = params.get("status")

    where_clauses = []
    sql_params = []

    # Status filter
    if status_param and status_param.lower() != "all":
        where_clauses.append("j.status = %s")
        sql_params.append(status_param.lower())
    elif not status_param:
        where_clauses.append("j.status = 'active'")

    # Origin filter (case-insensitive substring)
    if origin_param and origin_param.strip():
        where_clauses.append("LOWER(j.origin) LIKE LOWER(%s)")
        sql_params.append(f"%{origin_param.strip()}%")

    # Destination filter (case-insensitive substring)
    if dest_param and dest_param.strip():
        where_clauses.append("LOWER(j.destination) LIKE LOWER(%s)")
        sql_params.append(f"%{dest_param.strip()}%")

    # Departure Date filter
    if date_param and date_param.strip():
        date_str = date_param.strip()
        # Enforce basic date format validation
        if not DATE_REGEX.match(date_str):
            return _error_response(400, "Invalid date format. Expected YYYY-MM-DD.")
        where_clauses.append("j.departure_date = %s")
        sql_params.append(date_str)

    # Available seats filter
    if seats_param and seats_param.strip():
        try:
            req_seats = int(seats_param.strip())
            where_clauses.append("j.available_seats >= %s")
            sql_params.append(req_seats)
        except (ValueError, TypeError):
            return _error_response(400, "Seats parameter must be an integer.")

    # Driver filter
    if driver_param and driver_param.strip():
        where_clauses.append("j.driver_id = %s")
        sql_params.append(driver_param.strip())

    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    query = f"""
        SELECT
            j.id, j.driver_id, j.vehicle_id, j.origin, j.destination,
            j.departure_date, j.departure_time, j.arrival_time,
            j.total_seats, j.available_seats, j.price_per_seat,
            j.status, j.description, j.stops, j.created_at, j.updated_at,
            u.name, u.email, u.phone, u.role, u.avatar_url, u.rating, u.review_count,
            v.registration_number, v.vehicle_type, v.model, v.colour, v.seating_capacity, v.image_url
        FROM journeys j
        JOIN users u ON j.driver_id = u.id
        JOIN vehicles v ON j.vehicle_id = v.id
        {where_sql}
        ORDER BY j.departure_date ASC, j.departure_time ASC
        LIMIT 50;
    """

    conn = None
    cursor = None
    try:
        conn = _get_db_connection()
        cursor = conn.cursor()

        cursor.execute(query, tuple(sql_params))
        rows = cursor.fetchall()
        journeys = [format_journey_row(r) for r in rows]

        return _response(
            200,
            {
                "success": True,
                "journeys": journeys,
            },
        )
    except RuntimeError:
        return _error_response(503, "Database unavailable.")
    except Exception as exc:
        _log("ERROR", "Unhandled exception in list_journeys handler", error_type=type(exc).__name__)
        return _error_response(500, "Internal server error.")
    finally:
        if cursor is not None:
            try:
                cursor.close()
            except Exception:
                pass
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def _handle_get_journey(event: dict, journey_id: str) -> dict:
    """
    GET /journeys/{id}
    Retrieve full journey details including driver and vehicle profiles.
    Publicly accessible.
    """
    if not journey_id:
        return _error_response(400, "Journey ID is required.")

    conn = None
    cursor = None
    try:
        conn = _get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT
                j.id, j.driver_id, j.vehicle_id, j.origin, j.destination,
                j.departure_date, j.departure_time, j.arrival_time,
                j.total_seats, j.available_seats, j.price_per_seat,
                j.status, j.description, j.stops, j.created_at, j.updated_at,
                u.name, u.email, u.phone, u.role, u.avatar_url, u.rating, u.review_count,
                v.registration_number, v.vehicle_type, v.model, v.colour, v.seating_capacity, v.image_url
            FROM journeys j
            JOIN users u ON j.driver_id = u.id
            JOIN vehicles v ON j.vehicle_id = v.id
            WHERE j.id = %s;
            """,
            (journey_id,),
        )
        row = cursor.fetchone()

        if not row:
            return _error_response(404, "Journey not found.")

        return _response(
            200,
            {
                "success": True,
                "journey": format_journey_row(row),
            },
        )
    except RuntimeError:
        return _error_response(503, "Database unavailable.")
    except Exception as exc:
        _log("ERROR", "Unhandled exception in get_journey handler", error_type=type(exc).__name__)
        return _error_response(500, "Internal server error.")
    finally:
        if cursor is not None:
            try:
                cursor.close()
            except Exception:
                pass
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def _handle_update_journey(event: dict, journey_id: str) -> dict:
    """
    PUT /journeys/{id} or PATCH /journeys/{id}
    Update journey fields. Enforces ownership or admin permission,
    vehicle capacity constraints, and prevents changes that invalidate existing bookings.
    """
    if not journey_id:
        return _error_response(400, "Journey ID is required.")

    claims, auth_err = _extract_auth_claims(event)
    if auth_err:
        return auth_err

    try:
        body = _parse_body(event)
    except ValueError as exc:
        return _error_response(400, str(exc))

    try:
        validated = validate_journey_payload(body, is_update=True)
    except ValueError as exc:
        return _error_response(400, str(exc))

    if not validated:
        return _error_response(400, "No valid fields provided to update.")

    conn = None
    cursor = None
    try:
        conn = _get_db_connection()
        cursor = conn.cursor()

        user, auth_err = _get_authenticated_user(event, cursor)
        if auth_err:
            return auth_err

        # Fetch existing journey
        cursor.execute(
            """
            SELECT id, driver_id, vehicle_id, origin, destination,
                   departure_date, departure_time, arrival_time,
                   total_seats, available_seats, price_per_seat,
                   status, description, stops
            FROM journeys
            WHERE id = %s;
            """,
            (journey_id,),
        )
        existing = cursor.fetchone()

        if not existing:
            return _error_response(404, "Journey not found.")

        # Enforce owning driver or admin permission
        if str(existing[1]) != user["id"] and user["role"] != "admin":
            return _error_response(403, "You do not have permission to modify this journey.")

        # Check existing active/confirmed bookings
        cursor.execute(
            """
            SELECT COALESCE(SUM(seats_booked), 0)
            FROM bookings
            WHERE journey_id = %s AND status NOT IN ('cancelled');
            """,
            (journey_id,),
        )
        b_row = cursor.fetchone()
        booked_seats = int(b_row[0]) if b_row else 0

        # Validate total_seats change against booked seats
        new_total_seats = validated.get("total_seats", existing[8])
        if new_total_seats < booked_seats:
            return _error_response(
                409,
                f"Cannot reduce total seats to {new_total_seats}. {booked_seats} seat(s) are already booked on this journey.",
            )

        # Vehicle validation (if vehicle is changed or seats changed)
        new_vehicle_id = validated.get("vehicle_id", str(existing[2]))
        cursor.execute(
            """
            SELECT id, driver_id, seating_capacity
            FROM vehicles
            WHERE id = %s;
            """,
            (new_vehicle_id,),
        )
        v_row = cursor.fetchone()
        if not v_row:
            return _error_response(404, "Referenced vehicle does not exist.")

        journey_driver_id = str(existing[1])
        if str(v_row[1]) != journey_driver_id:
            return _error_response(403, "Vehicle does not belong to the journey driver.")

        if new_total_seats > int(v_row[2]):
            return _error_response(
                400,
                f"Journey total seats ({new_total_seats}) cannot exceed vehicle seating capacity ({v_row[2]}).",
            )

        new_available_seats = new_total_seats - booked_seats

        new_origin = validated.get("origin", existing[3])
        new_dest = validated.get("destination", existing[4])
        validate_endpoints(new_origin, new_dest)

        new_dep_date = validated.get("departure_date", str(existing[5]))
        new_dep_time = validated.get("departure_time", str(existing[6]))
        new_arr_time = validated["arrival_time"] if "arrival_time" in validated else existing[7]
        new_price = validated.get("price_per_seat", existing[10])
        new_status = validated.get("status", existing[11])
        new_desc = validated["description"] if "description" in validated else existing[12]

        if "stops" in validated:
            new_stops_json = json.dumps(validated["stops"])
        else:
            new_stops_json = existing[13] if isinstance(existing[13], str) else json.dumps(existing[13] or [])

        cursor.execute(
            """
            UPDATE journeys
            SET origin = %s,
                destination = %s,
                departure_date = %s,
                departure_time = %s,
                arrival_time = %s,
                total_seats = %s,
                available_seats = %s,
                price_per_seat = %s,
                status = %s,
                description = %s,
                stops = %s,
                vehicle_id = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s;
            """,
            (
                new_origin,
                new_dest,
                new_dep_date,
                new_dep_time,
                new_arr_time,
                new_total_seats,
                new_available_seats,
                new_price,
                new_status,
                new_desc,
                new_stops_json,
                new_vehicle_id,
                journey_id,
            ),
        )

        # Retrieve updated full joined record
        cursor.execute(
            """
            SELECT
                j.id, j.driver_id, j.vehicle_id, j.origin, j.destination,
                j.departure_date, j.departure_time, j.arrival_time,
                j.total_seats, j.available_seats, j.price_per_seat,
                j.status, j.description, j.stops, j.created_at, j.updated_at,
                u.name, u.email, u.phone, u.role, u.avatar_url, u.rating, u.review_count,
                v.registration_number, v.vehicle_type, v.model, v.colour, v.seating_capacity, v.image_url
            FROM journeys j
            JOIN users u ON j.driver_id = u.id
            JOIN vehicles v ON j.vehicle_id = v.id
            WHERE j.id = %s;
            """,
            (journey_id,),
        )
        updated_row = cursor.fetchone()
        conn.commit()

        journey_data = format_journey_row(updated_row)
        _log("INFO", "Journey updated successfully", journey_id=journey_id)

        return _response(
            200,
            {
                "success": True,
                "journey": journey_data,
                "message": "Journey updated successfully",
            },
        )
    except RuntimeError:
        return _error_response(503, "Database unavailable.")
    except Exception as exc:
        _log("ERROR", "Unhandled exception in update_journey handler", error_type=type(exc).__name__)
        return _error_response(500, "Internal server error.")
    finally:
        if cursor is not None:
            try:
                cursor.close()
            except Exception:
                pass
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def _handle_delete_journey(event: dict, journey_id: str) -> dict:
    """
    DELETE /journeys/{id}
    Delete a journey only if it has zero associated bookings.
    If bookings exist, returns 409 Conflict instructing caller to cancel instead.
    Enforces owning driver or admin permission.
    """
    if not journey_id:
        return _error_response(400, "Journey ID is required.")

    claims, auth_err = _extract_auth_claims(event)
    if auth_err:
        return auth_err

    conn = None
    cursor = None
    try:
        conn = _get_db_connection()
        cursor = conn.cursor()

        user, auth_err = _get_authenticated_user(event, cursor)
        if auth_err:
            return auth_err

        cursor.execute(
            """
            SELECT id, driver_id
            FROM journeys
            WHERE id = %s;
            """,
            (journey_id,),
        )
        existing = cursor.fetchone()

        if not existing:
            return _error_response(404, "Journey not found.")

        # Enforce owning driver or admin role
        if str(existing[1]) != user["id"] and user["role"] != "admin":
            return _error_response(403, "You do not have permission to delete this journey.")

        # Check for existing bookings
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM bookings
            WHERE journey_id = %s;
            """,
            (journey_id,),
        )
        count_row = cursor.fetchone()
        booking_count = count_row[0] if count_row else 0

        if booking_count > 0:
            return _error_response(
                409,
                f"Cannot delete journey because it is associated with {booking_count} existing booking(s). Please cancel the journey instead of deleting.",
            )

        try:
            cursor.execute("DELETE FROM journeys WHERE id = %s;", (journey_id,))
            conn.commit()
        except Exception as del_exc:
            conn.rollback()
            err_msg = str(del_exc).lower()
            if "foreign key" in err_msg or "restrict" in err_msg or "violates" in err_msg:
                return _error_response(
                    409,
                    "Cannot delete journey because related database records depend on it.",
                )
            raise

        _log("INFO", "Journey deleted successfully", journey_id=journey_id)

        return _response(
            200,
            {
                "success": True,
                "message": "Journey deleted successfully",
            },
        )
    except RuntimeError:
        return _error_response(503, "Database unavailable.")
    except Exception as exc:
        _log("ERROR", "Unhandled exception in delete_journey handler", error_type=type(exc).__name__)
        return _error_response(500, "Internal server error.")
    finally:
        if cursor is not None:
            try:
                cursor.close()
            except Exception:
                pass
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


# ─── Booking Routes Handlers ────────────────────────────────────────────────

BOOKING_PATH_REGEX = re.compile(r"^/bookings/([a-zA-Z0-9_-]{1,64})$")
BOOKING_CANCEL_PATH_REGEX = re.compile(r"^/bookings/([a-zA-Z0-9_-]{1,64})/cancel$")


def _handle_create_booking(event: dict) -> dict:
    """
    POST /bookings
    Book seats on an active journey for the authenticated passenger.
    Enforces concurrency locking (SELECT ... FOR UPDATE), prevents overbooking,
    rejects self-booking by the driver, calculates total price server-side,
    and derives passenger identity strictly from the JWT.
    """
    claims, auth_err = _extract_auth_claims(event)
    if auth_err:
        return auth_err

    try:
        body = _parse_body(event)
    except ValueError as exc:
        return _error_response(400, str(exc))

    try:
        validated = validate_create_booking_payload(body)
    except ValueError as exc:
        return _error_response(400, str(exc))

    conn = None
    cursor = None
    try:
        conn = _get_db_connection()
        cursor = conn.cursor()

        user, auth_err = _get_authenticated_user(event, cursor)
        if auth_err:
            return auth_err

        # Derive passenger identity
        passenger_id = user["id"]
        # Allow admin to book on behalf of a specific passenger if requested
        if user["role"] == "admin":
            specified_passenger = body.get("passengerId") or body.get("passenger_id")
            if specified_passenger:
                cursor.execute(
                    "SELECT id, role, status FROM users WHERE id = %s;",
                    (specified_passenger,),
                )
                p_row = cursor.fetchone()
                if not p_row:
                    return _error_response(404, "Specified passenger not found.")
                if p_row[2] != "active":
                    return _error_response(400, "Specified passenger account is not active.")
                passenger_id = str(p_row[0])

        journey_id = validated["journey_id"]
        seats_requested = validated["seats_booked"]

        # Lock the journey row in this transaction to prevent concurrent race conditions
        cursor.execute(
            """
            SELECT
                id, driver_id, vehicle_id, origin, destination,
                departure_date, departure_time, arrival_time,
                total_seats, available_seats, price_per_seat,
                status
            FROM journeys
            WHERE id = %s
            FOR UPDATE;
            """,
            (journey_id,),
        )
        j_row = cursor.fetchone()
        if not j_row:
            return _error_response(404, "Journey not found.")

        j_driver_id = str(j_row[1])
        j_dep_date = j_row[5]
        j_avail_seats = int(j_row[9])
        j_price_per_seat = float(j_row[10])
        j_status = str(j_row[11])

        # 1. Journey must be active
        if j_status != "active":
            return _error_response(400, f"Cannot book seats on a journey with status '{j_status}'.")

        # 2. Driver cannot book their own journey
        if j_driver_id == passenger_id:
            return _error_response(403, "Driver cannot book seats on their own journey.")

        # 3. Journey departure must not have passed
        today = datetime.date.today()
        dep_date_obj = j_dep_date
        if isinstance(j_dep_date, str):
            try:
                dep_date_obj = datetime.date.fromisoformat(j_dep_date)
            except ValueError:
                pass
        if isinstance(dep_date_obj, datetime.date) and dep_date_obj < today:
            return _error_response(400, "Cannot book a journey whose departure date has already passed.")

        # 4. Check seat availability
        if j_avail_seats < seats_requested:
            return _error_response(
                409,
                f"Not enough seats available. Requested {seats_requested}, but only {j_avail_seats} remaining.",
            )

        # 5. Check duplicate active booking for this passenger on this journey
        cursor.execute(
            """
            SELECT id FROM bookings
            WHERE journey_id = %s AND passenger_id = %s AND status != 'cancelled';
            """,
            (journey_id, passenger_id),
        )
        if cursor.fetchone():
            return _error_response(409, "You already have an active booking for this journey.")

        # Calculate total price server-side
        total_price = round(seats_requested * j_price_per_seat, 2)

        # Generate unique booking reference
        booking_ref = generate_booking_reference()

        # Atomically deduct available seats
        cursor.execute(
            """
            UPDATE journeys
            SET available_seats = available_seats - %s
            WHERE id = %s;
            """,
            (seats_requested, journey_id),
        )

        # Insert new booking
        cursor.execute(
            """
            INSERT INTO bookings (
                booking_reference, journey_id, passenger_id, seats_booked,
                total_price, status, payment_status, pickup_location, dropoff_location
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id;
            """,
            (
                booking_ref,
                journey_id,
                passenger_id,
                seats_requested,
                total_price,
                "confirmed",
                "unpaid",
                validated["pickup_location"],
                validated["dropoff_location"],
            ),
        )
        new_row = cursor.fetchone()
        booking_id = str(new_row[0])

        # Fetch joined booking record
        cursor.execute(
            f"{JOINED_BOOKING_SELECT} WHERE b.id = %s;",
            (booking_id,),
        )
        joined_row = cursor.fetchone()
        conn.commit()

        booking_data = format_booking_row(joined_row)
        _log(
            "INFO",
            "Booking created successfully",
            booking_id=booking_id,
            booking_reference=booking_ref,
            journey_id=journey_id,
            passenger_id=passenger_id,
            seats_booked=seats_requested,
            total_price=total_price,
        )

        return _response(
            201,
            {
                "success": True,
                "booking": booking_data,
                "message": "Booking confirmed successfully. Payment processing is not yet implemented (status: unpaid).",
            },
        )
    except RuntimeError:
        return _error_response(503, "Database unavailable.")
    except Exception as exc:
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                pass
        _log("ERROR", "Unhandled exception in create_booking handler", error_type=type(exc).__name__)
        return _error_response(500, "Internal server error.")
    finally:
        if cursor is not None:
            try:
                cursor.close()
            except Exception:
                pass
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def _handle_list_bookings(event: dict) -> dict:
    """
    GET /bookings
    List bookings for the authenticated user.
    - Passenger: returns their own booking history.
    - Driver: returns bookings for their journeys (or where they are passenger).
    - Admin: can view all bookings or filter by passenger, journey, or status.
    """
    claims, auth_err = _extract_auth_claims(event)
    if auth_err:
        return auth_err

    conn = None
    cursor = None
    try:
        conn = _get_db_connection()
        cursor = conn.cursor()

        user, auth_err = _get_authenticated_user(event, cursor)
        if auth_err:
            return auth_err

        params = event.get("queryStringParameters") or {}
        filter_passenger = params.get("passengerId") or params.get("passenger_id")
        filter_journey = params.get("journeyId") or params.get("journey_id")
        filter_status = params.get("status")
        as_role = params.get("as") or params.get("role")

        where_clauses = []
        sql_params = []

        user_id = user["id"]
        role = user["role"]

        if role == "admin":
            if filter_passenger:
                where_clauses.append("b.passenger_id = %s")
                sql_params.append(filter_passenger)
            if filter_journey:
                where_clauses.append("b.journey_id = %s")
                sql_params.append(filter_journey)
        elif role == "passenger":
            where_clauses.append("b.passenger_id = %s")
            sql_params.append(user_id)
            if filter_journey:
                where_clauses.append("b.journey_id = %s")
                sql_params.append(filter_journey)
        elif role == "driver":
            if as_role == "driver":
                where_clauses.append("j.driver_id = %s")
                sql_params.append(user_id)
            elif as_role == "passenger":
                where_clauses.append("b.passenger_id = %s")
                sql_params.append(user_id)
            elif filter_journey:
                where_clauses.append("b.journey_id = %s")
                sql_params.append(filter_journey)
                where_clauses.append("(j.driver_id = %s OR b.passenger_id = %s)")
                sql_params.extend([user_id, user_id])
            else:
                where_clauses.append("(j.driver_id = %s OR b.passenger_id = %s)")
                sql_params.extend([user_id, user_id])
        else:
            return _error_response(403, "Unauthorized role.")

        if filter_status:
            try:
                valid_status = validate_booking_status(filter_status)
                where_clauses.append("b.status = %s")
                sql_params.append(valid_status)
            except ValueError:
                return _error_response(400, f"Invalid status filter '{filter_status}'.")

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        query = f"""
        {JOINED_BOOKING_SELECT}
        {where_sql}
        ORDER BY b.created_at DESC;
        """

        cursor.execute(query, tuple(sql_params))
        rows = cursor.fetchall()
        bookings = [format_booking_row(r) for r in rows]

        return _response(
            200,
            {
                "success": True,
                "bookings": bookings,
                "count": len(bookings),
            },
        )
    except RuntimeError:
        return _error_response(503, "Database unavailable.")
    except Exception as exc:
        _log("ERROR", "Unhandled exception in list_bookings handler", error_type=type(exc).__name__)
        return _error_response(500, "Internal server error.")
    finally:
        if cursor is not None:
            try:
                cursor.close()
            except Exception:
                pass
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def _handle_get_booking(event: dict, booking_id: str) -> dict:
    """
    GET /bookings/{id}
    Retrieve booking details by ID or reference.
    Enforces ownership: accessible only by the passenger, journey driver, or admin.
    """
    claims, auth_err = _extract_auth_claims(event)
    if auth_err:
        return auth_err

    conn = None
    cursor = None
    try:
        conn = _get_db_connection()
        cursor = conn.cursor()

        user, auth_err = _get_authenticated_user(event, cursor)
        if auth_err:
            return auth_err

        cursor.execute(
            f"""
            {JOINED_BOOKING_SELECT}
            WHERE b.id = %s OR b.booking_reference = %s;
            """,
            (booking_id, booking_id),
        )
        row = cursor.fetchone()
        if not row:
            return _error_response(404, "Booking not found.")

        passenger_id = str(row[3])
        driver_id = str(row[30])
        user_id = user["id"]

        is_passenger = user_id == passenger_id
        is_driver = user_id == driver_id
        is_admin = user["role"] == "admin"

        if not (is_passenger or is_driver or is_admin):
            return _error_response(403, "Forbidden: You do not have permission to view this booking.")

        booking_data = format_booking_row(row)
        return _response(
            200,
            {
                "success": True,
                "booking": booking_data,
            },
        )
    except RuntimeError:
        return _error_response(503, "Database unavailable.")
    except Exception as exc:
        _log("ERROR", "Unhandled exception in get_booking handler", error_type=type(exc).__name__)
        return _error_response(500, "Internal server error.")
    finally:
        if cursor is not None:
            try:
                cursor.close()
            except Exception:
                pass
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def _handle_update_booking(event: dict, booking_id: str) -> dict:
    """
    PATCH /bookings/{id}
    Update booking details or perform explicit safe status transitions.
    If transitioned to 'cancelled', releases seats back to the journey exactly once.
    """
    claims, auth_err = _extract_auth_claims(event)
    if auth_err:
        return auth_err

    try:
        body = _parse_body(event)
    except ValueError as exc:
        return _error_response(400, str(exc))

    conn = None
    cursor = None
    try:
        conn = _get_db_connection()
        cursor = conn.cursor()

        user, auth_err = _get_authenticated_user(event, cursor)
        if auth_err:
            return auth_err

        # Lock booking and journey info
        cursor.execute(
            """
            SELECT b.id, b.journey_id, b.passenger_id, b.seats_booked, b.status, b.payment_status,
                   b.pickup_location, b.dropoff_location, j.driver_id
            FROM bookings b
            JOIN journeys j ON b.journey_id = j.id
            WHERE b.id = %s
            FOR UPDATE OF b;
            """,
            (booking_id,),
        )
        b_row = cursor.fetchone()
        if not b_row:
            return _error_response(404, "Booking not found.")

        b_id = str(b_row[0])
        journey_id = str(b_row[1])
        passenger_id = str(b_row[2])
        seats_booked = int(b_row[3])
        current_status = str(b_row[4])
        current_payment = str(b_row[5])
        current_pickup = b_row[6]
        current_dropoff = b_row[7]
        driver_id = str(b_row[8])

        user_id = user["id"]
        is_passenger = user_id == passenger_id
        is_driver = user_id == driver_id
        is_admin = user["role"] == "admin"

        if not (is_passenger or is_driver or is_admin):
            return _error_response(403, "Forbidden: You do not have permission to update this booking.")

        new_status = current_status
        if "status" in body:
            try:
                requested_status = validate_booking_status(body["status"])
                validate_status_transition(current_status, requested_status)
            except ValueError as exc:
                return _error_response(400, str(exc))

            if is_passenger and not is_admin:
                if requested_status != current_status and requested_status != "cancelled":
                    return _error_response(403, "Passengers may only cancel bookings.")

            new_status = requested_status

        new_payment = current_payment
        if "paymentStatus" in body or "payment_status" in body:
            if not (is_admin or is_driver):
                return _error_response(403, "Only driver or admin can update payment status.")
            try:
                new_payment = validate_payment_status(
                    body.get("paymentStatus") or body.get("payment_status")
                )
            except ValueError as exc:
                return _error_response(400, str(exc))

        new_pickup = current_pickup
        if "pickupLocation" in body or "pickup_location" in body:
            try:
                new_pickup = validate_location_note(
                    body.get("pickupLocation") or body.get("pickup_location"),
                    "Pickup location",
                )
            except ValueError as exc:
                return _error_response(400, str(exc))

        new_dropoff = current_dropoff
        if "dropoffLocation" in body or "dropoff_location" in body:
            try:
                new_dropoff = validate_location_note(
                    body.get("dropoffLocation") or body.get("dropoff_location"),
                    "Dropoff location",
                )
            except ValueError as exc:
                return _error_response(400, str(exc))

        # If transitioning to cancelled, release seats exactly once
        if current_status != "cancelled" and new_status == "cancelled":
            cursor.execute(
                """
                SELECT id, total_seats, available_seats
                FROM journeys
                WHERE id = %s
                FOR UPDATE;
                """,
                (journey_id,),
            )
            cursor.execute(
                """
                UPDATE journeys
                SET available_seats = LEAST(total_seats, available_seats + %s)
                WHERE id = %s;
                """,
                (seats_booked, journey_id),
            )

        cursor.execute(
            """
            UPDATE bookings
            SET status = %s,
                payment_status = %s,
                pickup_location = %s,
                dropoff_location = %s
            WHERE id = %s;
            """,
            (new_status, new_payment, new_pickup, new_dropoff, b_id),
        )

        cursor.execute(
            f"{JOINED_BOOKING_SELECT} WHERE b.id = %s;",
            (b_id,),
        )
        joined_row = cursor.fetchone()
        conn.commit()

        booking_data = format_booking_row(joined_row)
        _log("INFO", "Booking updated successfully", booking_id=b_id, new_status=new_status)

        return _response(
            200,
            {
                "success": True,
                "booking": booking_data,
                "message": "Booking updated successfully.",
            },
        )
    except RuntimeError:
        return _error_response(503, "Database unavailable.")
    except Exception as exc:
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                pass
        _log("ERROR", "Unhandled exception in update_booking handler", error_type=type(exc).__name__)
        return _error_response(500, "Internal server error.")
    finally:
        if cursor is not None:
            try:
                cursor.close()
            except Exception:
                pass
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def _handle_cancel_booking(event: dict, booking_id: str) -> dict:
    """
    POST /bookings/{id}/cancel
    Cancel a booking and release reserved seats back to the journey.
    Guarantees exactly-once seat restoration within a transaction.
    Accessible by the passenger, journey driver, or admin.
    """
    claims, auth_err = _extract_auth_claims(event)
    if auth_err:
        return auth_err

    conn = None
    cursor = None
    try:
        conn = _get_db_connection()
        cursor = conn.cursor()

        user, auth_err = _get_authenticated_user(event, cursor)
        if auth_err:
            return auth_err

        # Lock booking and journey info
        cursor.execute(
            """
            SELECT b.id, b.journey_id, b.passenger_id, b.seats_booked, b.status, j.driver_id
            FROM bookings b
            JOIN journeys j ON b.journey_id = j.id
            WHERE b.id = %s
            FOR UPDATE OF b;
            """,
            (booking_id,),
        )
        b_row = cursor.fetchone()
        if not b_row:
            return _error_response(404, "Booking not found.")

        b_id = str(b_row[0])
        journey_id = str(b_row[1])
        passenger_id = str(b_row[2])
        seats_booked = int(b_row[3])
        current_status = str(b_row[4])
        driver_id = str(b_row[5])

        user_id = user["id"]
        is_passenger = user_id == passenger_id
        is_driver = user_id == driver_id
        is_admin = user["role"] == "admin"

        if not (is_passenger or is_driver or is_admin):
            return _error_response(403, "Forbidden: You do not have permission to cancel this booking.")

        if current_status == "cancelled":
            return _error_response(409, "Booking is already cancelled.")

        if current_status == "completed":
            return _error_response(409, "Cannot cancel a completed booking.")

        # Lock journey row and restore available seats exactly once
        cursor.execute(
            """
            SELECT id, total_seats, available_seats
            FROM journeys
            WHERE id = %s
            FOR UPDATE;
            """,
            (journey_id,),
        )
        j_row = cursor.fetchone()
        if not j_row:
            return _error_response(404, "Referenced journey not found.")

        cursor.execute(
            """
            UPDATE journeys
            SET available_seats = LEAST(total_seats, available_seats + %s)
            WHERE id = %s;
            """,
            (seats_booked, journey_id),
        )

        cursor.execute(
            """
            UPDATE bookings
            SET status = 'cancelled'
            WHERE id = %s;
            """,
            (b_id,),
        )

        cursor.execute(
            f"{JOINED_BOOKING_SELECT} WHERE b.id = %s;",
            (b_id,),
        )
        joined_row = cursor.fetchone()
        conn.commit()

        booking_data = format_booking_row(joined_row)
        _log(
            "INFO",
            "Booking cancelled successfully",
            booking_id=b_id,
            journey_id=journey_id,
            seats_restored=seats_booked,
        )

        return _response(
            200,
            {
                "success": True,
                "booking": booking_data,
                "message": f"Booking cancelled successfully. {seats_booked} seat(s) released.",
            },
        )
    except RuntimeError:
        return _error_response(503, "Database unavailable.")
    except Exception as exc:
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                pass
        _log("ERROR", "Unhandled exception in cancel_booking handler", error_type=type(exc).__name__)
        return _error_response(500, "Internal server error.")
    finally:
        if cursor is not None:
            try:
                cursor.close()
            except Exception:
                pass
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


# ─── Main Lambda handler ────────────────────────────────────────────────────



def lambda_handler(
    event: dict,
    context,
) -> dict:
    """
    AWS Lambda entry point.

    Receives API Gateway HTTP API payload format 2.0 events.

    Routes on HTTP method + raw path.
    """

    http_ctx = (
        event
        .get("requestContext", {})
        .get("http", {})
    )

    method = http_ctx.get(
        "method",
        "UNKNOWN",
    )

    path = event.get(
        "rawPath",
        "/",
    )

    request_id = (
        event
        .get("requestContext", {})
        .get("requestId", "unknown")
    )

    _log(
        "INFO",
        "Request received",
        method=method,
        path=path,
        request_id=request_id,
    )

    # ─── Route dispatch ─────────────────────────────────────────────
    # Normalize path (handle optional /api prefix from local dev proxy)
    clean_path = path[4:] if path.startswith("/api/") else path

    if method == "GET" and (clean_path == "/health" or path == "/health"):
        return _handle_health()

    if method == "GET" and (clean_path == "/db-health" or path == "/db-health"):
        return _handle_db_health()

    if method == "POST" and (clean_path == "/auth/register" or path == "/auth/register"):
        return _handle_register(event)

    if method == "POST" and (clean_path == "/auth/login" or path == "/auth/login"):
        return _handle_login(event)

    if method == "GET" and (clean_path == "/auth/me" or path == "/auth/me"):
        return _handle_get_me(event)

    # ─── Vehicle Routes ─────────────────────────────────────────────
    if clean_path == "/vehicles" or path == "/vehicles":
        if method == "POST":
            return _handle_create_vehicle(event)
        if method == "GET":
            return _handle_list_vehicles(event)

    vehicle_match = VEHICLE_PATH_REGEX.match(clean_path) or VEHICLE_PATH_REGEX.match(path)
    v_id = None
    if vehicle_match:
        v_id = vehicle_match.group(1)
    elif event.get("pathParameters") and "id" in event["pathParameters"]:
        if clean_path.startswith("/vehicles"):
            v_id = event["pathParameters"]["id"]

    if v_id:
        if method == "GET":
            return _handle_get_vehicle(event, v_id)
        if method in ("PUT", "PATCH"):
            return _handle_update_vehicle(event, v_id)
        if method == "DELETE":
            return _handle_delete_vehicle(event, v_id)

    # ─── Journey Routes ─────────────────────────────────────────────
    if clean_path == "/journeys" or path == "/journeys":
        if method == "POST":
            return _handle_create_journey(event)
        if method == "GET":
            return _handle_list_journeys(event)

    journey_match = JOURNEY_PATH_REGEX.match(clean_path) or JOURNEY_PATH_REGEX.match(path)
    j_id = None
    if journey_match:
        j_id = journey_match.group(1)
    elif event.get("pathParameters") and "id" in event["pathParameters"]:
        if clean_path.startswith("/journeys"):
            j_id = event["pathParameters"]["id"]

    if j_id:
        if method == "GET":
            return _handle_get_journey(event, j_id)
        if method in ("PUT", "PATCH"):
            return _handle_update_journey(event, j_id)
        if method == "DELETE":
            return _handle_delete_journey(event, j_id)

    # ─── Booking Routes ─────────────────────────────────────────────
    # Cancel endpoint: POST /bookings/{id}/cancel
    cancel_match = BOOKING_CANCEL_PATH_REGEX.match(clean_path) or BOOKING_CANCEL_PATH_REGEX.match(path)
    b_cancel_id = None
    if cancel_match:
        b_cancel_id = cancel_match.group(1)
    elif event.get("pathParameters") and "id" in event["pathParameters"] and clean_path.endswith("/cancel"):
        b_cancel_id = event["pathParameters"]["id"]

    if b_cancel_id:
        if method in ("POST", "PATCH"):
            return _handle_cancel_booking(event, b_cancel_id)

    if clean_path == "/bookings" or path == "/bookings":
        if method == "POST":
            return _handle_create_booking(event)
        if method == "GET":
            return _handle_list_bookings(event)

    booking_match = BOOKING_PATH_REGEX.match(clean_path) or BOOKING_PATH_REGEX.match(path)
    b_id = None
    if booking_match:
        b_id = booking_match.group(1)
    elif event.get("pathParameters") and "id" in event["pathParameters"]:
        if clean_path.startswith("/bookings"):
            b_id = event["pathParameters"]["id"]

    if b_id:
        if method == "GET":
            return _handle_get_booking(event, b_id)
        if method in ("PUT", "PATCH"):
            return _handle_update_booking(event, b_id)
        if method == "DELETE":
            return _handle_cancel_booking(event, b_id)

    # ─── Unknown route ──────────────────────────────────────────────

    _log(
        "WARNING",
        "Route not found",
        method=method,
        path=path,
    )

    return _error_response(
        404,
        "Not found.",
    )