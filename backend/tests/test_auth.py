#!/usr/bin/env python3
"""
Unit Test Suite for RentASeat Authentication & Cryptography
Covers password hashing, JWT creation & verification, role enforcement,
input validation, and Lambda request handling (offline with mocks).
"""

import json
import os
import time
import unittest
from unittest.mock import MagicMock, patch

from backend.auth import (
    DUMMY_PASSWORD_HASH,
    _b64url_encode,
    create_jwt_token,
    get_jwt_secret,
    hash_password,
    validate_email,
    validate_name,
    validate_password_input,
    validate_phone,
    validate_registration_role,
    verify_jwt_token,
    verify_password,
)
from backend.lambda_function import lambda_handler


class TestPasswordHashing(unittest.TestCase):
    def test_hash_and_verify_success(self):
        password = "SecurePassword123!"
        hashed = hash_password(password)

        self.assertTrue(hashed.startswith("scrypt$16384$8$1$"))
        self.assertTrue(verify_password(password, hashed))
        self.assertFalse(verify_password("WrongPassword123!", hashed))
        self.assertFalse(verify_password("", hashed))

    def test_hash_password_length_constraints(self):
        with self.assertRaises(ValueError):
            hash_password("short")  # < 8 chars

        with self.assertRaises(ValueError):
            hash_password("a" * 129)  # > 128 chars

    def test_verify_malformed_hash(self):
        self.assertFalse(verify_password("Password123!", "invalid_hash_string"))
        self.assertFalse(verify_password("Password123!", "scrypt$1$2$3$corrupt$corrupt"))

    def test_verify_parameter_bounds(self):
        # Exceeding N (e.g. 131072)
        oversized_n = "scrypt$131072$8$1$" + "00" * 16 + "$" + "00" * 64
        self.assertFalse(verify_password("Password123!", oversized_n))

        # Non-power-of-two N
        invalid_n = "scrypt$10000$8$1$" + "00" * 16 + "$" + "00" * 64
        self.assertFalse(verify_password("Password123!", invalid_n))

        # Oversized r
        oversized_r = "scrypt$16384$32$1$" + "00" * 16 + "$" + "00" * 64
        self.assertFalse(verify_password("Password123!", oversized_r))

        # Oversized p
        oversized_p = "scrypt$16384$8$16$" + "00" * 16 + "$" + "00" * 64
        self.assertFalse(verify_password("Password123!", oversized_p))

        # Salt too short (<16 bytes)
        short_salt = "scrypt$16384$8$1$" + "00" * 8 + "$" + "00" * 64
        self.assertFalse(verify_password("Password123!", short_salt))

    def test_dummy_hash_properties(self):
        self.assertTrue(DUMMY_PASSWORD_HASH.startswith("scrypt$16384$8$1$"))
        self.assertFalse(verify_password("AnyPassword!", DUMMY_PASSWORD_HASH))


