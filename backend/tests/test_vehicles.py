#!/usr/bin/env python3
"""
Unit Test Suite for RentASeat Vehicle Management APIs
Covers vehicle validation, normalization, and Lambda HTTP handlers:
  - POST   /vehicles
  - GET    /vehicles
  - GET    /vehicles/{id}
  - PUT    /vehicles/{id} & PATCH /vehicles/{id}
  - DELETE /vehicles/{id}

Tests verify:
  - Input validation (types, models, registration numbers, seating capacities)
  - Role-based authorization (drivers & admins permitted, passengers rejected)
  - Ownership enforcement (drivers cannot view/edit/delete other drivers' vehicles)
  - Admin override permissions
  - Journey capacity constraints on vehicle updates
  - Journey dependency constraints on vehicle deletion (409 Conflict)
  - Duplicate registration handling (409 Conflict)
  - Sanitized error responses on missing records and DB errors
"""

import datetime
import json
import unittest
from unittest.mock import MagicMock, patch

from backend.auth import create_jwt_token
from backend.lambda_function import lambda_handler
from backend.vehicles import (
    ALLOWED_VEHICLE_TYPES,
    format_vehicle_row,
    validate_colour,
    validate_image_url,
    validate_model,
    validate_registration_number,
    validate_seating_capacity,
    validate_vehicle_payload,
    validate_vehicle_type,
)


class TestVehicleValidation(unittest.TestCase):
    def test_validate_vehicle_type(self):
        for v_type in ALLOWED_VEHICLE_TYPES:
            self.assertEqual(validate_vehicle_type(v_type), v_type)
            self.assertEqual(validate_vehicle_type(f"  {v_type.upper()}  "), v_type)

        invalid_types = ["truck", "motorcycle", "bus", "", None, 123]
        for inv in invalid_types:
            with self.assertRaises(ValueError):
                validate_vehicle_type(inv)

    def test_validate_registration_number(self):
        self.assertEqual(validate_registration_number("  ka-01-ab-1234  "), "KA-01-AB-1234")
        self.assertEqual(validate_registration_number("DL10CA0001"), "DL10CA0001")

        with self.assertRaises(ValueError):
            validate_registration_number("A")  # < 2 chars
        with self.assertRaises(ValueError):
            validate_registration_number("A" * 31)  # > 30 chars
        with self.assertRaises(ValueError):
            validate_registration_number("")
        with self.assertRaises(ValueError):
            validate_registration_number(None)

    def test_validate_model(self):
        self.assertEqual(validate_model("  Toyota Prius  "), "Toyota Prius")
        with self.assertRaises(ValueError):
            validate_model("X")  # < 2 chars
        with self.assertRaises(ValueError):
            validate_model("X" * 101)  # > 100 chars
        with self.assertRaises(ValueError):
            validate_model("")
        with self.assertRaises(ValueError):
            validate_model(None)

    def test_validate_seating_capacity(self):
        self.assertEqual(validate_seating_capacity(1), 1)
        self.assertEqual(validate_seating_capacity(4), 4)
        self.assertEqual(validate_seating_capacity(20), 20)
        self.assertEqual(validate_seating_capacity("6"), 6)

        invalid_capacities = [0, -1, 21, 100, "abc", None]
        for inv in invalid_capacities:
            with self.assertRaises(ValueError):
                validate_seating_capacity(inv)

    def test_validate_colour_and_image(self):
        self.assertEqual(validate_colour("  Silver  "), "Silver")
        self.assertIsNone(validate_colour(None))
        self.assertIsNone(validate_colour(""))
        with self.assertRaises(ValueError):
            validate_colour("C" * 51)

        self.assertEqual(validate_image_url("https://example.com/car.jpg"), "https://example.com/car.jpg")
        self.assertIsNone(validate_image_url(None))
        self.assertIsNone(validate_image_url(""))
        with self.assertRaises(ValueError):
            validate_image_url("I" * 501)

    def test_validate_vehicle_payload_create(self):
        payload = {
            "registrationNumber": "ka-05-mj-5678",
            "vehicleType": "suv",
            "model": "Hyundai Creta",
            "seatingCapacity": 5,
            "colour": "White",
            "imageUrl": "https://example.com/creta.jpg",
        }
        res = validate_vehicle_payload(payload, is_update=False)
        self.assertEqual(res["registration_number"], "KA-05-MJ-5678")
        self.assertEqual(res["vehicle_type"], "suv")
        self.assertEqual(res["model"], "Hyundai Creta")
        self.assertEqual(res["seating_capacity"], 5)
        self.assertEqual(res["colour"], "White")
        self.assertEqual(res["image_url"], "https://example.com/creta.jpg")

    def test_validate_vehicle_payload_update(self):
        partial_payload = {
            "model": "Honda Civic",
            "seatingCapacity": 4,
        }
        res = validate_vehicle_payload(partial_payload, is_update=True)
        self.assertEqual(res["model"], "Honda Civic")
        self.assertEqual(res["seating_capacity"], 4)
        self.assertNotIn("registration_number", res)

    def test_format_vehicle_row(self):
        now = datetime.datetime(2026, 10, 22, 12, 0, 0, tzinfo=datetime.timezone.utc)
        row = (
            "veh-123",
            "driver-456",
            "MH-02-CD-9999",
            "sedan",
            "Honda City",
            "Silver",
            4,
            "https://example.com/city.jpg",
            now,
            now,
        )
        formatted = format_vehicle_row(row)
        self.assertEqual(formatted["id"], "veh-123")
        self.assertEqual(formatted["driverId"], "driver-456")
        self.assertEqual(formatted["registrationNumber"], "MH-02-CD-9999")
        self.assertEqual(formatted["vehicleType"], "sedan")
        self.assertEqual(formatted["model"], "Honda City")
        self.assertEqual(formatted["colour"], "Silver")
        self.assertEqual(formatted["seatingCapacity"], 4)
        self.assertEqual(formatted["imageUrl"], "https://example.com/city.jpg")
        self.assertIn("2026-10-22", formatted["createdAt"])


