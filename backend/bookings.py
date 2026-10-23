"""
RentASeat Booking Validation, Reference Generation, and Serialization Utilities
Compatible with Python 3.13 and PostgreSQL schema constraints.

Validation rules match backend/migrations/001_initial_schema.sql:
  - booking_reference: uppercase alphanumeric string, length >= 6 (e.g. REN7K9P2M4)
  - seats_booked: integer between 1 and 10
  - total_price: non-negative numeric (calculated server-side: seats_booked * price_per_seat)
  - status: 'pending', 'confirmed', 'cancelled', 'completed'
  - payment_status: 'unpaid', 'paid', 'refunded' (payment processing not yet implemented)
  - pickup_location, dropoff_location: optional strings up to 255 characters
"""

import datetime
import json
import secrets
import string
from typing import Any

ALLOWED_BOOKING_STATUSES = {"pending", "confirmed", "cancelled", "completed"}
ALLOWED_PAYMENT_STATUSES = {"unpaid", "paid", "refunded"}

# Allowed state machine transitions
ALLOWED_TRANSITIONS = {
    "pending": {"pending", "confirmed", "cancelled"},
    "confirmed": {"confirmed", "completed", "cancelled"},
    "cancelled": set(),  # Terminal state
    "completed": set(),  # Terminal state
}


def generate_booking_reference(prefix: str = "REN") -> str:
    """
    Generate a cryptographically secure, human-readable booking reference.
    Format: 3-char prefix + 7 uppercase alphanumeric characters (e.g., 'REN8K4M9Q2').
    Total length: 10 characters (satisfies length >= 6 and uppercase constraint).
    """
    # Exclude ambiguous characters (0, O, 1, I) to prevent passenger reading mistakes
    alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
    suffix = "".join(secrets.choice(alphabet) for _ in range(7))
    return f"{prefix}{suffix}"


def validate_seats_booked(seats_val: Any) -> int:
    """
    Validate seats_booked input.
    Must be an integer between 1 and 10 (enforced by chk_bookings_seats).
    """
    if seats_val is None:
        raise ValueError("Seats booked is required.")
    try:
        seats = int(seats_val)
    except (ValueError, TypeError):
        raise ValueError("Seats booked must be a valid integer.") from None

    if seats < 1 or seats > 10:
        raise ValueError("Seats booked must be between 1 and 10.")
    return seats


def validate_booking_status(status_val: Any) -> str:
    """Validate booking status against allowed values."""
    if not status_val or not isinstance(status_val, str):
        return "confirmed"
    cleaned = status_val.strip().lower()
    if cleaned not in ALLOWED_BOOKING_STATUSES:
        raise ValueError(
            f"Invalid booking status '{status_val}'. Allowed values: {', '.join(sorted(ALLOWED_BOOKING_STATUSES))}."
        )
    return cleaned


def validate_payment_status(payment_status_val: Any) -> str:
    """Validate payment status against allowed values."""
    if not payment_status_val or not isinstance(payment_status_val, str):
        return "unpaid"
    cleaned = payment_status_val.strip().lower()
    if cleaned not in ALLOWED_PAYMENT_STATUSES:
        raise ValueError(
            f"Invalid payment status '{payment_status_val}'. Allowed values: {', '.join(sorted(ALLOWED_PAYMENT_STATUSES))}."
        )
    return cleaned


def validate_location_note(note_val: Any, field_name: str = "Location") -> str | None:
    """Validate optional pickup or dropoff location note (max 255 characters)."""
    if note_val is None or note_val == "":
        return None
    if not isinstance(note_val, str):
        raise ValueError(f"{field_name} must be a string.")
    cleaned = note_val.strip()
    if len(cleaned) > 255:
        raise ValueError(f"{field_name} must not exceed 255 characters.")
    return cleaned if cleaned else None


def validate_status_transition(current_status: str, new_status: str) -> None:
    """
    Enforce explicitly defined status transitions for bookings.
    Terminal states ('cancelled', 'completed') cannot transition to any other status.
    """
    current_clean = current_status.strip().lower()
    new_clean = new_status.strip().lower()

    if current_clean == new_clean:
        return

    if current_clean == "cancelled":
        raise ValueError("Cannot modify a cancelled booking.")
    if current_clean == "completed":
        raise ValueError("Cannot modify a completed booking.")

    allowed_next = ALLOWED_TRANSITIONS.get(current_clean, set())
    if new_clean not in allowed_next:
        raise ValueError(
            f"Invalid status transition from '{current_clean}' to '{new_clean}'. "
            f"Allowed next states: {', '.join(sorted(allowed_next)) or 'none'}."
        )


def validate_create_booking_payload(data: dict) -> dict[str, Any]:
    """Validate incoming POST /bookings payload."""
    if not isinstance(data, dict):
        raise ValueError("Invalid request body. Expected JSON object.")

    journey_id = data.get("journeyId") or data.get("journey_id")
    if not journey_id or not isinstance(journey_id, str) or not journey_id.strip():
        raise ValueError("Journey ID is required.")

    seats_booked_raw = data.get("seatsBooked") or data.get("seats_booked") or data.get("seats")
    seats_booked = validate_seats_booked(seats_booked_raw)

    pickup_loc = validate_location_note(
        data.get("pickupLocation") or data.get("pickup_location"),
        "Pickup location",
    )
    dropoff_loc = validate_location_note(
        data.get("dropoffLocation") or data.get("dropoff_location"),
        "Dropoff location",
    )

    return {
        "journey_id": journey_id.strip(),
        "seats_booked": seats_booked,
        "pickup_location": pickup_loc,
        "dropoff_location": dropoff_loc,
    }


