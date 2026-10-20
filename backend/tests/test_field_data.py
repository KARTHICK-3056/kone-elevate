"""Simulation from a real component, saved scenarios, measured inspections, telemetry."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.ml import inspection


def _motor(client, component_payload, **overrides):
    response = client.post("/api/v1/components", json={**component_payload, **overrides})
    assert response.status_code == 201, response.text
    return response.json()


# --------------------------------------------------------------- simulation from a real part
def test_simulation_starts_from_a_real_components_record(client, component_payload):
    motor = _motor(client, component_payload)
    body = client.post(f"/api/v1/simulation/start/{motor['component_id']}").json()

    focus = body["results"]["focus"]
    assert focus["component_id"] == motor["component_id"]
    params = body["results"]["components"]["Motor"]["parameters"]
    assert params["load_cycles"] == component_payload["load_cycles"]
    assert params["component_age"] > 8  # installed 2018
    assert "temperature_offset" in focus["calibration"]
    assert 0 <= focus["historical_load_kg"] <= 1100


def test_calibration_reproduces_the_units_own_readings(client, component_payload):
    motor = _motor(client, component_payload)
    start = client.post(f"/api/v1/simulation/start/{motor['component_id']}").json()
    step = client.post(
        "/api/v1/simulation/advance",
        json={"state": start["state"], "load_kg": start["results"]["focus"]["historical_load_kg"], "months": 1},
    ).json()
    truth = step["results"]["components"]["Motor"]["truth"]
    # One month on at its own load, the simulated reading sits near the real one.
    assert abs(truth["temperature"] - component_payload["temperature"]) < 8


def test_unsupported_type_cannot_be_simulated(client, component_payload):
    door = _motor(client, component_payload, component_type="Door Operator", material="Aluminum")
    assert client.post(f"/api/v1/simulation/start/{door['component_id']}").status_code == 422


# --------------------------------------------------------------- saved scenarios
def test_saved_scenario_is_labelled_and_never_touches_fleet_data(client, component_payload):
    motor = _motor(client, component_payload)
    component_id = motor["component_id"]
    before_component = client.get(f"/api/v1/components/{component_id}").json()
    before_dashboard = client.get("/api/v1/dashboard/summary").json()

    run = client.post(f"/api/v1/simulation/start/{component_id}").json()
    run = client.post(
        "/api/v1/simulation/advance", json={"state": run["state"], "load_kg": 900, "months": 24}
    ).json()
    saved = client.post(
        f"/api/v1/simulation/scenarios/{component_id}", json={"state": run["state"], "name": "Heavier traffic"}
    )
    assert saved.status_code == 201, saved.text
    summary = saved.json()["summary"]
    assert summary["kind"] == "SIMULATION" and summary["not_fleet_data"] is True
    assert summary["months_simulated"] == 24
    assert 900 in summary["loads_simulated_kg"]

    # The component itself and the fleet figures are untouched.
    after_component = client.get(f"/api/v1/components/{component_id}").json()
    for field in ("load_cycles", "operating_hours", "average_load", "inspection_score"):
        assert after_component[field] == before_component[field]
    # Every fleet figure is identical; only the audit count moves, because
    # saving a scenario is itself an audited action.
    after_dashboard = client.get("/api/v1/dashboard/summary").json()
    after_dashboard.pop("audit_records"); before_dashboard.pop("audit_records")
    assert after_dashboard == before_dashboard

    # It shows on the public passport, without who saved it.
    passport = client.get(f"/api/v1/passports/{component_id}").json()
    assert passport["scenarios"][0]["name"] == "Heavier traffic"
    assert "created_by" not in passport["scenarios"][0]

    scenario_id = saved.json()["id"]
    assert client.delete(f"/api/v1/simulation/scenarios/item/{scenario_id}").status_code == 204
    assert client.get(f"/api/v1/simulation/scenarios/{component_id}").json() == []


def test_a_new_lift_simulation_cannot_be_saved_to_a_component(client, component_payload):
    motor = _motor(client, component_payload)
    fresh = client.post("/api/v1/simulation/advance", json={"load_kg": 460, "months": 3}).json()
    response = client.post(
        f"/api/v1/simulation/scenarios/{motor['component_id']}", json={"state": fresh["state"]}
    )
    assert response.status_code == 422


# --------------------------------------------------------------- measured inspections
def test_worst_measurement_governs_the_score():
    result = inspection.score(
        "Steel Rope",
        {"nominal_diameter_mm": 10.0, "measured_diameter_mm": 9.7, "broken_wires_6d": 1, "rope_corrosion": "none"},
    )
    # 3% diameter loss of a 6% limit = 0.5 -> 100 - 65 x 0.5
    assert result["measured_values"]["rope_diameter_reduction_pct"] == pytest.approx(3.0)
    assert result["governing"]["key"] == "rope_diameter_reduction_pct"
    assert result["inspection_score"] == pytest.approx(67.5)
    assert result["discard_criteria_met"] == []


def test_a_failed_safety_check_is_a_discard_criterion():
    result = inspection.score("Brake", {"brake_torque_test_passed": False, "air_gap_in_range": True})
    assert result["discard_criteria_met"] == ["Brake torque / holding test passed"]
    assert result["band"] == "red"


def test_insulation_resistance_is_scored_on_a_log_scale():
    good = inspection.score("Motor", {"insulation_resistance_mohm": 100})
    mid = inspection.score("Motor", {"insulation_resistance_mohm": 10})
    bad = inspection.score("Motor", {"insulation_resistance_mohm": 0.8})
    assert good["inspection_score"] == 100
    assert mid["inspection_score"] == pytest.approx(67.5)
    assert bad["discard_criteria_met"]


def test_unknown_measurement_is_refused():
    with pytest.raises(ValueError):
        inspection.score("Sheave", {"made_up_reading": 1})


def test_recorded_inspection_updates_the_component(client, component_payload):
    motor = _motor(client, component_payload)
    response = client.post(
        f"/api/v1/components/{motor['component_id']}/inspections",
        json={
            "measurements": {
                "insulation_resistance_mohm": 40,
                "bearing_vibration_mm_s": 4.2,
                "bearing_temperature_c": 62,
                "no_abnormal_noise": True,
            },
            "notes": "Routine visit",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["service_event"]["event_type"] == "INSPECTION"
    assert body["service_event"]["sensor_metadata"]["inspection_method"] == "measured-checklist-v1"

    record = client.get(f"/api/v1/components/{motor['component_id']}").json()
    assert record["inspection_score"] == body["inspection"]["inspection_score"]
    assert record["vibration"] == 4.2
    assert record["temperature"] == 62


# --------------------------------------------------------------- telemetry
def _readings(days=90, start=None):
    start = start or datetime(2026, 6, 1)
    return [
        {
            "recorded_at": (start + timedelta(days=i)).isoformat(),
            "trips": 300,
            "run_seconds": 300 * 22,
            "load_kg": 500,
            "vibration": 3.0 + 0.01 * i,
            "temperature": 55.0,
        }
        for i in range(days)
    ]


def test_telemetry_adds_counters_and_is_idempotent(client, component_payload):
    motor = _motor(client, component_payload)
    url = f"/api/v1/components/{motor['component_id']}/telemetry"
    batch = {"source": "iot-retrofit", "readings": _readings(30)}

    first = client.post(url, json=batch).json()
    assert first["accepted"] == 30
    assert first["trips_added"] == 9000
    assert first["component_updates"]["load_cycles"] == component_payload["load_cycles"] + 9000

    again = client.post(url, json=batch).json()
    assert again["accepted"] == 0 and again["duplicates_ignored"] == 30
    record = client.get(f"/api/v1/components/{motor['component_id']}").json()
    assert record["load_cycles"] == component_payload["load_cycles"] + 9000


def test_telemetry_rejects_impossible_rows(client, component_payload):
    motor = _motor(client, component_payload)
    future = (datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=30)).isoformat()
    body = client.post(
        f"/api/v1/components/{motor['component_id']}/telemetry",
        json={"source": "iot-retrofit", "readings": [
            {"recorded_at": future, "trips": 10},
            {"recorded_at": "2010-01-01T00:00:00", "trips": 10},
            {"recorded_at": "2026-06-01T00:00:00", "vibration": 3.1},
        ]},
    ).json()
    assert body["accepted"] == 1
    assert body["rejected_count"] == 2


def test_csv_upload_and_monthly_summary(client, component_payload):
    motor = _motor(client, component_payload)
    lines = ["recorded_at,trips,run_seconds,load_percent,vibration,temperature"]
    for row in _readings(60):
        lines.append(f"{row['recorded_at']},{row['trips']},{row['run_seconds']},46,{row['vibration']},{row['temperature']}")
    lines.append("not-a-date,1,1,1,1,1")
    response = client.post(
        f"/api/v1/components/{motor['component_id']}/telemetry/csv",
        files={"file": ("export.csv", "\n".join(lines), "text/csv")},
        data={"source": "controller-export"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["accepted"] == 60 and body["csv_error_count"] == 1
    assert body["load_applied"] is True

    summary = client.get(f"/api/v1/components/{motor['component_id']}/telemetry").json()
    assert summary["total_readings"] == 60
    assert summary["sources"][0]["source"] == "controller-export"
    assert len(summary["monthly"]) >= 2


def test_telemetry_feeds_the_early_warning_trend(client, component_payload):
    motor = _motor(client, component_payload)
    # Twelve months of steadily rising vibration from a sensor.
    readings = [
        {"recorded_at": (datetime(2025, 9, 15) + timedelta(days=30 * m)).isoformat(),
         "vibration": 2.0 + 0.35 * m, "temperature": 55.0}
        for m in range(12)
    ]
    client.post(
        f"/api/v1/components/{motor['component_id']}/telemetry",
        json={"source": "iot-retrofit", "readings": readings},
    )
    forecast = client.get(f"/api/v1/passports/{motor['component_id']}/life").json()["early_warning"]
    vibration = next(i for i in forecast["indicators"] if i["indicator"] == "vibration")
    assert vibration["points"] >= 8
    assert vibration["status"] in {"worsening", "exceeded"}
