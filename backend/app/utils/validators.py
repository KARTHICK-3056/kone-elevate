"""Reusable validation bounds and helpers.

The numeric bounds here are the single source of truth for Pydantic schemas,
the synthetic-data generator and the seed script, so that a value accepted by
the API is always a value the ML pipeline can score.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Final

from app.utils.enums import ComponentType, Material

# --------------------------------------------------------------------------
# Physical bounds (prototype envelope)
# --------------------------------------------------------------------------
MIN_OPERATING_HOURS: Final[float] = 0.0
MAX_OPERATING_HOURS: Final[float] = 250_000.0

MIN_LOAD_CYCLES: Final[int] = 0
MAX_LOAD_CYCLES: Final[int] = 5_000_000

MIN_AVERAGE_LOAD: Final[float] = 0.0
MAX_AVERAGE_LOAD: Final[float] = 5_000.0  # kg

MIN_VIBRATION: Final[float] = 0.0
MAX_VIBRATION: Final[float] = 25.0  # mm/s RMS

MIN_TEMPERATURE: Final[float] = -40.0
MAX_TEMPERATURE: Final[float] = 150.0  # deg C

MIN_INSPECTION_SCORE: Final[float] = 0.0
MAX_INSPECTION_SCORE: Final[float] = 100.0

MIN_HEALTH_SCORE: Final[float] = 0.0
MAX_HEALTH_SCORE: Final[float] = 100.0

MIN_CONFIDENCE: Final[float] = 0.0
MAX_CONFIDENCE: Final[float] = 1.0

MIN_COMPONENT_AGE: Final[float] = 0.0
MAX_COMPONENT_AGE: Final[float] = 60.0  # years

MAX_SERVICE_COUNT: Final[int] = 200
MAX_REPAIR_COUNT: Final[int] = 60
MAX_FAILURE_HISTORY: Final[int] = 40
MAX_DAYS_SINCE_SERVICE: Final[int] = 4_000

#: Cap on a single service event's sensor_metadata dict - a flat bag for
#: variable readings, not a place to smuggle an unbounded document.
MAX_SENSOR_METADATA_KEYS: Final[int] = 20

EARLIEST_INSTALLATION_DATE: Final[date] = date(1960, 1, 1)


def validate_component_type(value: str) -> str:
    """Ensure the component type is one of the supported values."""
    if value not in ComponentType.values():
        raise ValueError(
            f"Unsupported component_type '{value}'. Expected one of: "
            + ", ".join(ComponentType.values())
        )
    return value


def validate_material(value: str) -> str:
    """Ensure the material is one of the supported values."""
    if value not in Material.values():
        raise ValueError(
            f"Unsupported material '{value}'. Expected one of: " + ", ".join(Material.values())
        )
    return value


def validate_material_grade(value: str | None) -> str | None:
    """Ensure a material grade, when given, is one the life model catalogues.

    Whether the grade fits the component's type and material is checked where
    both are known - ``app.ml.life_model.resolve_grade`` - so a partial update
    that changes only the grade is still accepted and the passport reports a
    mismatch rather than the request failing on a field it did not send.
    """
    if value is None or value == "":
        return None
    from app.ml.life_model import ALL_GRADES  # local import: avoids an ml <-> utils cycle

    if value not in ALL_GRADES:
        raise ValueError(
            f"Unsupported material_grade '{value}'. Expected one of: "
            + ", ".join(sorted(ALL_GRADES))
        )
    return value


def validate_installation_date(value: date | datetime | None) -> date | datetime | None:
    """Reject impossible installation dates (future or pre-1960)."""
    if value is None:
        return None
    as_date = value.date() if isinstance(value, datetime) else value
    if as_date > date.today():
        raise ValueError("installation_date cannot be in the future")
    if as_date < EARLIEST_INSTALLATION_DATE:
        raise ValueError("installation_date is implausibly old (before 1960)")
    return value


def validate_event_date(value: date | datetime | None) -> date | datetime | None:
    """Reject service events dated in the future."""
    if value is None:
        return None
    as_date = value.date() if isinstance(value, datetime) else value
    if as_date > date.today():
        raise ValueError("event_date cannot be in the future")
    return value
