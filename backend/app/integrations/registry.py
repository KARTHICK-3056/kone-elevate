"""Selects which adapter implementation is active.

The swap point this module was written for now has something to swap to.
``KONE_CLIENT_ID`` + ``KONE_CLIENT_SECRET`` select the KONE-backed
adapters; without them the fixture adapters keep answering, and every
response says which was used (``source``).

Spare parts is the exception, and stays fixture-only whatever is
configured: KONE publishes no spare-parts API in its reference
implementation, so there is no real backend to select. Silently returning
fixture stock from a call that looked like a live inventory check is
exactly the failure the ``source`` field exists to prevent.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Dict

from app.core.config import settings
from app.integrations.base import (
    EquipmentIdentityAdapter,
    ServiceRecordAdapter,
    SparePartsInventoryAdapter,
)
from app.integrations.fixture_adapters import (
    FixtureEquipmentIdentityAdapter,
    FixtureServiceRecordAdapter,
    FixtureSparePartsAdapter,
)
from app.integrations.kone_adapters import (
    KoneEquipmentIdentityAdapter,
    KoneServiceRecordAdapter,
)


@lru_cache
def equipment_identity_adapter() -> EquipmentIdentityAdapter:
    if settings.kone_api_configured:
        return KoneEquipmentIdentityAdapter()
    return FixtureEquipmentIdentityAdapter()


@lru_cache
def service_record_adapter() -> ServiceRecordAdapter:
    if settings.kone_api_configured:
        return KoneServiceRecordAdapter()
    return FixtureServiceRecordAdapter()


@lru_cache
def spare_parts_adapter() -> SparePartsInventoryAdapter:
    return FixtureSparePartsAdapter()


def integration_status() -> Dict[str, Any]:
    """What each interface is actually talking to right now.

    Exposed so the API can state its own provenance rather than leaving a
    caller to assume a number came from KONE when it came from a fixture.
    """
    configured = settings.kone_api_configured
    return {
        "kone_api_configured": configured,
        "kone_api_hostname": settings.KONE_API_HOSTNAME,
        "adapters": {
            "equipment_identity": "kone-api" if configured else "fixture",
            "service_records": "kone-api" if configured else "fixture",
            "spare_parts": "fixture",
        },
        "spare_parts_note": (
            "Permanently fixture-backed: KONE publishes no spare-parts API in "
            "its reference implementation, so there is no live source to "
            "select even with credentials configured."
        ),
        "live_call_ever_made": False,
        "provenance_note": (
            "Endpoints, OAuth scopes and response field names were written "
            "from KONE's published Apache-2.0 reference implementation "
            "(github.com/konecorp/kone-api-examples), not from a response "
            "this build has received. No KONE credentials exist here. See "
            "docs/kone-integration.md."
        ),
    }
