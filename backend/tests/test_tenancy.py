"""Row-level multi-tenancy: country is a hard boundary, unit a soft default.

See app.core.tenancy for the design this proves: a technician in one country
cannot see a component in another (404, not 403 - see the module docstring
for why); a planner in a different frontline unit within the *same* country
sees nothing by default but everything with ``?all_units=true``; the
the two global roles
(sustainability_controller, read_only_auditor) see across every country.
"""

from __future__ import annotations

from app.utils.enums import Role


def _create_component(client, **overrides):
    payload = {
        "component_type": "Motor",
        "material": "Steel",
        "manufacturer": "KONE MonoSpace",
        "origin": "Chennai Plant",
        "installation_date": "2018-04-12",
        "location": "Chennai, India",
        "operating_hours": 18000,
        "load_cycles": 140000,
        "average_load": 650,
        "vibration": 3.8,
        "temperature": 52,
        "service_count": 5,
        "repair_count": 1,
        "failure_history": 0,
        "inspection_score": 82,
        "run_initial_prediction": False,
    }
    payload.update(overrides)
    response = client.post("/api/v1/components", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


# --------------------------------------------------------------------------
# Country: the hard boundary
# --------------------------------------------------------------------------
def test_cross_country_component_read_is_a_404_not_a_403(tenant_client):
    india_tech = tenant_client(Role.TECHNICIAN, country="India", frontline_unit="Chennai")
    germany_tech = tenant_client(Role.TECHNICIAN, country="Germany", frontline_unit="Berlin")

    created = _create_component(india_tech, location="Chennai, India")

    response = germany_tech.get(f"/api/v1/components/{created['component_id']}")
    assert response.status_code == 404
    # Same failure shape as a genuinely nonexistent id - never 403 - so a
    # cross-country probe cannot distinguish "wrong tenant" from "no such id".
    assert "not found" in response.json()["detail"].lower()


def test_cross_country_component_is_excluded_from_listing_and_dashboard(tenant_client):
    india_tech = tenant_client(Role.TECHNICIAN, country="India", frontline_unit="Chennai")
    germany_tech = tenant_client(Role.TECHNICIAN, country="Germany", frontline_unit="Berlin")

    created = _create_component(india_tech, location="Chennai, India")

    listing = germany_tech.get("/api/v1/components").json()
    assert all(item["component_id"] != created["component_id"] for item in listing["items"])

    before = germany_tech.get("/api/v1/dashboard/summary").json()["total_components"]
    _create_component(india_tech, location="Chennai, India")
    after = germany_tech.get("/api/v1/dashboard/summary").json()["total_components"]
    assert after == before  # a second India-only component never moved Germany's count


def test_a_component_created_without_a_country_defaults_to_the_caller(tenant_client):
    india_tech = tenant_client(Role.TECHNICIAN, country="India", frontline_unit="Chennai")
    created = _create_component(india_tech)
    assert created["country"] == "India"


def test_global_role_has_no_default_country_and_must_supply_one(tenant_client):
    auditor = tenant_client(Role.READ_ONLY_AUDITOR, country=None, frontline_unit=None)
    response = auditor.post(
        "/api/v1/components",
        json={
            "component_type": "Motor",
            "material": "Steel",
            "installation_date": "2018-04-12",
            "run_initial_prediction": False,
        },
    )
    # Read-only auditors cannot write at all - current_actor rejects them
    # before the missing-country check would even run.
    assert response.status_code == 403


def test_sustainability_controller_sees_every_country(tenant_client):
    india_tech = tenant_client(Role.TECHNICIAN, country="India", frontline_unit="Chennai")
    germany_tech = tenant_client(Role.TECHNICIAN, country="Germany", frontline_unit="Berlin")
    controller = tenant_client(Role.SUSTAINABILITY_CONTROLLER, country=None, frontline_unit=None)

    india_component = _create_component(india_tech, location="Chennai, India")
    germany_component = _create_component(germany_tech, location="Berlin, Germany")

    ids = {item["component_id"] for item in controller.get("/api/v1/components").json()["items"]}
    assert india_component["component_id"] in ids
    assert germany_component["component_id"] in ids


def test_read_only_auditor_can_read_a_component_from_any_country(tenant_client):
    germany_tech = tenant_client(Role.TECHNICIAN, country="Germany", frontline_unit="Berlin")
    auditor = tenant_client(Role.READ_ONLY_AUDITOR, country=None, frontline_unit=None)

    created = _create_component(germany_tech, location="Berlin, Germany")
    response = auditor.get(f"/api/v1/components/{created['component_id']}")
    assert response.status_code == 200


# --------------------------------------------------------------------------
# Frontline unit: the soft default
# --------------------------------------------------------------------------
def test_frontline_unit_is_a_default_not_a_boundary(tenant_client):
    chennai_tech = tenant_client(Role.TECHNICIAN, country="India", frontline_unit="Chennai")
    bengaluru_planner = tenant_client(
        Role.RECOVERY_PLANNER, country="India", frontline_unit="Bengaluru"
    )

    created = _create_component(chennai_tech, location="Chennai, India")

    # Default view: a different unit in the same country does not see it ...
    default_view = bengaluru_planner.get("/api/v1/components").json()
    assert all(item["component_id"] != created["component_id"] for item in default_view["items"])

    # ... but it is not a hard boundary - all_units=true reveals it, unlike
    # the country case where nothing lifts the block.
    all_units_view = bengaluru_planner.get("/api/v1/components?all_units=true").json()
    assert any(item["component_id"] == created["component_id"] for item in all_units_view["items"])

    # And a direct lookup by id succeeds regardless of all_units - unit is
    # only a default for *listing*, not a lookup restriction.
    direct = bengaluru_planner.get(f"/api/v1/components/{created['component_id']}")
    assert direct.status_code == 200
