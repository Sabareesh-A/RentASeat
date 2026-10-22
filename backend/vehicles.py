"""
RentASeat Vehicle Validation and Serialization Utilities
Compatible with Python 3.13 and PostgreSQL schema constraints.

Validation rules match backend/migrations/001_initial_schema.sql:
  - vehicle_type in ('sedan', 'suv', 'hatchback', 'minivan', 'van')
  - seating_capacity between 1 and 20
  - model between 2 and 100 characters
  - registration_number between 2 and 30 characters (normalized to uppercase)
  - colour up to 50 characters (optional)
  - image_url up to 500 characters (optional)
"""

from typing import Any

ALLOWED_VEHICLE_TYPES = {"sedan", "suv", "hatchback", "minivan", "van"}


def validate_vehicle_type(vehicle_type: Any) -> str:
    """
    Validate vehicle type against allowed types.
    Normalizes to lowercase trimmed string.
    """
    if not vehicle_type or not isinstance(vehicle_type, str):
        raise ValueError(
            "Vehicle type is required. Allowed types: sedan, suv, hatchback, minivan, van."
        )
    cleaned = vehicle_type.strip().lower()
    if cleaned not in ALLOWED_VEHICLE_TYPES:
        raise ValueError(
            f"Invalid vehicle type '{vehicle_type}'. Allowed types: sedan, suv, hatchback, minivan, van."
        )
    return cleaned


def validate_registration_number(registration_number: Any) -> str:
    """
    Validate and normalize vehicle registration number.
    Enforces uppercase and length 2 to 30 characters.
    """
    if not registration_number or not isinstance(registration_number, str):
        raise ValueError("Registration number is required.")
    cleaned = registration_number.strip().upper()
    if len(cleaned) < 2:
        raise ValueError("Registration number must be at least 2 characters long.")
    if len(cleaned) > 30:
        raise ValueError("Registration number must not exceed 30 characters.")
    return cleaned


def validate_model(model: Any) -> str:
    """
    Validate vehicle make and model string.
    Enforces length 2 to 100 characters.
    """
    if not model or not isinstance(model, str):
        raise ValueError("Vehicle model is required.")
    cleaned = model.strip()
    if len(cleaned) < 2:
        raise ValueError("Vehicle model must be at least 2 characters long.")
    if len(cleaned) > 100:
        raise ValueError("Vehicle model must not exceed 100 characters.")
    return cleaned


def validate_seating_capacity(seating_capacity: Any) -> int:
    """
    Validate seating capacity.
    Enforces integer between 1 and 20.
    """
    if seating_capacity is None:
        raise ValueError("Seating capacity is required.")
    try:
        capacity = int(seating_capacity)
    except (ValueError, TypeError):
        raise ValueError("Seating capacity must be a valid integer.") from None

    if capacity < 1 or capacity > 20:
        raise ValueError("Seating capacity must be between 1 and 20.")
    return capacity


def validate_colour(colour: Any) -> str | None:
    """Validate optional vehicle colour string (max 50 chars)."""
    if colour is None or colour == "":
        return None
    if not isinstance(colour, str):
        raise ValueError("Vehicle colour must be a string.")
    cleaned = colour.strip()
    if len(cleaned) > 50:
        raise ValueError("Vehicle colour must not exceed 50 characters.")
    return cleaned or None


def validate_image_url(image_url: Any) -> str | None:
    """Validate optional vehicle image URL (max 500 chars)."""
    if image_url is None or image_url == "":
        return None
    if not isinstance(image_url, str):
        raise ValueError("Vehicle image URL must be a string.")
    cleaned = image_url.strip()
    if len(cleaned) > 500:
        raise ValueError("Vehicle image URL must not exceed 500 characters.")
    return cleaned or None


def validate_vehicle_payload(data: dict, is_update: bool = False) -> dict[str, Any]:
    """
    Validate incoming vehicle registration or update payload.
    Supports both camelCase and snake_case keys from frontend.
    If is_update is True, fields are optional unless provided.
    """
    result: dict[str, Any] = {}

    # Registration number
    reg_val = data.get("registrationNumber") or data.get("registration_number")
    if reg_val is not None or not is_update:
        result["registration_number"] = validate_registration_number(reg_val)

    # Vehicle type
    type_val = data.get("vehicleType") or data.get("vehicle_type")
    if type_val is not None or not is_update:
        result["vehicle_type"] = validate_vehicle_type(type_val)

    # Model
    model_val = data.get("model")
    if model_val is not None or not is_update:
        result["model"] = validate_model(model_val)

    # Seating capacity
    cap_val = data.get("seatingCapacity") if "seatingCapacity" in data else data.get("seating_capacity")
    if cap_val is not None or not is_update:
        result["seating_capacity"] = validate_seating_capacity(cap_val)

    # Colour (optional)
    if "colour" in data or "color" in data:
        col_val = data.get("colour") if "colour" in data else data.get("color")
        result["colour"] = validate_colour(col_val)
    elif not is_update:
        result["colour"] = None

    # Image URL (optional)
    img_val = data.get("imageUrl") or data.get("image_url") or data.get("image")
    if img_val is not None or ("imageUrl" in data or "image_url" in data or "image" in data):
        result["image_url"] = validate_image_url(img_val)
    elif not is_update:
        result["image_url"] = None

    return result


def format_vehicle_row(row: tuple | list) -> dict[str, Any]:
    """
    Format a database row tuple from vehicles table into a JSON-friendly dict.
    Expected row columns:
      0: id (UUID or str)
      1: driver_id (UUID or str)
      2: registration_number (str)
      3: vehicle_type (str)
      4: model (str)
      5: colour (str or None)
      6: seating_capacity (int)
      7: image_url (str or None)
      8: created_at (datetime)
      9: updated_at (datetime)
    """
    created_at = row[8]
    updated_at = row[9]

    created_iso = created_at.isoformat() if hasattr(created_at, "isoformat") else str(created_at)
    updated_iso = updated_at.isoformat() if hasattr(updated_at, "isoformat") else str(updated_at)

    return {
        "id": str(row[0]),
        "driverId": str(row[1]),
        "registrationNumber": str(row[2]),
        "vehicleType": str(row[3]),
        "model": str(row[4]),
        "colour": row[5] or "",
        "seatingCapacity": int(row[6]),
        "imageUrl": row[7] or "",
        "createdAt": created_iso,
        "updatedAt": updated_iso,
    }
