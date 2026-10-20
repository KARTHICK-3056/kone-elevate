"""KONE-backed adapters: the anti-corruption layer's real implementations.

This is the only module in the codebase allowed to know KONE's field names.
Everything downstream sees ``EquipmentIdentity`` / ``ServiceRecord`` from
``app.integrations.base`` and nothing else - which is what makes the
mapping decisions below the single place a schema misreading can hurt, and
therefore the place the contract tests concentrate on.

Two of the three interfaces get a real implementation:

* :class:`KoneEquipmentIdentityAdapter` - Equipment Status API v2.
* :class:`KoneServiceRecordAdapter` - Service Info API v2.
* **Spare parts: not implemented.** KONE publishes no spare-parts API in
  its reference implementation, so there is no real backend to point at.
  The registry keeps serving the fixture adapter and says so, rather than
  shipping a class whose name implies an integration that does not exist.

Where the mapping loses something
---------------------------------
The two systems do not model the same thing, and pretending otherwise is
how an anti-corruption layer rots:

* KONE addresses **equipment** - a whole lift behind one KEN. This platform
  tracks **components**. An identity mapped here describes the lift, not
  the sheave inside it; ``app.integrations.kone_features`` is where that
  gap is handled explicitly.
* ``EquipmentIdentity.installation_date`` has **no source**. Nothing in the
  published Equipment Status schema carries a commissioning date, so it is
  mapped as ``None`` rather than being back-derived from the first service
  order, which would be a guess wearing a date's clothes.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.integrations import kone_client
from app.integrations.base import EquipmentIdentity, ServiceRecord
from app.integrations.kone_client import KoneApiClient

#: KONE ``status``/``equipmentStatus`` values onto the vocabulary
#: ``EquipmentIdentity.status`` already uses elsewhere in this codebase.
_STATUS_MAP: Dict[str, str] = {
    "IN_SERVICE": "IN_SERVICE",
    "OPERATIONAL": "IN_SERVICE",
    "AVAILABLE": "IN_SERVICE",
    "OUT_OF_SERVICE": "OUT_OF_SERVICE",
    "UNDER_MAINTENANCE": "MAINTENANCE",
    "MODERNIZATION": "MODERNIZATION",
    "DECOMMISSIONED": "DECOMMISSIONED",
}

#: KONE ``activityType`` onto this platform's service-event vocabulary.
#: Anything unrecognised passes through unchanged rather than being forced
#: into the nearest bucket - a silently mis-bucketed event is worse than an
#: obviously foreign one.
_ACTIVITY_MAP: Dict[str, str] = {
    "PREVENTIVE_MAINTENANCE": "MAINTENANCE",
    "MAINTENANCE": "MAINTENANCE",
    "CALLOUT": "REPAIR",
    "REPAIR": "REPAIR",
    "INSPECTION": "INSPECTION",
    "MODERNIZATION": "MODERNIZATION",
    "REPLACEMENT": "REMOVAL",
}


def _parse_timestamp(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _address(payload: Dict[str, Any]) -> Optional[str]:
    parts = [
        payload.get("addressStreet"),
        payload.get("addressPostCode"),
        payload.get("addressCity"),
        payload.get("addressCountry"),
    ]
    joined = ", ".join(str(part) for part in parts if part)
    return joined or None


class KoneEquipmentIdentityAdapter:
    """Equipment Status API v2. See base.EquipmentIdentityAdapter."""

    def __init__(self, client: Optional[KoneApiClient] = None) -> None:
        self._client = client or kone_client.build_client()

    @property
    def source(self) -> str:
        return self._client.source

    def get_equipment(self, equipment_id: str) -> Optional[EquipmentIdentity]:
        ken = kone_client.normalise_ken(equipment_id)
        payload = self._client.get(
            kone_client.equipment_search_path("status"),
            [kone_client.equipment_scope(ken, "rtm")],
        )
        if not payload:
            return None
        # The recorded fixture holds one equipment; a real search response is
        # scoped to the KEN in the token, so a mismatch means we were handed
        # somebody else's equipment and must not return it as this one.
        returned = str(payload.get("equipmentId") or ken)
        if kone_client.normalise_ken(returned) != ken:
            return None

        raw_status = str(
            payload.get("equipmentStatus") or payload.get("status") or ""
        ).upper()
        return EquipmentIdentity(
            equipment_id=ken,
            equipment_type=str(payload.get("equipmentType") or "UNKNOWN"),
            site_name=str(
                payload.get("equipmentLocationDescription")
                or payload.get("addressCity")
                or "Unknown site"
            ),
            site_address=_address(payload),
            # No commissioning date exists anywhere in the published schema.
            installation_date=None,
            status=_STATUS_MAP.get(raw_status, raw_status or "UNKNOWN"),
        )


class KoneServiceRecordAdapter:
    """Service Info API v2. See base.ServiceRecordAdapter.

    Two calls per equipment: ``/serviceOrders`` lists the order numbers,
    then each order is fetched individually for the fields that matter
    (``failedComponentCode``, ``technicianActionCode``, the condition codes).
    KONE publishes no bulk-detail endpoint, so this is N+1 by the API's own
    shape rather than by choice - ``since`` exists to bound it.
    """

    def __init__(self, client: Optional[KoneApiClient] = None) -> None:
        self._client = client or kone_client.build_client()

    @property
    def source(self) -> str:
        return self._client.source

    def list_service_records(
        self, equipment_id: str, since: Optional[datetime] = None
    ) -> List[ServiceRecord]:
        ken = kone_client.normalise_ken(equipment_id)
        scopes = [kone_client.equipment_scope(ken, "serviceinfo")]
        listing = self._client.get(kone_client.service_orders_path(ken), scopes)
        if not listing:
            return []

        records: List[ServiceRecord] = []
        for row in listing:
            order_id = row.get("serviceOrderNumber")
            if not order_id:
                continue
            detail = self._client.get(
                kone_client.service_order_path(ken, str(order_id)), scopes
            )
            record = self._to_record(ken, row, detail)
            if record is None:
                continue
            if since is not None and record.performed_at < _as_aware(since):
                continue
            records.append(record)

        return sorted(records, key=lambda r: r.performed_at, reverse=True)

    def _to_record(
        self, ken: str, listing_row: Dict[str, Any], detail: Optional[Dict[str, Any]]
    ) -> Optional[ServiceRecord]:
        detail = detail or {}
        performed = _parse_timestamp(
            detail.get("finishedDateTime") or detail.get("actualArrivalDateTime")
        )
        if performed is None:
            # A service order with no date cannot be placed in a history, and
            # guessing one would corrupt every interval derived from it.
            return None

        activity = str(
            detail.get("activityType") or listing_row.get("activityType") or ""
        ).upper()
        return ServiceRecord(
            record_id=str(listing_row.get("serviceOrderNumber")),
            equipment_id=ken,
            event_type=_ACTIVITY_MAP.get(activity, activity or "UNKNOWN"),
            performed_at=performed,
            technician_reference=(
                str(detail["technicianRegistrationNumber"])
                if detail.get("technicianRegistrationNumber")
                else None
            ),
            notes=_notes(detail),
        )


def _as_aware(value: datetime) -> datetime:
    """Compare naive and aware timestamps without raising.

    Callers inside this codebase pass naive UTC datetimes; KONE returns
    ISO-8601 with an offset. Treating a naive value as UTC is the
    assumption already made everywhere else here (``utils.helpers.utcnow``).
    """
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _notes(detail: Dict[str, Any]) -> Optional[str]:
    """Flatten the fields a technician would actually want to read.

    ``failedComponentCode`` is carried into the note deliberately: it is the
    only component-level signal anywhere in KONE's public API surface, and
    dropping it in the mapping would throw away the most valuable field the
    Service Info API has.
    """
    fragments = [
        detail.get("jobDescription"),
        detail.get("additionalCommentsToCustomer"),
    ]
    if detail.get("failedComponentCode"):
        fragments.append(f"Failed component: {detail['failedComponentCode']}")
    if detail.get("equipmentFailureReason"):
        fragments.append(f"Failure reason: {detail['equipmentFailureReason']}")
    if detail.get("technicianActionCode"):
        fragments.append(f"Action: {detail['technicianActionCode']}")
    joined = " | ".join(str(part) for part in fragments if part)
    return joined or None


def service_order_details(
    equipment_id: str, client: Optional[KoneApiClient] = None
) -> List[Dict[str, Any]]:
    """Raw service-order detail documents for one equipment.

    Deliberately *not* part of the ``ServiceRecordAdapter`` protocol: this
    returns KONE-shaped dictionaries, and the protocol exists precisely so
    that most of the codebase never sees those. The feature-derivation layer
    (``app.integrations.kone_features``) needs the fields the generic
    ``ServiceRecord`` drops - condition codes, work time, failure codes - so
    it reaches for this instead, and it is the only caller that should.
    """
    api = client or kone_client.build_client()
    ken = kone_client.normalise_ken(equipment_id)
    scopes = [kone_client.equipment_scope(ken, "serviceinfo")]
    listing = api.get(kone_client.service_orders_path(ken), scopes) or []
    details: List[Dict[str, Any]] = []
    for row in listing:
        order_id = row.get("serviceOrderNumber")
        if not order_id:
            continue
        detail = api.get(kone_client.service_order_path(ken, str(order_id)), scopes)
        if detail:
            details.append(detail)
    return details


def equipment_telemetry(
    equipment_id: str, client: Optional[KoneApiClient] = None
) -> Dict[str, Any]:
    """Availability, status and the latest movement event, in KONE's shapes."""
    api = client or kone_client.build_client()
    ken = kone_client.normalise_ken(equipment_id)
    scopes = [kone_client.equipment_scope(ken, "rtm")]
    return {
        "status": api.get(kone_client.equipment_search_path("status"), scopes),
        "availability": api.get(kone_client.equipment_search_path("availability"), scopes),
        "movement": api.get(kone_client.equipment_search_path("movement"), scopes),
        "source": api.source,
    }
