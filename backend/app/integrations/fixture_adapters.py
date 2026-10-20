"""Fixture-backed adapters: the only concrete implementations that exist today.

Each reads a small recorded JSON fixture instead of calling a live system.
This is deliberately not a mock used only in tests - it is wired into
``app/api/integrations.py`` and answers real API requests, so the adapter
interface, the API layer built on top of it, and the contract tests all
exercise the same code path a real adapter would.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional

from app.integrations.base import EquipmentIdentity, ServiceRecord, SparePartAvailability

_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def _load(filename: str) -> list:
    with open(_FIXTURES_DIR / filename, encoding="utf-8") as handle:
        return json.load(handle)


class FixtureEquipmentIdentityAdapter:
    """Reads equipment.json. See app.integrations.base.EquipmentIdentityAdapter."""

    def __init__(self) -> None:
        self._records: Dict[str, EquipmentIdentity] = {}
        for row in _load("equipment.json"):
            identity = EquipmentIdentity(
                equipment_id=row["equipment_id"],
                equipment_type=row["equipment_type"],
                site_name=row["site_name"],
                site_address=row.get("site_address"),
                installation_date=date.fromisoformat(row["installation_date"])
                if row.get("installation_date")
                else None,
                status=row["status"],
            )
            self._records[identity.equipment_id] = identity

    @property
    def source(self) -> str:
        return "fixture"

    def get_equipment(self, equipment_id: str) -> Optional[EquipmentIdentity]:
        return self._records.get(equipment_id)


class FixtureServiceRecordAdapter:
    """Reads service_records.json. See app.integrations.base.ServiceRecordAdapter."""

    def __init__(self) -> None:
        self._records: List[ServiceRecord] = [
            ServiceRecord(
                record_id=row["record_id"],
                equipment_id=row["equipment_id"],
                event_type=row["event_type"],
                performed_at=datetime.fromisoformat(row["performed_at"].replace("Z", "+00:00")),
                technician_reference=row.get("technician_reference"),
                notes=row.get("notes"),
            )
            for row in _load("service_records.json")
        ]

    @property
    def source(self) -> str:
        return "fixture"

    def list_service_records(
        self, equipment_id: str, since: Optional[datetime] = None
    ) -> List[ServiceRecord]:
        matches = [r for r in self._records if r.equipment_id == equipment_id]
        if since is not None:
            matches = [r for r in matches if r.performed_at >= since]
        return sorted(matches, key=lambda r: r.performed_at, reverse=True)


class FixtureSparePartsAdapter:
    """Reads spare_parts.json. See app.integrations.base.SparePartsInventoryAdapter."""

    def __init__(self) -> None:
        self._records: Dict[str, SparePartAvailability] = {}
        for row in _load("spare_parts.json"):
            availability = SparePartAvailability(
                part_number=row["part_number"],
                description=row["description"],
                available_quantity=row["available_quantity"],
                warehouse_code=row.get("warehouse_code"),
                lead_time_days=row.get("lead_time_days"),
            )
            self._records[availability.part_number] = availability

    @property
    def source(self) -> str:
        return "fixture"

    def check_availability(self, part_number: str) -> Optional[SparePartAvailability]:
        return self._records.get(part_number)