class TestVehicleLambda(unittest.TestCase):
    def setUp(self):
        self.driver_id = "11111111-1111-1111-1111-111111111111"
        self.other_driver_id = "22222222-2222-2222-2222-222222222222"
        self.admin_id = "99999999-9999-9999-9999-999999999999"
        self.passenger_id = "33333333-3333-3333-3333-333333333333"

        self.driver_token = create_jwt_token(self.driver_id, "driver@example.com", "driver")
        self.other_driver_token = create_jwt_token(self.other_driver_id, "other@example.com", "driver")
        self.admin_token = create_jwt_token(self.admin_id, "admin@example.com", "admin")
        self.passenger_token = create_jwt_token(self.passenger_id, "passenger@example.com", "passenger")

    def _auth_header(self, token: str) -> dict:
        return {"authorization": f"Bearer {token}"}

    # ─── Create Vehicle ────────────────────────────────────────────────────────

    @patch("backend.lambda_function._get_db_connection")
    def test_create_vehicle_success(self, mock_conn_fn):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_conn_fn.return_value = mock_conn

        # Auth check row: user_id, name, email, phone, role, status
        user_row = (self.driver_id, "Driver One", "driver@example.com", "", "driver", "active")
        now = datetime.datetime.now(datetime.timezone.utc)
        created_row = (
            "veh-new-uuid",
            self.driver_id,
            "KA-01-AB-1234",
            "sedan",
            "Toyota Camry",
            "Black",
            4,
            "",
            now,
            now,
        )
        mock_cursor.fetchone.side_effect = [user_row, created_row]

        event = {
            "requestContext": {"http": {"method": "POST", "requestId": "req-v-1"}},
            "rawPath": "/vehicles",
            "headers": self._auth_header(self.driver_token),
            "body": json.dumps({
                "registrationNumber": "ka-01-ab-1234",
                "vehicleType": "sedan",
                "model": "Toyota Camry",
                "seatingCapacity": 4,
                "colour": "Black",
            }),
        }

        resp = lambda_handler(event, None)
        self.assertEqual(resp["statusCode"], 201)
        data = json.loads(resp["body"])
        self.assertTrue(data["success"])
        self.assertEqual(data["vehicle"]["registrationNumber"], "KA-01-AB-1234")
        self.assertEqual(data["vehicle"]["driverId"], self.driver_id)
        mock_conn.commit.assert_called_once()

    @patch("backend.lambda_function._get_db_connection")
    def test_create_vehicle_passenger_role_rejected(self, mock_conn_fn):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_conn_fn.return_value = mock_conn

        # Passenger user
        user_row = (self.passenger_id, "Passenger", "p@example.com", "", "passenger", "active")
        mock_cursor.fetchone.return_value = user_row

        event = {
            "requestContext": {"http": {"method": "POST", "requestId": "req-v-2"}},
            "rawPath": "/vehicles",
            "headers": self._auth_header(self.passenger_token),
            "body": json.dumps({
                "registrationNumber": "KA-01-AB-1234",
                "vehicleType": "sedan",
                "model": "Toyota Camry",
                "seatingCapacity": 4,
            }),
        }

        resp = lambda_handler(event, None)
        self.assertEqual(resp["statusCode"], 403)
        data = json.loads(resp["body"])
        self.assertIn("driver role required", data["error"].lower())

    @patch("backend.lambda_function._get_db_connection")
    def test_create_vehicle_duplicate_registration_returns_409(self, mock_conn_fn):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_conn_fn.return_value = mock_conn

        user_row = (self.driver_id, "Driver One", "driver@example.com", "", "driver", "active")
        mock_cursor.fetchone.return_value = user_row
        # INSERT raises unique constraint error
        mock_cursor.execute.side_effect = [
            None,  # Auth user lookup
            Exception('duplicate key value violates unique constraint "uq_vehicles_registration"'),
        ]

        event = {
            "requestContext": {"http": {"method": "POST", "requestId": "req-v-3"}},
            "rawPath": "/vehicles",
            "headers": self._auth_header(self.driver_token),
            "body": json.dumps({
                "registrationNumber": "KA-01-AB-1234",
                "vehicleType": "sedan",
                "model": "Toyota Camry",
                "seatingCapacity": 4,
            }),
        }

        resp = lambda_handler(event, None)
        self.assertEqual(resp["statusCode"], 409)
        data = json.loads(resp["body"])
        self.assertIn("already exists", data["error"])
        mock_conn.rollback.assert_called_once()

    def test_create_vehicle_unauthenticated_returns_401(self):
        event = {
            "requestContext": {"http": {"method": "POST", "requestId": "req-v-4"}},
            "rawPath": "/vehicles",
            "headers": {},
            "body": json.dumps({"model": "Test"}),
        }
        resp = lambda_handler(event, None)
        self.assertEqual(resp["statusCode"], 401)

    # ─── List Vehicles ─────────────────────────────────────────────────────────

    @patch("backend.lambda_function._get_db_connection")
    def test_list_vehicles_for_driver(self, mock_conn_fn):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_conn_fn.return_value = mock_conn

        user_row = (self.driver_id, "Driver One", "driver@example.com", "", "driver", "active")
        mock_cursor.fetchone.return_value = user_row

        now = datetime.datetime.now(datetime.timezone.utc)
        vehicle_rows = [
            ("veh-1", self.driver_id, "KA-01-AA-1111", "sedan", "Camry", "White", 4, "", now, now),
            ("veh-2", self.driver_id, "KA-01-BB-2222", "suv", "Innova", "Silver", 7, "", now, now),
        ]
        mock_cursor.fetchall.return_value = vehicle_rows

        event = {
            "requestContext": {"http": {"method": "GET", "requestId": "req-v-5"}},
            "rawPath": "/vehicles",
            "headers": self._auth_header(self.driver_token),
        }

        resp = lambda_handler(event, None)
        self.assertEqual(resp["statusCode"], 200)
        data = json.loads(resp["body"])
        self.assertTrue(data["success"])
        self.assertEqual(len(data["vehicles"]), 2)
        self.assertEqual(data["vehicles"][0]["registrationNumber"], "KA-01-AA-1111")
        self.assertEqual(data["vehicles"][1]["registrationNumber"], "KA-01-BB-2222")

    # ─── Get Vehicle by ID ─────────────────────────────────────────────────────

    @patch("backend.lambda_function._get_db_connection")
    def test_get_vehicle_by_id_owner_success(self, mock_conn_fn):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_conn_fn.return_value = mock_conn

        user_row = (self.driver_id, "Driver One", "driver@example.com", "", "driver", "active")
        now = datetime.datetime.now(datetime.timezone.utc)
        veh_row = ("veh-1", self.driver_id, "KA-01-AA-1111", "sedan", "Camry", "White", 4, "", now, now)

        mock_cursor.fetchone.side_effect = [user_row, veh_row]

        event = {
            "requestContext": {"http": {"method": "GET", "requestId": "req-v-6"}},
            "rawPath": "/vehicles/veh-1",
            "headers": self._auth_header(self.driver_token),
        }

        resp = lambda_handler(event, None)
        self.assertEqual(resp["statusCode"], 200)
        data = json.loads(resp["body"])
        self.assertEqual(data["vehicle"]["id"], "veh-1")

    @patch("backend.lambda_function._get_db_connection")
    def test_get_vehicle_by_id_ownership_forbidden_for_other_driver(self, mock_conn_fn):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_conn_fn.return_value = mock_conn

        # Other driver requests veh-1 which belongs to self.driver_id
        user_row = (self.other_driver_id, "Other Driver", "other@example.com", "", "driver", "active")
        now = datetime.datetime.now(datetime.timezone.utc)
        veh_row = ("veh-1", self.driver_id, "KA-01-AA-1111", "sedan", "Camry", "White", 4, "", now, now)

        mock_cursor.fetchone.side_effect = [user_row, veh_row]

        event = {
            "requestContext": {"http": {"method": "GET", "requestId": "req-v-7"}},
            "rawPath": "/vehicles/veh-1",
            "headers": self._auth_header(self.other_driver_token),
        }

        resp = lambda_handler(event, None)
        self.assertEqual(resp["statusCode"], 403)
        data = json.loads(resp["body"])
        self.assertIn("permission", data["error"].lower())

    @patch("backend.lambda_function._get_db_connection")
    def test_get_vehicle_by_id_admin_allowed(self, mock_conn_fn):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_conn_fn.return_value = mock_conn

        # Admin requests veh-1 which belongs to self.driver_id
        admin_row = (self.admin_id, "Admin User", "admin@example.com", "", "admin", "active")
        now = datetime.datetime.now(datetime.timezone.utc)
        veh_row = ("veh-1", self.driver_id, "KA-01-AA-1111", "sedan", "Camry", "White", 4, "", now, now)

        mock_cursor.fetchone.side_effect = [admin_row, veh_row]

        event = {
            "requestContext": {"http": {"method": "GET", "requestId": "req-v-8"}},
            "rawPath": "/vehicles/veh-1",
            "headers": self._auth_header(self.admin_token),
        }

        resp = lambda_handler(event, None)
        self.assertEqual(resp["statusCode"], 200)

    @patch("backend.lambda_function._get_db_connection")
    def test_get_vehicle_not_found_returns_404(self, mock_conn_fn):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_conn_fn.return_value = mock_conn

        user_row = (self.driver_id, "Driver One", "driver@example.com", "", "driver", "active")
        mock_cursor.fetchone.side_effect = [user_row, None]  # vehicle not found

        event = {
            "requestContext": {"http": {"method": "GET", "requestId": "req-v-9"}},
            "rawPath": "/vehicles/non-existent-veh",
            "headers": self._auth_header(self.driver_token),
        }

        resp = lambda_handler(event, None)
        self.assertEqual(resp["statusCode"], 404)

    # ─── Update Vehicle ────────────────────────────────────────────────────────

    @patch("backend.lambda_function._get_db_connection")
    def test_update_vehicle_success(self, mock_conn_fn):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_conn_fn.return_value = mock_conn

        user_row = (self.driver_id, "Driver One", "driver@example.com", "", "driver", "active")
        existing_veh = ("veh-1", self.driver_id, "KA-01-AA-1111", "sedan", "Camry", "White", 4, "")
        # max journey seats check: returns 0 active seats
        now = datetime.datetime.now(datetime.timezone.utc)
        updated_veh = ("veh-1", self.driver_id, "KA-01-AA-1111", "sedan", "Camry 2026", "Black", 5, "", now, now)

        mock_cursor.fetchone.side_effect = [user_row, existing_veh, (0,), updated_veh]

        event = {
            "requestContext": {"http": {"method": "PUT", "requestId": "req-v-10"}},
            "rawPath": "/vehicles/veh-1",
            "headers": self._auth_header(self.driver_token),
            "body": json.dumps({
                "model": "Camry 2026",
                "colour": "Black",
                "seatingCapacity": 5,
            }),
        }

        resp = lambda_handler(event, None)
        self.assertEqual(resp["statusCode"], 200)
        data = json.loads(resp["body"])
        self.assertEqual(data["vehicle"]["model"], "Camry 2026")
        self.assertEqual(data["vehicle"]["colour"], "Black")
        mock_conn.commit.assert_called_once()

    @patch("backend.lambda_function._get_db_connection")
    def test_update_vehicle_capacity_conflict_with_active_journey(self, mock_conn_fn):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_conn_fn.return_value = mock_conn

        user_row = (self.driver_id, "Driver One", "driver@example.com", "", "driver", "active")
        existing_veh = ("veh-1", self.driver_id, "KA-01-AA-1111", "sedan", "Camry", "White", 6, "")
        # Active journey requires 5 seats
        mock_cursor.fetchone.side_effect = [user_row, existing_veh, (5,)]

        # Driver attempts to reduce seating capacity to 4 (< 5 active seats)
        event = {
            "requestContext": {"http": {"method": "PATCH", "requestId": "req-v-11"}},
            "rawPath": "/vehicles/veh-1",
            "headers": self._auth_header(self.driver_token),
            "body": json.dumps({"seatingCapacity": 4}),
        }

        resp = lambda_handler(event, None)
        self.assertEqual(resp["statusCode"], 409)
        data = json.loads(resp["body"])
        self.assertIn("cannot reduce seating capacity", data["error"].lower())

    # ─── Delete Vehicle ────────────────────────────────────────────────────────

    @patch("backend.lambda_function._get_db_connection")
    def test_delete_vehicle_success(self, mock_conn_fn):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_conn_fn.return_value = mock_conn

        user_row = (self.driver_id, "Driver One", "driver@example.com", "", "driver", "active")
        existing_veh = ("veh-1", self.driver_id)
        # Journey count: 0
        mock_cursor.fetchone.side_effect = [user_row, existing_veh, (0,)]

        event = {
            "requestContext": {"http": {"method": "DELETE", "requestId": "req-v-12"}},
            "rawPath": "/vehicles/veh-1",
            "headers": self._auth_header(self.driver_token),
        }

        resp = lambda_handler(event, None)
        self.assertEqual(resp["statusCode"], 200)
        data = json.loads(resp["body"])
        self.assertTrue(data["success"])
        mock_conn.commit.assert_called_once()

    @patch("backend.lambda_function._get_db_connection")
    def test_delete_vehicle_conflict_with_existing_journeys(self, mock_conn_fn):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_conn_fn.return_value = mock_conn

        user_row = (self.driver_id, "Driver One", "driver@example.com", "", "driver", "active")
        existing_veh = ("veh-1", self.driver_id)
        # Journey count: 2
        mock_cursor.fetchone.side_effect = [user_row, existing_veh, (2,)]

        event = {
            "requestContext": {"http": {"method": "DELETE", "requestId": "req-v-13"}},
            "rawPath": "/vehicles/veh-1",
            "headers": self._auth_header(self.driver_token),
        }

        resp = lambda_handler(event, None)
        self.assertEqual(resp["statusCode"], 409)
        data = json.loads(resp["body"])
        self.assertIn("associated with 2 existing journey", data["error"].lower())


if __name__ == "__main__":
    unittest.main()
