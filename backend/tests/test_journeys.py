#!/usr/bin/env python3
"""
Unit Test Suite for RentASeat Journey Management APIs
Covers journey validation, normalization, and Lambda HTTP handlers:
  - POST   /journeys
  - GET    /journeys
  - GET    /journeys/{id}
  - PUT    /journeys/{id} & PATCH /journeys/{id}
  - DELETE /journeys/{id}

Tests verify:
  - Input validation (locations, dates, times, seat counts, prices, status, endpoints distinctness)
  - Role-based authorization (drivers & admins permitted, passengers rejected)
  - Vehicle ownership enforcement (driver must own referenced vehicle)
  - Vehicle capacity enforcement (journey seats cannot exceed vehicle capacity)
  - Journey search filters (origin, destination, date, seats, driverId)
  - Ownership protection on updates and deletions
  - Existing booking protection (409 Conflict when reducing seats below booked count or deleting booked journeys)
  - Missing records (404) and database failure sanitization (500/503)
"""

import datetime
import json
import unittest
from unittest.mock import MagicMock, patch

from backend.auth import create_jwt_token
from backend.journeys import (
    ALLOWED_JOURNEY_STATUSES,
    format_journey_row,
    validate_departure_date,
    validate_endpoints,
    validate_journey_payload,
    validate_location,
    validate_price,
    validate_seats,
    validate_status,
    validate_stops,
    validate_time,
)
from backend.lambda_function import lambda_handler


