"""
RentASeat Journey Validation and Serialization Utilities
Compatible with Python 3.13 and PostgreSQL schema constraints.

Validation rules match backend/migrations/001_initial_schema.sql and 002_journey_vehicle_constraints.sql:
  - origin, destination: length 2 to 200 characters, trimmed, lower(origin) != lower(destination)
  - departure_date: YYYY-MM-DD format
  - departure_time: HH:MM or HH:MM:SS format
  - arrival_time: optional HH:MM or HH:MM:SS format
  - total_seats: integer between 1 and 20
  - available_seats: integer between 0 and total_seats
  - price_per_seat: positive numeric > 0
  - status: 'active', 'completed', 'cancelled'
  - description: optional text string
  - stops: list of string locations
  - vehicle_id: valid vehicle UUID
"""

import datetime
import json
import re
from typing import Any

ALLOWED_JOURNEY_STATUSES = {"active", "completed", "cancelled"}
DATE_REGEX = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TIME_REGEX = re.compile(r"^\d{2}:\d{2}(:\d{2})?$")


def validate_location(location: Any, field_name: str = "Location") -> str:
    """Validate origin or destination city string."""
    if not location or not isinstance(location, str):
        raise ValueError(f"{field_name} is required.")
    cleaned = location.strip()
    if len(cleaned) < 2:
        raise ValueError(f"{field_name} must be at least 2 characters long.")
    if len(cleaned) > 200:
        raise ValueError(f"{field_name} must not exceed 200 characters.")
    return cleaned


def validate_endpoints(origin: str, destination: str) -> None:
    """Ensure origin and destination endpoints are different."""
    if origin.strip().lower() == destination.strip().lower():
        raise ValueError("Origin and destination must be different.")


def validate_departure_date(date_val: Any) -> str:
    """Validate departure date in YYYY-MM-DD format."""
    if not date_val or not isinstance(date_val, str):
        raise ValueError("Departure date is required in YYYY-MM-DD format.")
    cleaned = date_val.strip()
    if not DATE_REGEX.match(cleaned):
        raise ValueError("Invalid date format. Expected YYYY-MM-DD.")
    try:
        datetime.date.fromisoformat(cleaned)
    except ValueError:
        raise ValueError("Invalid calendar date.") from None
    return cleaned


def validate_time(time_val: Any, field_name: str = "Time") -> str:
    """Validate time string in HH:MM or HH:MM:SS format."""
    if not time_val or not isinstance(time_val, str):
        raise ValueError(f"{field_name} is required in HH:MM format.")
    cleaned = time_val.strip()
    if not TIME_REGEX.match(cleaned):
        raise ValueError(f"Invalid {field_name.lower()} format. Expected HH:MM or HH:MM:SS.")
    try:
        parts = [int(p) for p in cleaned.split(":")]
        if len(parts) == 2:
            datetime.time(hour=parts[0], minute=parts[1])
        elif len(parts) == 3:
            datetime.time(hour=parts[0], minute=parts[1], second=parts[2])
    except ValueError:
        raise ValueError(f"Invalid time values in {field_name.lower()}.") from None
    return cleaned


def validate_price(price_val: Any) -> float:
    """Validate price per seat (must be positive number)."""
    if price_val is None:
        raise ValueError("Price per seat is required.")
    try:
        price = float(price_val)
    except (ValueError, TypeError):
        raise ValueError("Price per seat must be a valid number.") from None

    if price <= 0:
        raise ValueError("Price per seat must be greater than zero.")
    if price > 100000:
        raise ValueError("Price per seat exceeds maximum allowable amount.")
    return round(price, 2)


def validate_seats(seats_val: Any, field_name: str = "Seats") -> int:
    """Validate seat count (integer 1 to 20)."""
    if seats_val is None:
        raise ValueError(f"{field_name} is required.")
    try:
        seats = int(seats_val)
    except (ValueError, TypeError):
        raise ValueError(f"{field_name} must be a valid integer.") from None

    if seats < 1 or seats > 20:
        raise ValueError(f"{field_name} must be between 1 and 20.")
    return seats


def validate_status(status_val: Any) -> str:
    """Validate journey status."""
    if not status_val or not isinstance(status_val, str):
        return "active"
    cleaned = status_val.strip().lower()
    if cleaned not in ALLOWED_JOURNEY_STATUSES:
        raise ValueError(
            f"Invalid journey status '{status_val}'. Allowed values: active, completed, cancelled."
        )
    return cleaned


def validate_stops(stops_val: Any) -> list[str]:
    """Validate intermediate stops list."""
    if stops_val is None or stops_val == "":
        return []
    if isinstance(stops_val, str):
        try:
            parsed = json.loads(stops_val)
            if isinstance(parsed, list):
                stops_val = parsed
            else:
                stops_val = [s.strip() for s in stops_val.split(",") if s.strip()]
        except json.JSONDecodeError:
            stops_val = [s.strip() for s in stops_val.split(",") if s.strip()]

    if not isinstance(stops_val, list):
        raise ValueError("Stops must be a list of location strings.")

    cleaned_stops: list[str] = []
    for stop in stops_val:
        if isinstance(stop, str) and stop.strip():
            cleaned_stops.append(stop.strip()[:200])
    return cleaned_stops


