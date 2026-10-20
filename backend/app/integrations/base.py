"""Interfaces and data shapes the rest of the app depends on.

Everything downstream of this module (the API layer, services) imports
these types and nothing else - never a fixture path, never an HTTP client,
never a KONE-specific response shape. That is the entire point of the
anti-corruption layer: the day a real adapter exists, it implements these
same three ``Protocol``s and nothing else in the codebase changes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import List, Optional, Protocol


@dataclass(frozen=True)
class EquipmentIdentity:
    """What "which physical equipment is this" resolves to.

    Field names are this build's own generic modelling of an elevator
    equipment record - not copied from KONE's real API Portal schema, which
    this build never had credentials to see.
    """

    equipment_id: str
    equipment_type: str
    site_name: str
    site_address: Optional[str]
    installation_date: Optional[date]
    status: str  # e.g. "IN_SERVICE", "MODERNIZATION", "DECOMMISSIONED"


@dataclass(frozen=True)
class ServiceRecord:
    """One maintenance/inspection event against a piece of equipment."""

    record_id: str
    equipment_id: str
    event_type: str
    performed_at: datetime
    technician_reference: Optional[str]
    notes: Optional[str]


@dataclass(frozen=True)
class SparePartAvailability:
    """Whether a part number is available, and where, right now."""

    part_number: str
    description: str
    available_quantity: int
    warehouse_code: Optional[str]
    lead_time_days: Optional[int]


class EquipmentIdentityAdapter(Protocol):
    """Resolves an equipment id to its identity record."""

    def get_equipment(self, equipment_id: str) -> Optional[EquipmentIdentity]:
        """Return the equipment record, or None if the id is unknown."""
        ...


class ServiceRecordAdapter(Protocol):
    """Reads maintenance/inspection history for a piece of equipment."""

    def list_service_records(
        self, equipment_id: str, since: Optional[datetime] = None
    ) -> List[ServiceRecord]:
        """Return service records for the equipment, newest first.

        ``since`` filters to records at or after that timestamp; omitted
        means the full available history.
        """
        ...


class SparePartsInventoryAdapter(Protocol):
    """Checks spare-parts availability by part number."""

    def check_availability(self, part_number: str) -> Optional[SparePartAvailability]:
        """Return current availability, or None if the part number is unknown."""
        ...


class AdapterError(RuntimeError):
    """Raised by an adapter implementation for a genuine integration failure
    (the external system is unreachable, returned malformed data, etc.) -
    distinct from a normal "not found", which returns None instead of
    raising, since "unknown id" is an expected outcome, not a fault.
    """
