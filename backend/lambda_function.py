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