JOINED_BOOKING_SELECT = """
SELECT
    b.id, b.booking_reference, b.journey_id, b.passenger_id,
    b.seats_booked, b.total_price, b.status, b.payment_status,
    b.pickup_location, b.dropoff_location, b.created_at, b.updated_at,
    u_pass.name, u_pass.email, u_pass.phone, u_pass.role, u_pass.avatar_url, u_pass.rating, u_pass.review_count,
    j.origin, j.destination, j.departure_date, j.departure_time, j.arrival_time,
    j.total_seats, j.available_seats, j.price_per_seat, j.status, j.description, j.stops,
    j.driver_id, u_driv.name, u_driv.email, u_driv.phone, u_driv.role, u_driv.avatar_url, u_driv.rating, u_driv.review_count,
    j.vehicle_id, v.registration_number, v.vehicle_type, v.model, v.colour, v.seating_capacity, v.image_url
FROM bookings b
JOIN users u_pass ON b.passenger_id = u_pass.id
JOIN journeys j ON b.journey_id = j.id
JOIN users u_driv ON j.driver_id = u_driv.id
LEFT JOIN vehicles v ON j.vehicle_id = v.id
"""


def format_booking_row(row: tuple | list) -> dict[str, Any]:
    """
    Format a database row resulting from joining bookings, users (passenger),
    journeys, users (driver), and vehicles.

    Expected columns (45):
      0: b.id
      1: b.booking_reference
      2: b.journey_id
      3: b.passenger_id
      4: b.seats_booked
      5: b.total_price
      6: b.status
      7: b.payment_status
      8: b.pickup_location
      9: b.dropoff_location
      10: b.created_at
      11: b.updated_at
      12: u_pass.name
      13: u_pass.email
      14: u_pass.phone
      15: u_pass.role
      16: u_pass.avatar_url
      17: u_pass.rating
      18: u_pass.review_count
      19: j.origin
      20: j.destination
      21: j.departure_date
      22: j.departure_time
      23: j.arrival_time
      24: j.total_seats
      25: j.available_seats
      26: j.price_per_seat
      27: j.status
      28: j.description
      29: j.stops
      30: j.driver_id
      31: u_driv.name
      32: u_driv.email
      33: u_driv.phone
      34: u_driv.role
      35: u_driv.avatar_url
      36: u_driv.rating
      37: u_driv.review_count
      38: j.vehicle_id
      39: v.registration_number
      40: v.vehicle_type
      41: v.model
      42: v.colour
      43: v.seating_capacity
      44: v.image_url
    """
    created_at = row[10]
    updated_at = row[11]
    created_iso = created_at.isoformat() if hasattr(created_at, "isoformat") else str(created_at)
    updated_iso = updated_at.isoformat() if hasattr(updated_at, "isoformat") else str(updated_at)

    # Passenger sub-object
    passenger_dict = {
        "id": str(row[3]),
        "name": str(row[12]),
        "email": str(row[13]),
        "phone": str(row[14] or ""),
        "role": str(row[15]),
        "avatar": str(row[16] or ""),
        "rating": float(row[17]) if row[17] is not None else 5.0,
        "reviews": int(row[18]) if row[18] is not None else 0,
    }

    # Driver sub-object
    driver_dict = {
        "id": str(row[30]),
        "name": str(row[31]),
        "email": str(row[32]),
        "phone": str(row[33] or ""),
        "role": str(row[34]),
        "avatar": str(row[35] or ""),
        "rating": float(row[36]) if row[36] is not None else 5.0,
        "reviews": int(row[37]) if row[37] is not None else 0,
    }

    # Vehicle sub-object (if attached)
    vehicle_dict = None
    if row[38] is not None:
        vehicle_dict = {
            "id": str(row[38]),
            "driverId": str(row[30]),
            "registrationNumber": str(row[39] or ""),
            "vehicleType": str(row[40] or ""),
            "model": str(row[41] or ""),
            "colour": str(row[42] or ""),
            "seatingCapacity": int(row[43]) if row[43] is not None else 0,
            "imageUrl": str(row[44] or ""),
        }

    # Stops parsing
    stops_val = row[29]
    if isinstance(stops_val, list):
        stops_list = stops_val
    elif isinstance(stops_val, str) and stops_val:
        try:
            stops_list = json.loads(stops_val)
        except json.JSONDecodeError:
            stops_list = []
    else:
        stops_list = []

    dep_date_str = str(row[21])
    dep_time_str = str(row[22])[:5] if row[22] is not None else ""
    arr_time_str = str(row[23])[:5] if row[23] is not None else ""

    journey_dict = {
        "id": str(row[2]),
        "driverId": str(row[30]),
        "vehicleId": str(row[38]) if row[38] else None,
        "origin": str(row[19]),
        "from": str(row[19]),
        "destination": str(row[20]),
        "to": str(row[20]),
        "date": dep_date_str,
        "departureDate": dep_date_str,
        "departureTime": dep_time_str,
        "arrivalTime": arr_time_str,
        "totalSeats": int(row[24]),
        "availableSeats": int(row[25]),
        "pricePerSeat": float(row[26]),
        "status": str(row[27]),
        "description": str(row[28] or ""),
        "stops": stops_list,
        "driver": driver_dict,
        "vehicle": vehicle_dict,
    }

    return {
        "id": str(row[0]),
        "bookingReference": str(row[1]),
        "journeyId": str(row[2]),
        "passengerId": str(row[3]),
        "seatsBooked": int(row[4]),
        "totalPrice": float(row[5]),
        "status": str(row[6]),
        "paymentStatus": str(row[7]),
        "pickupLocation": str(row[8]) if row[8] is not None else None,
        "dropoffLocation": str(row[9]) if row[9] is not None else None,
        "createdAt": created_iso,
        "updatedAt": updated_iso,
        "passenger": passenger_dict,
        "journey": journey_dict,
    }
