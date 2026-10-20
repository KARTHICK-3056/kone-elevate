"""KONE systems integration endpoints, behind the anti-corruption layer (P5).

Every response carries the ``source`` the answer actually came from -
``"fixture"`` or ``"kone-api"`` - the same "state which parts are real"
discipline the DPP export (`registry_status`) and the chain anchor
(`published_to`) already use elsewhere in this codebase.

KONE-backed adapters exist as of K-1 and are selected automatically when
``KONE_CLIENT_ID``/``KONE_CLIENT_SECRET`` are configured. **They are not
configured in this build and no live KONE call has ever been made**, so
every response today reads ``"source": "fixture"``. That string is read off
the active adapter rather than hardcoded, so it stops saying "fixture" the
moment it stops being true. ``GET /integrations/status`` reports the whole
picture; see docs/kone-integration.md.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, status

from app.integrations import kone_adapters, kone_labels, registry
from app.integrations.base import EquipmentIdentity, ServiceRecord, SparePartAvailability

router = APIRouter(prefix="/integrations", tags=["KONE Integration"])

_SOURCE_NOTICE = (
    "read from the active adapter. `fixture` unless KONE credentials are "
    "configured; this build has none, and no live KONE call has ever been "
    "made. See GET /integrations/status and docs/kone-integration.md."
)


def _source_of(adapter: object) -> str:
    """What the active adapter is actually talking to.

    Read off the adapter rather than hardcoded: a response that claims
    "fixture" while a real adapter answered - or vice versa - is worse than
    no provenance field at all.
    """
    return str(getattr(adapter, "source", "fixture"))


def _equipment_to_dict(identity: EquipmentIdentity) -> Dict[str, Any]:
    return {
        "equipment_id": identity.equipment_id,
        "equipment_type": identity.equipment_type,
        "site_name": identity.site_name,
        "site_address": identity.site_address,
        "installation_date": identity.installation_date,
        "status": identity.status,
    }


def _service_record_to_dict(record: ServiceRecord) -> Dict[str, Any]:
    return {
        "record_id": record.record_id,
        "equipment_id": record.equipment_id,
        "event_type": record.event_type,
        "performed_at": record.performed_at,
        "technician_reference": record.technician_reference,
        "notes": record.notes,
    }


def _part_to_dict(part: SparePartAvailability) -> Dict[str, Any]:
    return {
        "part_number": part.part_number,
        "description": part.description,
        "available_quantity": part.available_quantity,
        "warehouse_code": part.warehouse_code,
        "lead_time_days": part.lead_time_days,
    }


@router.get(
    "/equipment/{equipment_id}",
    summary="Resolve equipment identity",
    description=(
        "Equipment identity behind the anti-corruption layer. "
        f"**Source: {_SOURCE_NOTICE}**"
    ),
    responses={404: {"description": "Unknown equipment id"}},
)
def get_equipment(equipment_id: str) -> Dict[str, Any]:
    adapter = registry.equipment_identity_adapter()
    identity = adapter.get_equipment(equipment_id)
    if identity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Equipment '{equipment_id}' was not found.",
        )
    return {**_equipment_to_dict(identity), "source": _source_of(adapter)}


@router.get(
    "/equipment/{equipment_id}/service-records",
    summary="Equipment service-record history",
    description=(
        "Maintenance/inspection history for one piece of equipment, behind "
        f"the anti-corruption layer. **Source: {_SOURCE_NOTICE}**"
    ),
)
def list_service_records(
    equipment_id: str,
    since: Optional[datetime] = Query(None, description="Only records at or after this timestamp"),
) -> Dict[str, Any]:
    adapter = registry.service_record_adapter()
    records: List[ServiceRecord] = adapter.list_service_records(equipment_id, since=since)
    return {
        "equipment_id": equipment_id,
        "count": len(records),
        "items": [_service_record_to_dict(record) for record in records],
        "source": _source_of(adapter),
    }


@router.get(
    "/spare-parts/{part_number}",
    summary="Spare-parts availability",
    description=(
        "Availability for one part number, behind the anti-corruption layer. "
        f"**Source: {_SOURCE_NOTICE}**"
    ),
    responses={404: {"description": "Unknown part number"}},
)
def check_spare_part(part_number: str) -> Dict[str, Any]:
    adapter = registry.spare_parts_adapter()
    availability = adapter.check_availability(part_number)
    if availability is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Part number '{part_number}' was not found.",
        )
    return {**_part_to_dict(availability), "source": _source_of(adapter)}


@router.get(
    "/equipment/{equipment_id}/harvested-labels",
    summary="Weak disposition labels harvested from KONE service orders",
    description=(
        "The only route to real disposition labels that does not require a "
        "pilot - and an honest account of how far it gets.\n\n"
        "KONE's `technicianActionCode` records what was done to the "
        "**equipment**, not where a removed **component** went. This can "
        "therefore observe 'the part was kept in service' directly, and "
        "cannot distinguish component recovery from material recovery from disposal for "
        "anything that came out. Those observations are returned as "
        "**censored**, never guessed.\n\n"
        "`coverage.classes_never_observed` is the figure that matters: this "
        "source is blind to the disposal classes, so it is for measuring "
        "agreement, not for retraining."
    ),
)
def harvested_labels(equipment_id: str) -> Dict[str, Any]:
    orders = kone_adapters.service_order_details(equipment_id)
    labels = kone_labels.harvest(orders)
    return {
        "equipment_id": equipment_id,
        "labels": labels,
        "coverage": kone_labels.label_coverage(labels),
        "scoreable": len(kone_labels.agreement_input(labels)),
        "source": registry.integration_status()["adapters"]["service_records"],
    }


@router.get(
    "/status",
    summary="What each integration interface is actually talking to",
    description=(
        "Whether KONE credentials are configured, which adapter is serving "
        "each interface, and the provenance of the integration itself. "
        "Published so a caller never has to assume a figure came from KONE "
        "when it came from a recorded fixture."
    ),
)
def integration_status() -> Dict[str, Any]:
    return registry.integration_status()