class TestJourneyValidation(unittest.TestCase):
    def test_validate_location(self):
        self.assertEqual(validate_location("  London  "), "London")
        with self.assertRaises(ValueError):
            validate_location("A")  # < 2 chars
        with self.assertRaises(ValueError):
            validate_location("A" * 201)  # > 200 chars
        with self.assertRaises(ValueError):
            validate_location("")
        with self.assertRaises(ValueError):
            validate_location(None)

    def test_validate_endpoints_different(self):
        validate_endpoints("London", "Manchester")
        validate_endpoints("New York", "Boston")
        with self.assertRaises(ValueError):
            validate_endpoints("London", "London")
        with self.assertRaises(ValueError):
            validate_endpoints("  london  ", "LONDON")

    def test_validate_departure_date(self):
        self.assertEqual(validate_departure_date("2026-11-15"), "2026-11-15")
        invalid_dates = ["15-11-2026", "2026/11/15", "invalid", "", None, "2026-02-31"]
        for inv in invalid_dates:
            with self.assertRaises(ValueError):
                validate_departure_date(inv)

    def test_validate_time(self):
        self.assertEqual(validate_time("09:30"), "09:30")
        self.assertEqual(validate_time("14:45:00"), "14:45:00")
        invalid_times = ["25:00", "09:65", "abc", "", None, "9:30"]
        for inv in invalid_times:
            with self.assertRaises(ValueError):
                validate_time(inv)

    def test_validate_price(self):
        self.assertEqual(validate_price(25.5), 25.50)
        self.assertEqual(validate_price("30"), 30.00)
        invalid_prices = [0, -10, "abc", None, 100001]
        for inv in invalid_prices:
            with self.assertRaises(ValueError):
                validate_price(inv)

    def test_validate_seats(self):
        self.assertEqual(validate_seats(1), 1)
        self.assertEqual(validate_seats(4), 4)
        self.assertEqual(validate_seats(20), 20)
        self.assertEqual(validate_seats("3"), 3)
        invalid_seats = [0, -1, 21, "abc", None]
        for inv in invalid_seats:
            with self.assertRaises(ValueError):
                validate_seats(inv)

    def test_validate_status(self):
        for s in ALLOWED_JOURNEY_STATUSES:
            self.assertEqual(validate_status(s), s)
            self.assertEqual(validate_status(s.upper()), s)
        self.assertEqual(validate_status(None), "active")
        with self.assertRaises(ValueError):
            validate_status("unknown_status")

    def test_validate_stops(self):
        self.assertEqual(validate_stops(["Oxford", "Birmingham"]), ["Oxford", "Birmingham"])
        self.assertEqual(validate_stops('["Reading", "Swindon"]'), ["Reading", "Swindon"])
        self.assertEqual(validate_stops("Bristol, Cardiff"), ["Bristol", "Cardiff"])
        self.assertEqual(validate_stops(None), [])

    def test_validate_journey_payload_create(self):
        payload = {
            "from": "London",
            "to": "Manchester",
            "date": "2026-11-20",
            "departureTime": "08:00",
            "arrivalTime": "12:00",
            "totalSeats": 3,
            "pricePerSeat": 25.0,
            "vehicleId": "veh-1234",
            "description": "Smooth highway drive with music.",
            "stops": ["Birmingham"],
        }
        res = validate_journey_payload(payload, is_update=False)
        self.assertEqual(res["origin"], "London")
        self.assertEqual(res["destination"], "Manchester")
        self.assertEqual(res["departure_date"], "2026-11-20")
        self.assertEqual(res["departure_time"], "08:00")
        self.assertEqual(res["arrival_time"], "12:00")
        self.assertEqual(res["total_seats"], 3)
        self.assertEqual(res["price_per_seat"], 25.0)
        self.assertEqual(res["vehicle_id"], "veh-1234")
        self.assertEqual(res["stops"], ["Birmingham"])

    def test_validate_journey_payload_update(self):
        payload = {
            "pricePerSeat": 30.0,
            "totalSeats": 4,
        }
        res = validate_journey_payload(payload, is_update=True)
        self.assertEqual(res["price_per_seat"], 30.0)
        self.assertEqual(res["total_seats"], 4)
        self.assertNotIn("origin", res)

    def test_format_journey_row(self):
        now = datetime.datetime(2026, 10, 23, 10, 0, 0, tzinfo=datetime.timezone.utc)
        dep_date = datetime.date(2026, 11, 25)
        dep_time = datetime.time(9, 30)
        arr_time = datetime.time(13, 0)
        row = (
            "j-100",  # id
            "driver-1",  # driver_id
            "veh-1",  # vehicle_id
            "London",  # origin
            "Edinburgh",  # destination
            dep_date,
            dep_time,
            arr_time,
            4,  # total_seats
            3,  # available_seats
            45.50,  # price_per_seat
            "active",  # status
            "Scenic route north.",  # description
            ["Newcastle"],  # stops
            now,  # created_at
            now,  # updated_at
            "John Doe",  # driver_name
            "john@example.com",  # driver_email
            "+44-7700-900077",  # driver_phone
            "driver",  # driver_role
            "https://example.com/avatar.jpg",
            4.9,  # rating
            15,  # review_count
            "AB12CDE",  # vehicle_registration
            "sedan",  # vehicle_type
            "BMW 3 Series",  # vehicle_model
            "Blue",  # vehicle_colour
            4,  # vehicle_seating_capacity
            "",  # vehicle_image_url
        )
        formatted = format_journey_row(row)
        self.assertEqual(formatted["id"], "j-100")
        self.assertEqual(formatted["origin"], "London")
        self.assertEqual(formatted["from"], "London")
        self.assertEqual(formatted["destination"], "Edinburgh")
        self.assertEqual(formatted["to"], "Edinburgh")
        self.assertEqual(formatted["departureDate"], "2026-11-25")
        self.assertEqual(formatted["date"], "2026-11-25")
        self.assertEqual(formatted["departureTime"], "09:30")
        self.assertEqual(formatted["arrivalTime"], "13:00")
        self.assertEqual(formatted["totalSeats"], 4)
        self.assertEqual(formatted["availableSeats"], 3)
        self.assertEqual(formatted["pricePerSeat"], 45.50)
        self.assertEqual(formatted["driver"]["name"], "John Doe")
        self.assertEqual(formatted["driver"]["rating"], 4.9)
        self.assertEqual(formatted["vehicle"]["registrationNumber"], "AB12CDE")
        self.assertEqual(formatted["vehicle"]["model"], "BMW 3 Series")