def validate_journey_payload(data: dict, is_update: bool = False) -> dict[str, Any]:
    """
    Validate incoming journey creation or update payload.
    Supports both frontend keys (from, to, date) and DB keys (origin, destination, departureDate).
    """
    result: dict[str, Any] = {}

    # Origin / From
    origin_val = data.get("origin") or data.get("from")
    if origin_val is not None or not is_update:
        result["origin"] = validate_location(origin_val, "Origin (from)")

    # Destination / To
    dest_val = data.get("destination") or data.get("to")
    if dest_val is not None or not is_update:
        result["destination"] = validate_location(dest_val, "Destination (to)")

    # Check distinct endpoints if both present
    if "origin" in result and "destination" in result:
        validate_endpoints(result["origin"], result["destination"])

    # Departure Date
    date_val = data.get("departureDate") or data.get("departure_date") or data.get("date")
    if date_val is not None or not is_update:
        result["departure_date"] = validate_departure_date(date_val)

    # Departure Time
    dep_time_val = data.get("departureTime") or data.get("departure_time")
    if dep_time_val is not None or not is_update:
        result["departure_time"] = validate_time(dep_time_val, "Departure time")

    # Arrival Time (optional)
    arr_time_val = data.get("arrivalTime") or data.get("arrival_time")
    if arr_time_val is not None or not is_update:
        if arr_time_val:
            result["arrival_time"] = validate_time(arr_time_val, "Arrival time")
        else:
            result["arrival_time"] = None

    # Total Seats
    seats_val = data.get("totalSeats") or data.get("total_seats") or data.get("availableSeats") or data.get("available_seats")
    if seats_val is not None or not is_update:
        result["total_seats"] = validate_seats(seats_val, "Total seats")

    # Price Per Seat
    price_val = data.get("pricePerSeat") or data.get("price_per_seat") or data.get("price")
    if price_val is not None or not is_update:
        result["price_per_seat"] = validate_price(price_val)

    # Vehicle ID
    veh_val = data.get("vehicleId") or data.get("vehicle_id")
    if veh_val is not None or not is_update:
        if not veh_val or not isinstance(veh_val, str) or len(veh_val.strip()) < 1:
            raise ValueError("Vehicle ID is required.")
        result["vehicle_id"] = veh_val.strip()

    # Status
    if "status" in data:
        result["status"] = validate_status(data["status"])
    elif not is_update:
        result["status"] = "active"

    # Description (optional)
    if "description" in data:
        desc = data.get("description")
        result["description"] = desc.strip() if isinstance(desc, str) else ""
    elif not is_update:
        result["description"] = ""

    # Stops (optional)
    if "stops" in data:
        result["stops"] = validate_stops(data["stops"])
    elif not is_update:
        result["stops"] = []

    return result


def format_journey_row(row: tuple | list) -> dict[str, Any]:
    """
    Format a database row resulting from joining journeys, users, and vehicles.
    Expected columns:
      0: j.id
      1: j.driver_id
      2: j.vehicle_id
      3: j.origin
      4: j.destination
      5: j.departure_date
      6: j.departure_time
      7: j.arrival_time
      8: j.total_seats
      9: j.available_seats
      10: j.price_per_seat
      11: j.status
      12: j.description
      13: j.stops
      14: j.created_at
      15: j.updated_at
      16: u.name (driver)
      17: u.email (driver)
      18: u.phone (driver)
      19: u.role (driver)
      20: u.avatar_url (driver)
      21: u.rating (driver)
      22: u.review_count (driver)
      23: v.registration_number (vehicle)
      24: v.vehicle_type (vehicle)
      25: v.model (vehicle)
      26: v.colour (vehicle)
      27: v.seating_capacity (vehicle)
      28: v.image_url (vehicle)
    """
    # Timestamps & date/time formatting
    dep_date_str = str(row[5])
    dep_time_str = str(row[6])[:5] if row[6] is not None else ""
    arr_time_str = str(row[7])[:5] if row[7] is not None else ""

    created_at = row[14]
    updated_at = row[15]
    created_iso = created_at.isoformat() if hasattr(created_at, "isoformat") else str(created_at)
    updated_iso = updated_at.isoformat() if hasattr(updated_at, "isoformat") else str(updated_at)

    # Stops parsing
    stops_val = row[13]
    if isinstance(stops_val, list):
        stops_list = stops_val
    elif isinstance(stops_val, str) and stops_val:
        try:
            stops_list = json.loads(stops_val)
        except json.JSONDecodeError:
            stops_list = []
    else:
        stops_list = []

    # Driver profile
    driver_dict = {
        "id": str(row[1]),
        "name": str(row[16]),
        "email": str(row[17]),
        "phone": str(row[18] or ""),
        "role": str(row[19]),
        "avatar": str(row[20] or ""),
        "rating": float(row[21]) if row[21] is not None else 5.0,
        "reviews": int(row[22]) if row[22] is not None else 0,
    }

    # Vehicle profile
    vehicle_dict = {
        "id": str(row[2]),
        "driverId": str(row[1]),
        "registrationNumber": str(row[23]),
        "vehicleType": str(row[24]),
        "model": str(row[25]),
        "colour": str(row[26] or ""),
        "seatingCapacity": int(row[27]),
        "imageUrl": str(row[28] or ""),
    }

    return {
        "id": str(row[0]),
        "driverId": str(row[1]),
        "vehicleId": str(row[2]),
        "origin": str(row[3]),
        "from": str(row[3]),
        "destination": str(row[4]),
        "to": str(row[4]),
        "date": dep_date_str,
        "departureDate": dep_date_str,
        "departureTime": dep_time_str,
        "arrivalTime": arr_time_str,
        "totalSeats": int(row[8]),
        "availableSeats": int(row[9]),
        "pricePerSeat": float(row[10]),
        "status": str(row[11]),
        "description": str(row[12] or ""),
        "stops": stops_list,
        "createdAt": created_iso,
        "updatedAt": updated_iso,
        "driver": driver_dict,
        "vehicle": vehicle_dict,
    }