class TestJWTToken(unittest.TestCase):
    def test_create_and_verify_jwt(self):
        user_id = "123e4567-e89b-12d3-a456-426614174000"
        email = "test.user@example.com"
        role = "passenger"

        token = create_jwt_token(user_id=user_id, email=email, role=role, expires_in_seconds=3600)
        self.assertIsInstance(token, str)
        self.assertEqual(len(token.split(".")), 3)

        payload = verify_jwt_token(token)
        self.assertEqual(payload["sub"], user_id)
        self.assertEqual(payload["email"], email)
        self.assertEqual(payload["role"], role)
        self.assertGreater(payload["exp"], time.time())

    def test_tampered_jwt_rejected(self):
        token = create_jwt_token("user1", "user@example.com", "passenger")
        parts = token.split(".")
        # Tamper payload
        tampered_token = f"{parts[0]}.eyJhZG1pbiI6IHRydWV9.{parts[2]}"

        with self.assertRaises(ValueError) as ctx:
            verify_jwt_token(tampered_token)
        self.assertIn("signature", str(ctx.exception).lower())

    def test_expired_jwt_rejected(self):
        # Create token already expired (-10 seconds)
        token = create_jwt_token("user1", "user@example.com", "passenger", expires_in_seconds=-10)
        with self.assertRaises(ValueError) as ctx:
            verify_jwt_token(token)
        self.assertIn("expired", str(ctx.exception).lower())

    def test_malformed_jwt_rejected(self):
        with self.assertRaises(ValueError):
            verify_jwt_token("not-a-token")
        with self.assertRaises(ValueError):
            verify_jwt_token("")

    def test_reject_non_hs256_algorithm(self):
        # Algorithm 'none' attack attempt
        header_none = _b64url_encode(b'{"alg":"none","typ":"JWT"}')
        payload = _b64url_encode(b'{"sub":"user1","exp":9999999999}')
        token_none = f"{header_none}.{payload}."
        with self.assertRaises(ValueError) as ctx:
            verify_jwt_token(token_none)
        self.assertIn("algorithm", str(ctx.exception).lower())

        # Asymmetric algorithm RS256 attempt
        header_rs256 = _b64url_encode(b'{"alg":"RS256","typ":"JWT"}')
        token_rs256 = f"{header_rs256}.{payload}.signature"
        with self.assertRaises(ValueError) as ctx:
            verify_jwt_token(token_rs256)
        self.assertIn("algorithm", str(ctx.exception).lower())

    def test_production_jwt_secret_enforcement(self):
        # When AWS_LAMBDA_FUNCTION_NAME is set, empty secret must raise RuntimeError
        with patch.dict(os.environ, {"AWS_LAMBDA_FUNCTION_NAME": "rentaseat-prod", "JWT_SECRET": ""}):
            with self.assertRaises(RuntimeError) as ctx:
                get_jwt_secret()
            self.assertIn("mandatory in deployed environments", str(ctx.exception))

        # When AWS_LAMBDA_FUNCTION_NAME is set, secret < 32 chars must raise RuntimeError
        with patch.dict(os.environ, {"AWS_LAMBDA_FUNCTION_NAME": "rentaseat-prod", "JWT_SECRET": "too-short"}):
            with self.assertRaises(RuntimeError) as ctx:
                get_jwt_secret()
            self.assertIn("at least 32 characters", str(ctx.exception))

        # Valid 32+ char secret in deployed environment succeeds
        valid_secret = "a" * 32
        with patch.dict(os.environ, {"AWS_LAMBDA_FUNCTION_NAME": "rentaseat-prod", "JWT_SECRET": valid_secret}):
            self.assertEqual(get_jwt_secret(), valid_secret)


class TestInputValidation(unittest.TestCase):
    def test_email_validation(self):
        self.assertEqual(validate_email("  Test@Example.COM "), "test@example.com")
        self.assertEqual(validate_email("user.name+tag@domain.co.uk"), "user.name+tag@domain.co.uk")

        invalid_emails = ["not-an-email", "@missing-user.com", "user@", "", None, 12345]
        for invalid in invalid_emails:
            with self.assertRaises(ValueError):
                validate_email(invalid)

    def test_name_validation(self):
        self.assertEqual(validate_name("  John Doe  "), "John Doe")
        with self.assertRaises(ValueError):
            validate_name("A")  # < 2 chars
        with self.assertRaises(ValueError):
            validate_name("")
        with self.assertRaises(ValueError):
            validate_name(None)

    def test_role_enforcement_prevents_admin_escalation(self):
        # Default role
        self.assertEqual(validate_registration_role(None), "passenger")
        self.assertEqual(validate_registration_role(""), "passenger")
        self.assertEqual(validate_registration_role("passenger"), "passenger")
        self.assertEqual(validate_registration_role("driver"), "driver")

        # Privilege escalation attempts must be rejected
        with self.assertRaises(ValueError) as ctx:
            validate_registration_role("admin")
        self.assertIn("admin", str(ctx.exception).lower())

        with self.assertRaises(ValueError) as ctx:
            validate_registration_role("superadmin")
        self.assertIn("invalid role", str(ctx.exception).lower())

    def test_password_input_validation(self):
        self.assertEqual(validate_password_input("ValidPassword123!"), "ValidPassword123!")
        with self.assertRaises(ValueError):
            validate_password_input("short")
        with self.assertRaises(ValueError):
            validate_password_input(None)

    def test_phone_validation(self):
        self.assertIsNone(validate_phone(None))
        self.assertIsNone(validate_phone(""))
        self.assertEqual(validate_phone("+1-555-0101"), "+1-555-0101")
        with self.assertRaises(ValueError):
            validate_phone("abc")


