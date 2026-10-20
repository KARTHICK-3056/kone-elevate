"""Which component types get the full deep dive, and which type is gone.

* Brake and Governor passports carry the life projection, material profile
  and pre-emptive forecast, like Motor, Steel Rope and Sheave.
* Governor has a measured inspection checklist covering the tripping speed
  test, rope groove wear, overspeed switch, gripping jaw and tripping
  linkage - the periodic EN 81-20/50 governor test, not just the car-load
  physics Door Operator still lacks.
* Guide Rail and Control Board were removed as component types.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

import sqlalchemy as sa

from app.ml import early_warning, inspection, life_model
from app.utils.enums import ComponentType, Material

DEEP_DIVE_TYPES = ("Motor", "Steel Rope", "Sheave", "Brake", "Governor")


@pytest.mark.parametrize("component_type", DEEP_DIVE_TYPES)
def test_every_deep_dive_type_is_fully_modelled(component_type):
    assert life_model.is_supported(component_type)
    assert component_type in life_model.MATERIAL_GRADES
    assert component_type in life_model.MECHANISMS
    assert component_type in early_warning.FAILURE_MODES
    assert component_type in early_warning.LEAD_TIME_DAYS
    assert inspection.checklist(component_type) is not None


@pytest.mark.parametrize(
    "component_type, material",
    [("Brake", "Cast Iron"), ("Governor", "Cast Iron")],
)
def test_the_passport_carries_the_deep_dive(client, component_payload, component_type, material):
    created = client.post(
        "/api/v1/components",
        json={**component_payload, "component_type": component_type, "material": material},
    ).json()
    body = client.get(f"/api/v1/passports/{created['component_id']}").json()
    assert body["life_assessment"]["supported"] is True
    assert body["life_assessment"]["available"] is True
    assert body["material_profile"]["supported"] is True
    assert body["early_warning"]["supported"] is True


def test_a_governor_inspection_is_scored_from_measurements():
    result = inspection.score(
        "Governor",
        {
            "governor_tripping_speed_deviation_pct": 0.0,
            "governor_rope_groove_wear_mm": 0.0,
            "governor_switch_trips_before_mechanical": True,
            "governor_jaw_grips_rope": True,
            "governor_linkage_condition": "free and lubricated",
        },
    )
    assert result["inspection_score"] == 100.0
    failed = inspection.score(
        "Governor",
        {"governor_switch_trips_before_mechanical": False},
    )
    assert failed["discard_criteria_met"] == ["Electrical overspeed switch trips before the mechanical trip speed"]
    assert failed["governing"]["key"] == "governor_switch_trips_before_mechanical"


@pytest.mark.parametrize(
    "component_type, key",
    [(t, k) for t, grades in life_model.MATERIAL_GRADES.items() for k in grades],
)
def test_every_grade_carries_a_formal_designation(component_type, key):
    grade = life_model.MATERIAL_GRADES[component_type][key]
    assert grade["designation"] and grade["grading_system"]
    assert grade["specifications"], "a grade must list its graded parts"
    for row in grade["specifications"]:
        assert row["part"] and row["grade"] and row["standard"]
    assert life_model.display_label(grade).endswith(grade["designation"])


def test_the_hardened_sheave_is_42crmo4_aisi_4140():
    grade = life_model.MATERIAL_GRADES["Sheave"]["hardened_steel"]
    assert grade["designation"] == "42CrMo4+QT"
    assert grade["equivalent"] == "AISI 4140"
    assert grade["grading_system"].startswith("EN 10083-3")


def test_the_passport_shows_the_grade_specification(client, component_payload):
    created = client.post(
        "/api/v1/components",
        json={**component_payload, "component_type": "Sheave", "material": "Cast Iron", "material_grade": "ductile_iron"},
    ).json()
    assert created["material_grade_label"].endswith("EN-GJS-600-3")
    profile = client.get(f"/api/v1/passports/{created['component_id']}").json()["material_profile"]
    assert profile["designation"] == "EN-GJS-600-3"
    assert profile["equivalent"] == "ASTM A536 80-55-06"
    assert profile["specifications"][0]["standard"].startswith("EN 1563")


def test_the_grade_catalogue_is_published_for_the_add_form(client):
    grades = client.get("/api/v1/meta/enums").json()["material_grades"]
    for component_type in DEEP_DIVE_TYPES:
        assert grades[component_type], component_type
    assert "Control Board" not in grades
    brake = {g["grade"]: g for g in grades["Brake"]}
    assert brake["cast_iron_drum_organic"]["designation"] == "EN-GJL-250 drum, SAE J866 FF lining"
    assert brake["cast_iron_drum_organic"]["grading_system"].startswith("EN 1561")


def test_a_recorded_grade_is_accepted_on_create(client, component_payload):
    created = client.post(
        "/api/v1/components",
        json={**component_payload, "component_type": "Brake", "material": "Cast Iron",
              "material_grade": "cast_iron_drum_organic"},
    )
    assert created.status_code == 201, created.text
    assert created.json()["material_grade_label"] == (
        life_model.display_label(life_model.MATERIAL_GRADES["Brake"]["cast_iron_drum_organic"])
    )


def test_guide_rail_is_no_longer_a_component_type(client, component_payload):
    assert "Guide Rail" not in ComponentType.values()
    response = client.post(
        "/api/v1/components", json={**component_payload, "component_type": "Guide Rail", "material": "Steel"}
    )
    assert response.status_code == 422


def test_control_board_is_no_longer_a_component_type(client, component_payload):
    assert "Control Board" not in ComponentType.values()
    assert "Electronic" not in Material.values()
    for type_, material in (("Control Board", "Electronic"), ("Motor", "Electronic")):
        response = client.post(
            "/api/v1/components", json={**component_payload, "component_type": type_, "material": material}
        )
        assert response.status_code == 422, (type_, material)


def test_the_control_board_migration_deletes_boards_and_keeps_the_ledger():
    path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0021_remove_control_board.py"
    spec = importlib.util.spec_from_file_location("m0021", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    engine = sa.create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(sa.text("CREATE TABLE components (id INTEGER PRIMARY KEY, component_type TEXT)"))
        conn.execute(sa.text("CREATE TABLE predictions (id INTEGER PRIMARY KEY, component_id INTEGER)"))
        conn.execute(sa.text("CREATE TABLE material_flow (id INTEGER PRIMARY KEY, component_pk INTEGER)"))
        conn.execute(sa.text("INSERT INTO components VALUES (1, 'Control Board'), (2, 'Motor')"))
        conn.execute(sa.text("INSERT INTO predictions VALUES (10, 1), (11, 2)"))
        conn.execute(sa.text("INSERT INTO material_flow VALUES (20, 1), (21, 2)"))

        assert migration.apply(conn) == 1

        assert conn.execute(sa.text("SELECT id FROM components")).scalars().all() == [2]
        assert conn.execute(sa.text("SELECT id FROM predictions")).scalars().all() == [11]
        ledger = dict(conn.execute(sa.text("SELECT id, component_pk FROM material_flow")).all())
        assert ledger == {20: None, 21: 2}


def test_the_seed_has_a_brake_demo_scenario():
    source = (Path(__file__).resolve().parents[1] / "scripts" / "seed_database.py").read_text(encoding="utf-8")
    assert "5. SAFETY-CRITICAL BRAKE, WORN LINING" in source


@pytest.mark.parametrize("component_type", ["Governor", "Door Operator"])
def test_governor_and_door_operator_have_a_life_and_a_forecast(client, component_payload, component_type):
    material = "Cast Iron" if component_type == "Governor" else "Aluminum"
    created = client.post(
        "/api/v1/components",
        json={**component_payload, "component_type": component_type, "material": material},
    ).json()
    body = client.get(f"/api/v1/passports/{created['component_id']}").json()
    assert body["life_assessment"]["available"] is True
    assert body["life_assessment"]["design_life_years"] > 0
    assert body["material_profile"]["grade_provenance"] == "industry_default"
    assert body["early_warning"]["supported"] is True
    assert component_type in early_warning.LEAD_TIME_DAYS
