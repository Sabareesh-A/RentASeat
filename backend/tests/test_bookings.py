#!/usr/bin/env python3
"""
Unit Test Suite for RentASeat Booking Management APIs
Covers booking validation, status transitions, reference generation, serialization,
and Lambda HTTP handlers:
  - POST   /bookings
  - GET    /bookings
  - GET    /bookings/{id}
  - PATCH  /bookings/{id}
  - POST   /bookings/{id}/cancel & DELETE /bookings/{id}

Tests verify:
  - Input validation (seats 1-10, statuses, notes <= 255 chars)
  - Booking reference generation (format, length, uppercase)
  - State machine transitions (safe transitions, terminal states)
  - Concurrency & locking (SELECT ... FOR UPDATE on journeys and bookings)
  - Overbooking prevention (insufficient seat counts return 409 Conflict)
  - Self-booking prevention (driver cannot book own journey: 403 Forbidden)
  - Past departure prevention (cannot book departed journeys: 400 Bad Request)
  - Duplicate booking prevention (passenger cannot double-book active journey: 409 Conflict)
  - Server-calculated pricing (total_price = seats * price_per_seat)
  - Exact-once seat restoration on cancellation
  - Strict ownership access control (passenger, driver, admin)
"""

import datetime
import json
import unittest
from unittest.mock import MagicMock, patch

from backend.auth import create_jwt_token
from backend.bookings import (
    ALLOWED_BOOKING_STATUSES,
    ALLOWED_PAYMENT_STATUSES,
    format_booking_row,
    generate_booking_reference,
    validate_booking_status,
    validate_create_booking_payload,
    validate_location_note,
    validate_payment_status,
    validate_seats_booked,
    validate_status_transition,
)
from backend.lambda_function import lambda_handler


