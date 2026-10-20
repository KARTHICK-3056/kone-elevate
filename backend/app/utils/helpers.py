"""Small, dependency-free helpers used across the backend."""

from __future__ import annotations

import random
import string
from datetime import date, datetime, timezone
from typing import Any, Dict, Iterable, Optional

_ID_ALPHABET = string.ascii_uppercase + string.digits


def utcnow() -> datetime:
    """Timezone-naive UTC timestamp (consistent across SQLite and PostgreSQL)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def new_component_id(component_type: str, sequence: Optional[int] = None) -> str:
    """Build a readable component identifier, e.g. ``KE-MOT-000123``.

    A random suffix is used when no explicit sequence number is supplied.
    """
    prefix = "".join(ch for ch in component_type.upper() if ch.isalpha())[:3] or "CMP"
    if sequence is None:
        suffix = "".join(random.choices(_ID_ALPHABET, k=6))
    else:
        suffix = f"{sequence:06d}"
    return f"KE-{prefix}-{suffix}"


def new_serial_number(component_type: str) -> str:
    """Build a plausible manufacturer serial number."""
    prefix = "".join(ch for ch in component_type.upper() if ch.isalpha())[:2] or "XX"
    return f"{prefix}{random.randint(10, 99)}-{''.join(random.choices(_ID_ALPHABET, k=8))}"


def new_qr_token() -> str:
    """Opaque token embedded in a passport QR payload."""
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=24))


def _as_datetime(moment: date | datetime) -> datetime:
    """Widen a bare ``date`` to midnight ``datetime`` so subtraction works."""
    if isinstance(moment, date) and not isinstance(moment, datetime):
        return datetime.combine(moment, datetime.min.time())
    return moment


def years_between(start: Optional[date | datetime], end: Optional[date | datetime] = None) -> float:
    """Return the number of years between two dates, rounded to 2 decimals."""
    if start is None:
        return 0.0
    end = end or utcnow()
    delta_days = (_as_datetime(end) - _as_datetime(start)).days
    return round(max(delta_days, 0) / 365.25, 2)


def days_since(moment: Optional[date | datetime]) -> int:
    """Whole days elapsed since a date/datetime (0 when unknown)."""
    if moment is None:
        return 0
    return max((utcnow() - _as_datetime(moment)).days, 0)


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    """Constrain a value to the inclusive range [low, high]."""
    return max(low, min(high, value))


def percentage(part: float, whole: float, digits: int = 1) -> float:
    """Safe percentage helper that never divides by zero."""
    if not whole:
        return 0.0
    return round(100.0 * part / whole, digits)


def serialise(obj: Any, exclude: Iterable[str] = ()) -> Dict[str, Any]:
    """Convert an ORM instance into a JSON-friendly snapshot dictionary.

    Used by the audit service to store an immutable copy of each record.
    """
    exclude = set(exclude)
    data: Dict[str, Any] = {}
    for column in obj.__table__.columns:  # type: ignore[attr-defined]
        if column.name in exclude:
            continue
        value = getattr(obj, column.name)
        if isinstance(value, (datetime, date)):
            value = value.isoformat()
        data[column.name] = value
    return data


def chunk(items: list, size: int) -> Iterable[list]:
    """Yield successive fixed-size chunks from a list."""
    for index in range(0, len(items), size):
        yield items[index : index + size]