class TestLambdaAuthRouting(unittest.TestCase):
    def test_health_check_preserved(self):
        event = {
            "requestContext": {"http": {"method": "GET", "requestId": "test-req-1"}},
            "rawPath": "/health",
        }
        resp = lambda_handler(event, None)
        self.assertEqual(resp["statusCode"], 200)
        data = json.loads(resp["body"])
        self.assertEqual(data["status"], "ok")

    def test_register_missing_fields_returns_400(self):
        event = {
            "requestContext": {"http": {"method": "POST", "requestId": "test-req-2"}},
            "rawPath": "/auth/register",
            "body": json.dumps({"name": "Test User"}),  # missing email & password
        }
        resp = lambda_handler(event, None)
        self.assertEqual(resp["statusCode"], 400)
        data = json.loads(resp["body"])
        self.assertIn("error", data)

    def test_register_role_admin_escalation_returns_400(self):
        event = {
            "requestContext": {"http": {"method": "POST", "requestId": "test-req-3"}},
            "rawPath": "/auth/register",
            "body": json.dumps({
                "name": "Attacker",
                "email": "attacker@example.com",
                "password": "Password123!",
                "role": "admin",
            }),
        }
        resp = lambda_handler(event, None)
        self.assertEqual(resp["statusCode"], 400)
        data = json.loads(resp["body"])
        self.assertIn("admin", data["error"].lower())

    def test_register_payload_too_large_returns_400(self):
        oversized = "a" * 70000
        event = {
            "requestContext": {"http": {"method": "POST", "requestId": "test-req-4"}},
            "rawPath": "/auth/register",
            "body": json.dumps({"data": oversized}),
        }
        resp = lambda_handler(event, None)
        self.assertEqual(resp["statusCode"], 400)
        data = json.loads(resp["body"])
        self.assertIn("64 kb", data["error"].lower())

    def test_login_missing_credentials_returns_400(self):
        event = {
            "requestContext": {"http": {"method": "POST", "requestId": "test-req-5"}},
            "rawPath": "/auth/login",
            "body": json.dumps({"email": "test@example.com"}),  # missing password
        }
        resp = lambda_handler(event, None)
        self.assertEqual(resp["statusCode"], 400)

    def test_get_me_missing_bearer_token_returns_401(self):
        event = {
            "requestContext": {"http": {"method": "GET", "requestId": "test-req-6"}},
            "rawPath": "/auth/me",
            "headers": {},
        }
        resp = lambda_handler(event, None)
        self.assertEqual(resp["statusCode"], 401)

    @patch("backend.lambda_function._get_db_connection")
    def test_register_success_with_mock_db(self, mock_conn_fn):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_conn_fn.return_value = mock_conn

        # 1st query: email check (returns None -> no conflict)
        # 2nd query: insert user (returns created row)
        created_row = (
            "123e4567-e89b-12d3-a456-426614174000",
            "Jane Doe",
            "jane.doe@example.com",
            "+1-555-0199",
            "passenger",
            "active",
            None,
            5.0,
            0,
            "2026-10-22T19:00:00Z",
        )
        mock_cursor.fetchone.side_effect = [None, created_row]

        event = {
            "requestContext": {"http": {"method": "POST", "requestId": "test-req-7"}},
            "rawPath": "/auth/register",
            "body": json.dumps({
                "name": "Jane Doe",
                "email": "jane.doe@example.com",
                "password": "SecurePassword123!",
                "phone": "+1-555-0199",
                "role": "passenger",
            }),
        }

        resp = lambda_handler(event, None)
        self.assertEqual(resp["statusCode"], 201)
        data = json.loads(resp["body"])
        self.assertTrue(data["success"])
        self.assertIn("token", data)
        self.assertEqual(data["user"]["email"], "jane.doe@example.com")
        self.assertEqual(data["user"]["role"], "passenger")
        mock_conn.commit.assert_called_once()

    @patch("backend.lambda_function._get_db_connection")
    def test_register_duplicate_email_returns_409(self, mock_conn_fn):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_conn_fn.return_value = mock_conn

        # Email exists
        mock_cursor.fetchone.return_value = ("existing-user-id",)

        event = {
            "requestContext": {"http": {"method": "POST", "requestId": "test-req-8"}},
            "rawPath": "/auth/register",
            "body": json.dumps({
                "name": "Duplicate User",
                "email": "existing@example.com",
                "password": "Password123!",
            }),
        }

        resp = lambda_handler(event, None)
        self.assertEqual(resp["statusCode"], 409)
        data = json.loads(resp["body"])
        self.assertIn("already exists", data["error"])

    @patch("backend.lambda_function._get_db_connection")
    def test_login_success_with_mock_db(self, mock_conn_fn):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_conn_fn.return_value = mock_conn

        raw_pw = "ValidPassword123!"
        hashed_pw = hash_password(raw_pw)

        user_row = (
            "123e4567-e89b-12d3-a456-426614174000",
            "Jane Doe",
            "jane.doe@example.com",
            hashed_pw,
            "+1-555-0199",
            "driver",
            "active",
            None,
            4.8,
            12,
            "2026-10-22T19:00:00Z",
        )
        mock_cursor.fetchone.return_value = user_row

        event = {
            "requestContext": {"http": {"method": "POST", "requestId": "test-req-9"}},
            "rawPath": "/auth/login",
            "body": json.dumps({
                "email": "jane.doe@example.com",
                "password": raw_pw,
            }),
        }

        resp = lambda_handler(event, None)
        self.assertEqual(resp["statusCode"], 200)
        data = json.loads(resp["body"])
        self.assertTrue(data["success"])
        self.assertIn("token", data)
        self.assertEqual(data["user"]["role"], "driver")

    @patch("backend.lambda_function._get_db_connection")
    def test_login_wrong_password_returns_401(self, mock_conn_fn):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_conn_fn.return_value = mock_conn

        hashed_pw = hash_password("CorrectPassword123!")
        user_row = (
            "user-1", "Name", "user@example.com", hashed_pw, "", "passenger", "active", None, 5.0, 0, "2026-01-01"
        )
        mock_cursor.fetchone.return_value = user_row

        event = {
            "requestContext": {"http": {"method": "POST", "requestId": "test-req-10"}},
            "rawPath": "/auth/login",
            "body": json.dumps({
                "email": "user@example.com",
                "password": "WrongPassword999!",
            }),
        }

        resp = lambda_handler(event, None)
        self.assertEqual(resp["statusCode"], 401)
        data = json.loads(resp["body"])
        self.assertEqual(data["error"], "Invalid email or password.")

    @patch("backend.lambda_function._get_db_connection")
    def test_login_suspended_account_returns_403(self, mock_conn_fn):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_conn_fn.return_value = mock_conn

        raw_pw = "ValidPassword123!"
        hashed_pw = hash_password(raw_pw)
        user_row = (
            "user-1", "Name", "user@example.com", hashed_pw, "", "passenger", "suspended", None, 5.0, 0, "2026-01-01"
        )
        mock_cursor.fetchone.return_value = user_row

        event = {
            "requestContext": {"http": {"method": "POST", "requestId": "test-req-11"}},
            "rawPath": "/auth/login",
            "body": json.dumps({
                "email": "user@example.com",
                "password": raw_pw,
            }),
        }

        resp = lambda_handler(event, None)
        self.assertEqual(resp["statusCode"], 403)
        data = json.loads(resp["body"])
        self.assertIn("suspended", data["error"].lower())

    @patch("backend.lambda_function._get_db_connection")
    @patch("backend.lambda_function.verify_password")
    def test_login_nonexistent_user_executes_dummy_verification(self, mock_verify, mock_conn_fn):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_conn_fn.return_value = mock_conn

        # User not found in DB
        mock_cursor.fetchone.return_value = None

        event = {
            "requestContext": {"http": {"method": "POST", "requestId": "test-req-12"}},
            "rawPath": "/auth/login",
            "body": json.dumps({
                "email": "nonexistent@example.com",
                "password": "Password123!",
            }),
        }

        resp = lambda_handler(event, None)
        self.assertEqual(resp["statusCode"], 401)
        data = json.loads(resp["body"])
        self.assertEqual(data["error"], "Invalid email or password.")
        # Verifies dummy password computation was called to prevent timing enumeration
        mock_verify.assert_called_once_with("Password123!", DUMMY_PASSWORD_HASH)

    @patch("backend.lambda_function._get_db_connection")
    def test_register_race_condition_unique_violation_returns_409(self, mock_conn_fn):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_conn_fn.return_value = mock_conn

        # Check passes (None)
        mock_cursor.fetchone.return_value = None
        # But INSERT fails with unique constraint error
        mock_cursor.execute.side_effect = [
            None,  # SELECT email check
            Exception('duplicate key value violates unique constraint "uq_users_email"'),
        ]

        event = {
            "requestContext": {"http": {"method": "POST", "requestId": "test-req-13"}},
            "rawPath": "/auth/register",
            "body": json.dumps({
                "name": "Race User",
                "email": "race@example.com",
                "password": "Password123!",
            }),
        }

        resp = lambda_handler(event, None)
        self.assertEqual(resp["statusCode"], 409)
        data = json.loads(resp["body"])
        self.assertIn("already exists", data["error"])
        mock_conn.rollback.assert_called_once()


if __name__ == "__main__":
    unittest.main()