class TestBookingValidation(unittest.TestCase):
    def test_validate_seats_booked(self):
        self.assertEqual(validate_seats_booked(1), 1)
        self.assertEqual(validate_seats_booked(5), 5)
        self.assertEqual(validate_seats_booked(10), 10)
        self.assertEqual(validate_seats_booked("3"), 3)
        invalid = [0, -1, 11, 20, "abc", None]
        for inv in invalid:
            with self.assertRaises(ValueError):
                validate_seats_booked(inv)

    def test_validate_booking_status(self):
        for s in ALLOWED_BOOKING_STATUSES:
            self.assertEqual(validate_booking_status(s), s)
            self.assertEqual(validate_booking_status(s.upper()), s)
        with self.assertRaises(ValueError):
            validate_booking_status("invalid_status")

    def test_validate_payment_status(self):
        for s in ALLOWED_PAYMENT_STATUSES:
            self.assertEqual(validate_payment_status(s), s)
            self.assertEqual(validate_payment_status(s.upper()), s)
        with self.assertRaises(ValueError):
            validate_payment_status("escrow")

    def test_validate_location_note(self):
        self.assertIsNone(validate_location_note(None))
        self.assertIsNone(validate_location_note(""))
        self.assertEqual(validate_location_note("  Gate 3 pickup  "), "Gate 3 pickup")
        with self.assertRaises(ValueError):
            validate_location_note("A" * 256)
        with self.assertRaises(ValueError):
            validate_location_note(12345)

    def test_validate_status_transition_valid(self):
        # Valid forward transitions
        validate_status_transition("pending", "confirmed")
        validate_status_transition("pending", "cancelled")
        validate_status_transition("confirmed", "completed")
        validate_status_transition("confirmed", "cancelled")
        validate_status_transition("confirmed", "confirmed")  # No-op

    def test_validate_status_transition_invalid(self):
        # Cancelled is terminal
        with self.assertRaises(ValueError):
            validate_status_transition("cancelled", "confirmed")
        with self.assertRaises(ValueError):
            validate_status_transition("cancelled", "pending")

        # Completed is terminal
        with self.assertRaises(ValueError):
            validate_status_transition("completed", "cancelled")
        with self.assertRaises(ValueError):
            validate_status_transition("completed", "confirmed")

        # Invalid jump
        with self.assertRaises(ValueError):
            validate_status_transition("pending", "completed")

    def test_generate_booking_reference(self):
        ref1 = generate_booking_reference()
        ref2 = generate_booking_reference()
        self.assertTrue(ref1.startswith("REN"))
        self.assertEqual(len(ref1), 10)
        self.assertEqual(ref1, ref1.upper())
        self.assertNotEqual(ref1, ref2)

    def test_validate_create_booking_payload(self):
        valid_payload = {
            "journeyId": "j-12345",
            "seatsBooked": 2,
            "pickupLocation": "Central Station",
            "dropoffLocation": "Airport Terminal 2",
        }
        res = validate_create_booking_payload(valid_payload)
        self.assertEqual(res["journey_id"], "j-12345")
        self.assertEqual(res["seats_booked"], 2)
        self.assertEqual(res["pickup_location"], "Central Station")
        self.assertEqual(res["dropoff_location"], "Airport Terminal 2")

        with self.assertRaises(ValueError):
            validate_create_booking_payload({})  # Missing journeyId
        with self.assertRaises(ValueError):
            validate_create_booking_payload({"journeyId": "j-1", "seatsBooked": 0})

    def test_format_booking_row(self):
        now = datetime.datetime(2026, 10, 23, 10, 0, 0, tzinfo=datetime.timezone.utc)
        dep_date = datetime.date(2026, 11, 20)
        dep_time = datetime.time(9, 30)
        arr_time = datetime.time(13, 0)

        # 45 columns
        row = (
            "b-100",  # 0: b.id
            "REN8K4M9Q2",  # 1: b.booking_reference
            "j-200",  # 2: b.journey_id
            "pass-1",  # 3: b.passenger_id
            2,  # 4: b.seats_booked
            50.00,  # 5: b.total_price
            "confirmed",  # 6: b.status
            "unpaid",  # 7: b.payment_status
            "Pickup note",  # 8: b.pickup_location
            "Dropoff note",  # 9: b.dropoff_location
            now,  # 10: b.created_at
            now,  # 11: b.updated_at
            "Alice Passenger",  # 12: u_pass.name
            "alice@example.com",  # 13: u_pass.email
            "+44-7700-111222",  # 14: u_pass.phone
            "passenger",  # 15: u_pass.role
            "",  # 16: u_pass.avatar_url
            5.0,  # 17: u_pass.rating
            3,  # 18: u_pass.review_count
            "London",  # 19: j.origin
            "Manchester",  # 20: j.destination
            dep_date,  # 21: j.departure_date
            dep_time,  # 22: j.departure_time
            arr_time,  # 23: j.arrival_time
            4,  # 24: j.total_seats
            2,  # 25: j.available_seats
            25.00,  # 26: j.price_per_seat
            "active",  # 27: j.status
            "Highway trip",  # 28: j.description
            ["Birmingham"],  # 29: j.stops
            "driver-1",  # 30: j.driver_id
            "Bob Driver",  # 31: u_driv.name
            "bob@example.com",  # 32: u_driv.email
            "+44-7700-333444",  # 33: u_driv.phone
            "driver",  # 34: u_driv.role
            "",  # 35: u_driv.avatar_url
            4.9,  # 36: u_driv.rating
            12,  # 37: u_driv.review_count
            "veh-1",  # 38: j.vehicle_id
            "AB12 CDE",  # 39: v.registration_number
            "sedan",  # 40: v.vehicle_type
            "Toyota Camry",  # 41: v.model
            "Blue",  # 42: v.colour
            4,  # 43: v.seating_capacity
            "",  # 44: v.image_url
        )

        formatted = format_booking_row(row)
        self.assertEqual(formatted["id"], "b-100")
        self.assertEqual(formatted["bookingReference"], "REN8K4M9Q2")
        self.assertEqual(formatted["journeyId"], "j-200")
        self.assertEqual(formatted["passengerId"], "pass-1")
        self.assertEqual(formatted["seatsBooked"], 2)
        self.assertEqual(formatted["totalPrice"], 50.0)
        self.assertEqual(formatted["status"], "confirmed")
        self.assertEqual(formatted["paymentStatus"], "unpaid")
        self.assertEqual(formatted["pickupLocation"], "Pickup note")
        self.assertEqual(formatted["dropoffLocation"], "Dropoff note")
        self.assertEqual(formatted["passenger"]["name"], "Alice Passenger")
        self.assertEqual(formatted["journey"]["from"], "London")
        self.assertEqual(formatted["journey"]["to"], "Manchester")
        self.assertEqual(formatted["journey"]["driver"]["name"], "Bob Driver")
        self.assertEqual(formatted["journey"]["vehicle"]["registrationNumber"], "AB12 CDE")