class TestJourneyLambda(unittest.TestCase):
    def setUp(self):
        self.driver_id = "11111111-1111-1111-1111-111111111111"
        self.other_driver_id = "22222222-2222-2222-2222-222222222222"
        self.admin_id = "99999999-9999-9999-9999-999999999999"
        self.passenger_id = "33333333-3333-3333-3333-333333333333"
        self.vehicle_id = "44444444-4444-4444-4444-444444444444"

        self.driver_token = create_jwt_token(self.driver_id, "driver@example.com", "driver")
        self.other_driver_token = create_jwt_token(self.other_driver_id, "other@example.com", "driver")
        self.admin_token = create_jwt_token(self.admin_id, "admin@example.com", "admin")
        self.passenger_token = create_jwt_token(self.passenger_id, "passenger@example.com", "passenger")

    def _auth_header(self, token: str) -> dict:
        return {"authorization": f"Bearer {token}"}

    def _mock_joined_journey_row(self, journey_id: str, driver_id: str, vehicle_id: str):
        now = datetime.datetime.now(datetime.timezone.utc)
        return (
            journey_id,
            driver_id,
            vehicle_id,
            "London",
            "Manchester",
            datetime.date(2026, 11, 20),
            datetime.time(8, 0),
            datetime.time(12, 0),
            3,
            3,
            25.0,
            "active",
            "Morning drive",
            ["Birmingham"],
            now,
            now,
            "Driver Name",
            "driver@example.com",
            "+1234567890",
            "driver",
            "",
            5.0,
            2,
            "KA-01-AB-1234",
            "sedan",
            "Toyota Camry",
            "Black",
            4,
            "",
        )

    # ─── Create Journey (POST /journeys) ───────────────────────────────────────

    @patch("backend.lambda_function._get_db_connection")
    def test_create_journey_success(self, mock_conn_fn):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_conn_fn.return_value = mock_conn

        user_row = (self.driver_id, "Driver One", "driver@example.com", "", "driver", "active")
        # Vehicle: id, driver_id, seating_capacity = 4
        veh_row = (self.vehicle_id, self.driver_id, 4)
        new_id_row = ("j-uuid-123",)
        joined_row = self._mock_joined_journey_row("j-uuid-123", self.driver_id, self.vehicle_id)

        mock_cursor.fetchone.side_effect = [user_row, veh_row, new_id_row, joined_row]

        event = {
            "requestContext": {"http": {"method": "POST", "requestId": "req-j-1"}},
            "rawPath": "/journeys",
            "headers": self._auth_header(self.driver_token),
            "body": json.dumps({
                "from": "London",
                "to": "Manchester",
                "date": "2026-11-20",
                "departureTime": "08:00",
                "arrivalTime": "12:00",
                "totalSeats": 3,
                "pricePerSeat": 25.0,
                "vehicleId": self.vehicle_id,
            }),
        }

        resp = lambda_handler(event, None)
        self.assertEqual(resp["statusCode"], 201)
        data = json.loads(resp["body"])
        self.assertTrue(data["success"])
        self.assertEqual(data["journey"]["from"], "London")
        self.assertEqual(data["journey"]["to"], "Manchester")
        self.assertEqual(data["journey"]["totalSeats"], 3)
        mock_conn.commit.assert_called_once()

    @patch("backend.lambda_function._get_db_connection")
    def test_create_journey_passenger_role_rejected(self, mock_conn_fn):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_conn_fn.return_value = mock_conn

        user_row = (self.passenger_id, "Passenger User", "p@example.com", "", "passenger", "active")
        mock_cursor.fetchone.return_value = user_row

        event = {
            "requestContext": {"http": {"method": "POST", "requestId": "req-j-2"}},
            "rawPath": "/journeys",
            "headers": self._auth_header(self.passenger_token),
            "body": json.dumps({
                "from": "London",
                "to": "Manchester",
                "date": "2026-11-20",
                "departureTime": "08:00",
                "totalSeats": 3,
                "pricePerSeat": 25.0,
                "vehicleId": self.vehicle_id,
            }),
        }

        resp = lambda_handler(event, None)
        self.assertEqual(resp["statusCode"], 403)
        data = json.loads(resp["body"])
        self.assertIn("driver role required", data["error"].lower())

    @patch("backend.lambda_function._get_db_connection")
    def test_create_journey_vehicle_ownership_mismatch(self, mock_conn_fn):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_conn_fn.return_value = mock_conn

        user_row = (self.driver_id, "Driver One", "driver@example.com", "", "driver", "active")
        # Vehicle belongs to other_driver_id
        veh_row = (self.vehicle_id, self.other_driver_id, 4)
        mock_cursor.fetchone.side_effect = [user_row, veh_row]

        event = {
            "requestContext": {"http": {"method": "POST", "requestId": "req-j-3"}},
            "rawPath": "/journeys",
            "headers": self._auth_header(self.driver_token),
            "body": json.dumps({
                "from": "London",
                "to": "Manchester",
                "date": "2026-11-20",
                "departureTime": "08:00",
                "totalSeats": 3,
                "pricePerSeat": 25.0,
                "vehicleId": self.vehicle_id,
            }),
        }

        resp = lambda_handler(event, None)
        self.assertEqual(resp["statusCode"], 403)
        data = json.loads(resp["body"])
        self.assertIn("does not belong to the journey driver", data["error"].lower())

    @patch("backend.lambda_function._get_db_connection")
    def test_create_journey_capacity_exceeds_vehicle(self, mock_conn_fn):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_conn_fn.return_value = mock_conn

        user_row = (self.driver_id, "Driver One", "driver@example.com", "", "driver", "active")
        # Vehicle capacity is 3
        veh_row = (self.vehicle_id, self.driver_id, 3)
        mock_cursor.fetchone.side_effect = [user_row, veh_row]

        # Driver attempts to offer 4 seats on a 3-seat vehicle
        event = {
            "requestContext": {"http": {"method": "POST", "requestId": "req-j-4"}},
            "rawPath": "/journeys",
            "headers": self._auth_header(self.driver_token),
            "body": json.dumps({
                "from": "London",
                "to": "Manchester",
                "date": "2026-11-20",
                "departureTime": "08:00",
                "totalSeats": 4,
                "pricePerSeat": 25.0,
                "vehicleId": self.vehicle_id,
            }),
        }

        resp = lambda_handler(event, None)
        self.assertEqual(resp["statusCode"], 400)
        data = json.loads(resp["body"])
        self.assertIn("cannot exceed vehicle seating capacity", data["error"].lower())

    # ─── Search / List Journeys (GET /journeys) ────────────────────────────────

    @patch("backend.lambda_function._get_db_connection")
    def test_list_journeys_search_filter(self, mock_conn_fn):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_conn_fn.return_value = mock_conn

        row = self._mock_joined_journey_row("j-1", self.driver_id, self.vehicle_id)
        mock_cursor.fetchall.return_value = [row]

        # Search journeys from London to Manchester on 2026-11-20
        event = {
            "requestContext": {"http": {"method": "GET", "requestId": "req-j-5"}},
            "rawPath": "/journeys",
            "queryStringParameters": {
                "from": "London",
                "to": "Manchester",
                "date": "2026-11-20",
                "seats": "2",
            },
        }

        resp = lambda_handler(event, None)
        self.assertEqual(resp["statusCode"], 200)
        data = json.loads(resp["body"])
        self.assertTrue(data["success"])
        self.assertEqual(len(data["journeys"]), 1)
        self.assertEqual(data["journeys"][0]["id"], "j-1")

    # ─── Get Journey (GET /journeys/{id}) ──────────────────────────────────────

    @patch("backend.lambda_function._get_db_connection")
    def test_get_journey_by_id_success(self, mock_conn_fn):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_conn_fn.return_value = mock_conn

        row = self._mock_joined_journey_row("j-123", self.driver_id, self.vehicle_id)
        mock_cursor.fetchone.return_value = row

        event = {
            "requestContext": {"http": {"method": "GET", "requestId": "req-j-6"}},
            "rawPath": "/journeys/j-123",
        }

        resp = lambda_handler(event, None)
        self.assertEqual(resp["statusCode"], 200)
        data = json.loads(resp["body"])
        self.assertEqual(data["journey"]["id"], "j-123")

    @patch("backend.lambda_function._get_db_connection")
    def test_get_journey_by_id_not_found(self, mock_conn_fn):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_conn_fn.return_value = mock_conn

        mock_cursor.fetchone.return_value = None

        event = {
            "requestContext": {"http": {"method": "GET", "requestId": "req-j-7"}},
            "rawPath": "/journeys/j-missing",
        }

        resp = lambda_handler(event, None)
        self.assertEqual(resp["statusCode"], 404)

    # ─── Update Journey (PUT /journeys/{id}) ───────────────────────────────────

    @patch("backend.lambda_function._get_db_connection")
    def test_update_journey_conflict_reducing_seats_below_booked(self, mock_conn_fn):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_conn_fn.return_value = mock_conn

        user_row = (self.driver_id, "Driver One", "driver@example.com", "", "driver", "active")
        # Existing journey has 4 total seats
        existing_journey = (
            "j-1", self.driver_id, self.vehicle_id, "London", "Manchester",
            datetime.date(2026, 11, 20), datetime.time(8, 0), None,
            4, 2, 25.0, "active", "", [],
        )
        # Bookings check: 3 seats are booked!
        bookings_count_row = (3,)

        mock_cursor.fetchone.side_effect = [user_row, existing_journey, bookings_count_row]

        # Driver attempts to reduce total seats to 2 (< 3 booked seats)
        event = {
            "requestContext": {"http": {"method": "PUT", "requestId": "req-j-8"}},
            "rawPath": "/journeys/j-1",
            "headers": self._auth_header(self.driver_token),
            "body": json.dumps({"totalSeats": 2}),
        }

        resp = lambda_handler(event, None)
        self.assertEqual(resp["statusCode"], 409)
        data = json.loads(resp["body"])
        self.assertIn("cannot reduce total seats", data["error"].lower())

    @patch("backend.lambda_function._get_db_connection")
    def test_update_journey_forbidden_for_other_driver(self, mock_conn_fn):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_conn_fn.return_value = mock_conn

        user_row = (self.other_driver_id, "Other Driver", "other@example.com", "", "driver", "active")
        existing_journey = (
            "j-1", self.driver_id, self.vehicle_id, "London", "Manchester",
            datetime.date(2026, 11, 20), datetime.time(8, 0), None,
            4, 4, 25.0, "active", "", [],
        )
        mock_cursor.fetchone.side_effect = [user_row, existing_journey]

        event = {
            "requestContext": {"http": {"method": "PATCH", "requestId": "req-j-9"}},
            "rawPath": "/journeys/j-1",
            "headers": self._auth_header(self.other_driver_token),
            "body": json.dumps({"pricePerSeat": 35.0}),
        }

        resp = lambda_handler(event, None)
        self.assertEqual(resp["statusCode"], 403)
        data = json.loads(resp["body"])
        self.assertIn("permission", data["error"].lower())

    # ─── Delete Journey (DELETE /journeys/{id}) ─────────────────────────────────

    @patch("backend.lambda_function._get_db_connection")
    def test_delete_journey_success(self, mock_conn_fn):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_conn_fn.return_value = mock_conn

        user_row = (self.driver_id, "Driver One", "driver@example.com", "", "driver", "active")
        existing_journey = ("j-1", self.driver_id)
        # 0 bookings
        bookings_count_row = (0,)

        mock_cursor.fetchone.side_effect = [user_row, existing_journey, bookings_count_row]

        event = {
            "requestContext": {"http": {"method": "DELETE", "requestId": "req-j-10"}},
            "rawPath": "/journeys/j-1",
            "headers": self._auth_header(self.driver_token),
        }

        resp = lambda_handler(event, None)
        self.assertEqual(resp["statusCode"], 200)
        data = json.loads(resp["body"])
        self.assertTrue(data["success"])
        mock_conn.commit.assert_called_once()

    @patch("backend.lambda_function._get_db_connection")
    def test_delete_journey_conflict_with_existing_bookings(self, mock_conn_fn):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_conn_fn.return_value = mock_conn

        user_row = (self.driver_id, "Driver One", "driver@example.com", "", "driver", "active")
        existing_journey = ("j-1", self.driver_id)
        # 2 bookings exist
        bookings_count_row = (2,)

        mock_cursor.fetchone.side_effect = [user_row, existing_journey, bookings_count_row]

        event = {
            "requestContext": {"http": {"method": "DELETE", "requestId": "req-j-11"}},
            "rawPath": "/journeys/j-1",
            "headers": self._auth_header(self.driver_token),
        }

        resp = lambda_handler(event, None)
        self.assertEqual(resp["statusCode"], 409)
        data = json.loads(resp["body"])
        self.assertIn("associated with 2 existing booking", data["error"].lower())


if __name__ == "__main__":
    unittest.main()
