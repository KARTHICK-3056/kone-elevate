"""Anti-corruption-layer contract tests (P5).

The functions in this file describe what ANY implementation of the three
adapter interfaces must satisfy - today that means the fixture adapters,
tomorrow it would mean a real KONE-backed one. A future real adapter is
expected to be run through these same functions before it is trusted,
which is the entire point of writing the contract once, separately from
any one implementation.
"""

from __future__ import annotations

from datetime import timedelta

from app.integrations.base import (
    EquipmentIdentity,
    EquipmentIdentityAdapter,
    ServiceRecord,
    ServiceRecordAdapter,
    SparePartAvailability,
    SparePartsInventoryAdapter,
)
from app.integrations.fixture_adapters import (
    FixtureEquipmentIdentityAdapter,
    FixtureServiceRecordAdapter,
    FixtureSparePartsAdapter,
)


# --------------------------------------------------------------------------
# Contracts - reusable across any adapter implementation
# --------------------------------------------------------------------------
def assert_equipment_identity_contract(
    adapter: EquipmentIdentityAdapter, known_id: str, unknown_id: str
) -> None:
    identity = adapter.get_equipment(known_id)
    assert isinstance(identity, EquipmentIdentity)
    assert identity.equipment_id == known_id
    assert identity.equipment_type
    assert identity.site_name
    assert identity.status

    assert adapter.get_equipment(unknown_id) is None  # never raises for "not found"


def assert_service_record_contract(
    adapter: ServiceRecordAdapter, known_equipment_id: str, unknown_equipment_id: str
) -> None:
    records = adapter.list_service_records(known_equipment_id)
    assert isinstance(records, list)
    assert all(isinstance(r, ServiceRecord) for r in records)
    assert all(r.equipment_id == known_equipment_id for r in records)
    # Newest first.
    assert records == sorted(records, key=lambda r: r.performed_at, reverse=True)

    assert adapter.list_service_records(unknown_equipment_id) == []  # empty, not an error

    if records:
        cutoff = records[0].performed_at
        filtered = adapter.list_service_records(known_equipment_id, since=cutoff)
        assert all(r.performed_at >= cutoff for r in filtered)


def assert_spare_parts_contract(
    adapter: SparePartsInventoryAdapter, known_part: str, unknown_part: str
) -> None:
    availability = adapter.check_availability(known_part)
    assert isinstance(availability, SparePartAvailability)
    assert availability.part_number == known_part
    assert availability.available_quantity >= 0

    assert adapter.check_availability(unknown_part) is None


# --------------------------------------------------------------------------
# The fixture adapters, run against the contracts above
# --------------------------------------------------------------------------
def test_fixture_equipment_identity_adapter_satisfies_the_contract():
    assert_equipment_identity_contract(
        FixtureEquipmentIdentityAdapter(), known_id="EQ-CHN-0001", unknown_id="EQ-DOES-NOT-EXIST"
    )


def test_fixture_service_record_adapter_satisfies_the_contract():
    assert_service_record_contract(
        FixtureServiceRecordAdapter(),
        known_equipment_id="EQ-CHN-0001",
        unknown_equipment_id="EQ-DOES-NOT-EXIST",
    )


def test_fixture_spare_parts_adapter_satisfies_the_contract():
    assert_spare_parts_contract(
        FixtureSparePartsAdapter(), known_part="KE-GOV-STD-01", unknown_part="NOT-A-REAL-PART"
    )


def test_service_records_since_filter_excludes_older_records():
    adapter = FixtureServiceRecordAdapter()
    all_records = adapter.list_service_records("EQ-CHN-0001")
    assert len(all_records) >= 2

    future_cutoff = max(r.performed_at for r in all_records) + timedelta(days=1)
    assert adapter.list_service_records("EQ-CHN-0001", since=future_cutoff) == []


def test_fixture_data_uses_timezone_aware_timestamps():
    # A real API will return timezone-aware timestamps; a fixture adapter
    # that silently parsed naive ones would pass every other test here and
    # still break the moment `since=` is compared against `datetime.now(UTC)`.
    adapter = FixtureServiceRecordAdapter()
    for record in adapter.list_service_records("EQ-CHN-0001"):
        assert record.performed_at.tzinfo is not None


# --------------------------------------------------------------------------
# The API layer built on top of the adapters
# --------------------------------------------------------------------------
def test_get_equipment_endpoint(client):
    response = client.get("/api/v1/integrations/equipment/EQ-CHN-0001")
    assert response.status_code == 200
    body = response.json()
    assert body["equipment_id"] == "EQ-CHN-0001"
    assert body["source"] == "fixture"


def test_get_equipment_endpoint_404_for_unknown_id(client):
    response = client.get("/api/v1/integrations/equipment/NOPE")
    assert response.status_code == 404


def test_service_records_endpoint(client):
    response = client.get("/api/v1/integrations/equipment/EQ-CHN-0001/service-records")
    assert response.status_code == 200
    body = response.json()
    assert body["equipment_id"] == "EQ-CHN-0001"
    assert body["count"] == len(body["items"])
    assert body["source"] == "fixture"


def test_spare_part_endpoint(client):
    response = client.get("/api/v1/integrations/spare-parts/KE-BRK-STD-02")
    assert response.status_code == 200
    body = response.json()
    assert body["part_number"] == "KE-BRK-STD-02"
    assert body["available_quantity"] >= 0


def test_spare_part_endpoint_404_for_unknown_part(client):
    response = client.get("/api/v1/integrations/spare-parts/NOT-A-REAL-PART")
    assert response.status_code == 404


def test_integrations_require_authentication(anonymous_client):
    assert anonymous_client.get("/api/v1/integrations/equipment/EQ-CHN-0001").status_code == 401