class TestBookingApiHandlers(unittest.TestCase):
    def setUp(self):
        self.now = datetime.datetime(2026, 10, 23, 10, 0, 0, tzinfo=datetime.timezone.utc)
        self.future_date = datetime.date(2026, 11, 20)
        self.past_date = datetime.date(2026, 9, 1)
        self.dep_time = datetime.time(9, 30)
        self.arr_time = datetime.time(13, 0)

        self.passenger_token = create_jwt_token("pass-uuid-1", "passenger", "alice@example.com")
        self.driver_token = create_jwt_token("driver-uuid-1", "driver", "bob@example.com")
        self.admin_token = create_jwt_token("admin-uuid-1", "admin", "admin@example.com")
        self.stranger_token = create_jwt_token("stranger-uuid-9", "passenger", "stranger@example.com")

    def _sample_45_col_booking_row(
        self,
        b_id="b-100",
        ref="REN8K4M9Q2",
        j_id="j-200",
        p_id="pass-uuid-1",
        seats=2,
        price=50.00,
        status="confirmed",
        d_id="driver-uuid-1",
    ):
        return (
            b_id,
            ref,
            j_id,
            p_id,
            seats,
            price,
            status,
            "unpaid",
            "Pickup note",
            "Dropoff note",
            self.now,
            self.now,
            "Alice Passenger",
            "alice@example.com",
            "+44-7700-111222",
            "passenger",
            "",
            5.0,
            3,
            "London",
            "Manchester",
            self.future_date,
            self.dep_time,
            self.arr_time,
            4,
            2,
            25.00,
            "active",
            "Highway trip",
            ["Birmingham"],
            d_id,
            "Bob Driver",
            "bob@example.com",
            "+44-7700-333444",
            "driver",
            "",
            4.9,
            12,
            "veh-1",
            "AB12 CDE",
            "sedan",
            "Toyota Camry",
            "Blue",
            4,
            "",
        )

    # ─── POST /bookings Tests ───────────────────────────────────────────────

    def test_create_booking_unauthorized(self):
        event = {
            "rawPath": "/bookings",
            "requestContext": {"http": {"method": "POST"}},
            "body": json.dumps({"journeyId": "j-100", "seatsBooked": 1}),
        }
        res = lambda_handler(event, None)
        self.assertEqual(res["statusCode"], 401)

    def test_create_booking_missing_fields(self):
        event = {
            "rawPath": "/bookings",
            "headers": {"authorization": f"Bearer {self.passenger_token}"},
            "requestContext": {"http": {"method": "POST"}},
            "body": json.dumps({"seatsBooked": 0}),
        }
        res = lambda_handler(event, None)
        self.assertEqual(res["statusCode"], 400)

    @patch("backend.lambda_function._get_db_connection")
    def test_create_booking_journey_not_found(self, mock_get_conn):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor

        # Mock authenticated user
        mock_cursor.fetchone.side_effect = [
            ("pass-uuid-1", "Alice", "alice@example.com", "+44", "passenger", "active"),  # user lookup
            None,  # Journey lookup returns None
        ]

        event = {
            "rawPath": "/bookings",
            "headers": {"authorization": f"Bearer {self.passenger_token}"},
            "requestContext": {"http": {"method": "POST"}},
            "body": json.dumps({"journeyId": "non-existent-j", "seatsBooked": 1}),
        }
        res = lambda_handler(event, None)
        self.assertEqual(res["statusCode"], 404)
        body = json.loads(res["body"])
        self.assertIn("not found", body["error"].lower())

    @patch("backend.lambda_function._get_db_connection")
    def test_create_booking_driver_cannot_book_own_journey(self, mock_get_conn):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor

        # Driver attempts to book their own journey
        mock_cursor.fetchone.side_effect = [
            ("driver-uuid-1", "Bob Driver", "bob@example.com", "+44", "driver", "active"),  # user lookup
            (
                "j-100",
                "driver-uuid-1",  # driver_id equals requester id!
                "veh-1",
                "London",
                "Manchester",
                self.future_date,
                self.dep_time,
                self.arr_time,
                4,
                4,
                25.0,
                "active",
            ),
        ]

        event = {
            "rawPath": "/bookings",
            "headers": {"authorization": f"Bearer {self.driver_token}"},
            "requestContext": {"http": {"method": "POST"}},
            "body": json.dumps({"journeyId": "j-100", "seatsBooked": 1}),
        }
        res = lambda_handler(event, None)
        self.assertEqual(res["statusCode"], 403)
        body = json.loads(res["body"])
        self.assertIn("Driver cannot book seats on their own journey", body["error"])

    @patch("backend.lambda_function._get_db_connection")
    def test_create_booking_past_journey_rejected(self, mock_get_conn):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor

        mock_cursor.fetchone.side_effect = [
            ("pass-uuid-1", "Alice", "alice@example.com", "+44", "passenger", "active"),
            (
                "j-100",
                "driver-uuid-1",
                "veh-1",
                "London",
                "Manchester",
                self.past_date,  # Past departure date!
                self.dep_time,
                self.arr_time,
                4,
                4,
                25.0,
                "active",
            ),
        ]

        event = {
            "rawPath": "/bookings",
            "headers": {"authorization": f"Bearer {self.passenger_token}"},
            "requestContext": {"http": {"method": "POST"}},
            "body": json.dumps({"journeyId": "j-100", "seatsBooked": 1}),
        }
        res = lambda_handler(event, None)
        self.assertEqual(res["statusCode"], 400)
        body = json.loads(res["body"])
        self.assertIn("already passed", body["error"])

    @patch("backend.lambda_function._get_db_connection")
    def test_create_booking_insufficient_seats_returns_409(self, mock_get_conn):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor

        mock_cursor.fetchone.side_effect = [
            ("pass-uuid-1", "Alice", "alice@example.com", "+44", "passenger", "active"),
            (
                "j-100",
                "driver-uuid-1",
                "veh-1",
                "London",
                "Manchester",
                self.future_date,
                self.dep_time,
                self.arr_time,
                4,
                1,  # Only 1 seat available!
                25.0,
                "active",
            ),
        ]

        event = {
            "rawPath": "/bookings",
            "headers": {"authorization": f"Bearer {self.passenger_token}"},
            "requestContext": {"http": {"method": "POST"}},
            "body": json.dumps({"journeyId": "j-100", "seatsBooked": 2}),  # Requests 2 seats
        }
        res = lambda_handler(event, None)
        self.assertEqual(res["statusCode"], 409)
        body = json.loads(res["body"])
        self.assertIn("Not enough seats available", body["error"])

    @patch("backend.lambda_function._get_db_connection")
    def test_create_booking_duplicate_active_booking_rejected(self, mock_get_conn):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor

        mock_cursor.fetchone.side_effect = [
            ("pass-uuid-1", "Alice", "alice@example.com", "+44", "passenger", "active"),
            (
                "j-100",
                "driver-uuid-1",
                "veh-1",
                "London",
                "Manchester",
                self.future_date,
                self.dep_time,
                self.arr_time,
                4,
                4,
                25.0,
                "active",
            ),
            ("existing-b-1",),  # Duplicate check returns an existing active booking!
        ]

        event = {
            "rawPath": "/bookings",
            "headers": {"authorization": f"Bearer {self.passenger_token}"},
            "requestContext": {"http": {"method": "POST"}},
            "body": json.dumps({"journeyId": "j-100", "seatsBooked": 1}),
        }
        res = lambda_handler(event, None)
        self.assertEqual(res["statusCode"], 409)
        body = json.loads(res["body"])
        self.assertIn("already have an active booking", body["error"])

    @patch("backend.lambda_function._get_db_connection")
    def test_create_booking_success_calculates_price_and_locks_row(self, mock_get_conn):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor

        sample_joined = self._sample_45_col_booking_row(
            b_id="b-new-123",
            j_id="j-100",
            p_id="pass-uuid-1",
            seats=2,
            price=50.00,
        )

        mock_cursor.fetchone.side_effect = [
            ("pass-uuid-1", "Alice", "alice@example.com", "+44", "passenger", "active"),  # user lookup
            (
                "j-100",
                "driver-uuid-1",
                "veh-1",
                "London",
                "Manchester",
                self.future_date,
                self.dep_time,
                self.arr_time,
                4,
                4,  # available_seats
                25.0,  # price_per_seat
                "active",
            ),
            None,  # No duplicate booking
            ("b-new-123",),  # RETURNING id
            sample_joined,  # Full joined query
        ]

        event = {
            "rawPath": "/bookings",
            "headers": {"authorization": f"Bearer {self.passenger_token}"},
            "requestContext": {"http": {"method": "POST"}},
            "body": json.dumps({
                "journeyId": "j-100",
                "seatsBooked": 2,
                "pickupLocation": "King's Cross",
                "dropoffLocation": "Piccadilly",
            }),
        }
        res = lambda_handler(event, None)
        self.assertEqual(res["statusCode"], 201)
        body = json.loads(res["body"])
        self.assertTrue(body["success"])
        self.assertEqual(body["booking"]["id"], "b-new-123")
        self.assertEqual(body["booking"]["totalPrice"], 50.0)
        self.assertEqual(body["booking"]["status"], "confirmed")
        self.assertEqual(body["booking"]["paymentStatus"], "unpaid")
        self.assertIn("unpaid", body["message"])

        # Verify SELECT ... FOR UPDATE was executed to lock the journey row
        select_calls = [
            str(call[0][0])
            for call in mock_cursor.execute.call_args_list
            if "SELECT" in str(call[0][0]) and "journeys" in str(call[0][0])
        ]
        self.assertTrue(any("FOR UPDATE" in call for call in select_calls))

        # Verify available_seats was decremented
        update_calls = [
            str(call[0][0])
            for call in mock_cursor.execute.call_args_list
            if "UPDATE journeys" in str(call[0][0])
        ]
        self.assertTrue(any("available_seats = available_seats - %s" in call for call in update_calls))

        # Verify transaction commit
        mock_conn.commit.assert_called()

    # ─── GET /bookings Tests ────────────────────────────────────────────────

    @patch("backend.lambda_function._get_db_connection")
    def test_list_bookings_passenger_scoping(self, mock_get_conn):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor

        mock_cursor.fetchone.return_value = (
            "pass-uuid-1",
            "Alice",
            "alice@example.com",
            "+44",
            "passenger",
            "active",
        )
        sample_row = self._sample_45_col_booking_row()
        mock_cursor.fetchall.return_value = [sample_row]

        event = {
            "rawPath": "/bookings",
            "headers": {"authorization": f"Bearer {self.passenger_token}"},
            "requestContext": {"http": {"method": "GET"}},
        }
        res = lambda_handler(event, None)
        self.assertEqual(res["statusCode"], 200)
        body = json.loads(res["body"])
        self.assertEqual(body["count"], 1)

        # Confirm WHERE clause enforces b.passenger_id = %s
        list_query = mock_cursor.execute.call_args[0][0]
        params = mock_cursor.execute.call_args[0][1]
        self.assertIn("b.passenger_id = %s", list_query)
        self.assertIn("pass-uuid-1", params)

    @patch("backend.lambda_function._get_db_connection")
    def test_list_bookings_driver_scoping(self, mock_get_conn):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor

        mock_cursor.fetchone.return_value = (
            "driver-uuid-1",
            "Bob",
            "bob@example.com",
            "+44",
            "driver",
            "active",
        )
        sample_row = self._sample_45_col_booking_row()
        mock_cursor.fetchall.return_value = [sample_row]

        event = {
            "rawPath": "/bookings",
            "headers": {"authorization": f"Bearer {self.driver_token}"},
            "queryStringParameters": {"as": "driver"},
            "requestContext": {"http": {"method": "GET"}},
        }
        res = lambda_handler(event, None)
        self.assertEqual(res["statusCode"], 200)

        list_query = mock_cursor.execute.call_args[0][0]
        params = mock_cursor.execute.call_args[0][1]
        self.assertIn("j.driver_id = %s", list_query)
        self.assertIn("driver-uuid-1", params)

    # ─── GET /bookings/{id} Tests ───────────────────────────────────────────

    @patch("backend.lambda_function._get_db_connection")
    def test_get_booking_by_id_passenger_allowed(self, mock_get_conn):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor

        mock_cursor.fetchone.side_effect = [
            ("pass-uuid-1", "Alice", "alice@example.com", "+44", "passenger", "active"),
            self._sample_45_col_booking_row(b_id="b-100", p_id="pass-uuid-1"),
        ]

        event = {
            "rawPath": "/bookings/b-100",
            "headers": {"authorization": f"Bearer {self.passenger_token}"},
            "requestContext": {"http": {"method": "GET"}},
        }
        res = lambda_handler(event, None)
        self.assertEqual(res["statusCode"], 200)
        body = json.loads(res["body"])
        self.assertEqual(body["booking"]["id"], "b-100")

    @patch("backend.lambda_function._get_db_connection")
    def test_get_booking_by_id_unrelated_stranger_forbidden(self, mock_get_conn):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor

        mock_cursor.fetchone.side_effect = [
            ("stranger-uuid-9", "Stranger", "stranger@example.com", "+44", "passenger", "active"),
            self._sample_45_col_booking_row(b_id="b-100", p_id="pass-uuid-1", d_id="driver-uuid-1"),
        ]

        event = {
            "rawPath": "/bookings/b-100",
            "headers": {"authorization": f"Bearer {self.stranger_token}"},
            "requestContext": {"http": {"method": "GET"}},
        }
        res = lambda_handler(event, None)
        self.assertEqual(res["statusCode"], 403)
        body = json.loads(res["body"])
        self.assertIn("do not have permission", body["error"])

    # ─── POST /bookings/{id}/cancel Tests ───────────────────────────────────

    @patch("backend.lambda_function._get_db_connection")
    def test_cancel_booking_releases_seats_and_updates_status(self, mock_get_conn):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor

        mock_cursor.fetchone.side_effect = [
            ("pass-uuid-1", "Alice", "alice@example.com", "+44", "passenger", "active"),  # user lookup
            ("b-100", "j-200", "pass-uuid-1", 2, "confirmed", "driver-uuid-1"),  # booking row
            ("j-200", 4, 1),  # journey row (total_seats=4, available_seats=1)
            self._sample_45_col_booking_row(b_id="b-100", status="cancelled"),  # joined row
        ]

        event = {
            "rawPath": "/bookings/b-100/cancel",
            "headers": {"authorization": f"Bearer {self.passenger_token}"},
            "requestContext": {"http": {"method": "POST"}},
        }
        res = lambda_handler(event, None)
        self.assertEqual(res["statusCode"], 200)
        body = json.loads(res["body"])
        self.assertTrue(body["success"])
        self.assertIn("2 seat(s) released", body["message"])

        # Verify seat restoration query was called
        update_calls = [
            str(call[0][0])
            for call in mock_cursor.execute.call_args_list
            if "UPDATE journeys" in str(call[0][0])
        ]
        self.assertTrue(any("LEAST(total_seats, available_seats + %s)" in call for call in update_calls))

        # Verify booking status set to cancelled
        booking_update_calls = [
            str(call[0][0])
            for call in mock_cursor.execute.call_args_list
            if "UPDATE bookings" in str(call[0][0])
        ]
        self.assertTrue(any("status = 'cancelled'" in call for call in booking_update_calls))

        # Verify commit
        mock_conn.commit.assert_called()

    @patch("backend.lambda_function._get_db_connection")
    def test_cancel_booking_already_cancelled_returns_409(self, mock_get_conn):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor

        mock_cursor.fetchone.side_effect = [
            ("pass-uuid-1", "Alice", "alice@example.com", "+44", "passenger", "active"),
            ("b-100", "j-200", "pass-uuid-1", 2, "cancelled", "driver-uuid-1"),  # Already cancelled!
        ]

        event = {
            "rawPath": "/bookings/b-100/cancel",
            "headers": {"authorization": f"Bearer {self.passenger_token}"},
            "requestContext": {"http": {"method": "POST"}},
        }
        res = lambda_handler(event, None)
        self.assertEqual(res["statusCode"], 409)
        body = json.loads(res["body"])
        self.assertIn("already cancelled", body["error"].lower())

    @patch("backend.lambda_function._get_db_connection")
    def test_cancel_booking_via_delete_method(self, mock_get_conn):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor

        mock_cursor.fetchone.side_effect = [
            ("pass-uuid-1", "Alice", "alice@example.com", "+44", "passenger", "active"),
            ("b-100", "j-200", "pass-uuid-1", 2, "confirmed", "driver-uuid-1"),
            ("j-200", 4, 1),
            self._sample_45_col_booking_row(b_id="b-100", status="cancelled"),
        ]

        event = {
            "rawPath": "/bookings/b-100",
            "headers": {"authorization": f"Bearer {self.passenger_token}"},
            "requestContext": {"http": {"method": "DELETE"}},
        }
        res = lambda_handler(event, None)
        self.assertEqual(res["statusCode"], 200)
        body = json.loads(res["body"])
        self.assertTrue(body["success"])

    # ─── PATCH /bookings/{id} Tests ─────────────────────────────────────────

    @patch("backend.lambda_function._get_db_connection")
    def test_patch_booking_passenger_cannot_mark_completed(self, mock_get_conn):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor

        mock_cursor.fetchone.side_effect = [
            ("pass-uuid-1", "Alice", "alice@example.com", "+44", "passenger", "active"),
            (
                "b-100",
                "j-200",
                "pass-uuid-1",
                2,
                "confirmed",
                "unpaid",
                None,
                None,
                "driver-uuid-1",
            ),
        ]

        event = {
            "rawPath": "/bookings/b-100",
            "headers": {"authorization": f"Bearer {self.passenger_token}"},
            "requestContext": {"http": {"method": "PATCH"}},
            "body": json.dumps({"status": "completed"}),
        }
        res = lambda_handler(event, None)
        self.assertEqual(res["statusCode"], 403)
        body = json.loads(res["body"])
        self.assertIn("Passengers may only cancel bookings", body["error"])

    @patch("backend.lambda_function._get_db_connection")
    def test_patch_booking_driver_marks_completed(self, mock_get_conn):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor

        mock_cursor.fetchone.side_effect = [
            ("driver-uuid-1", "Bob", "bob@example.com", "+44", "driver", "active"),
            (
                "b-100",
                "j-200",
                "pass-uuid-1",
                2,
                "confirmed",
                "unpaid",
                None,
                None,
                "driver-uuid-1",
            ),
            self._sample_45_col_booking_row(b_id="b-100", status="completed"),
        ]

        event = {
            "rawPath": "/bookings/b-100",
            "headers": {"authorization": f"Bearer {self.driver_token}"},
            "requestContext": {"http": {"method": "PATCH"}},
            "body": json.dumps({"status": "completed"}),
        }
        res = lambda_handler(event, None)
        self.assertEqual(res["statusCode"], 200)
        body = json.loads(res["body"])
        self.assertTrue(body["success"])
        self.assertEqual(body["booking"]["status"], "completed")


if __name__ == "__main__":
    unittest.main()
