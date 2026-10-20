"""Interactive lift simulation (app.simulation) and its API."""

from __future__ import annotations

from datetime import date

import pytest

from app.ml.features import FEATURE_COLUMNS
from app.simulation import engine
from app.simulation import reference as ref

START = date(2026, 9, 24)


def _run(load_kg: float, years: int, seed: int = 7):
    state = engine.new_state(seed=seed, start=START)
    result = None
    for _ in range(years // 2):
        result = engine.advance(state, load_kg, 24)
        state = result["state"]
    return result


def test_the_load_is_the_only_input_and_all_13_parameters_are_derived():
    result = engine.advance(None, 460, 12)
    for component in result["results"]["components"].values():
        assert set(component["parameters"]) == set(FEATURE_COLUMNS)
        assert len(component["parameters"]) == 13
    assert set(engine.parameter_basis()) == set(FEATURE_COLUMNS)


def test_same_seed_same_story():
    a = _run(600, 6)
    b = _run(600, 6)
    assert a["state"]["components"] == b["state"]["components"]


def test_heavier_load_wears_rope_and_sheave_faster():
    light = engine.advance(engine.new_state(start=START), 200, 24)["results"]["components"]
    heavy = engine.advance(engine.new_state(start=START), 1000, 24)["results"]["components"]
    for component_type in ("Steel Rope", "Sheave"):
        assert heavy[component_type]["truth"]["wear"] > light[component_type]["truth"]["wear"]


def test_simulated_parts_are_the_four_focus_components():
    assert list(engine.COMPONENTS) == ["Motor", "Steel Rope", "Sheave", "Governor"]


def test_governor_feels_load_only_weakly():
    # Its rope is tensioned by the pit weight, not the car: a full car moves
    # the governor's equivalent stress far less than the rope's.
    governor = engine.equivalent_ratio("Governor", 1000, 460, 0.7)
    rope = engine.equivalent_ratio("Steel Rope", 1000, 460, 0.7)
    assert 1.0 < governor < rope


def test_motor_stress_is_lowest_near_the_counterweight_balance():
    ratios = {load: engine.equivalent_ratio("Motor", load, 460, 0.7) for load in (0, 500, 1000)}
    assert ratios[500] < ratios[0]
    assert ratios[500] < ratios[1000]


def test_full_load_motor_runs_near_not_far_past_its_limit():
    result = engine.advance(engine.new_state(start=START), 1000, 12)
    temperature = result["results"]["components"]["Motor"]["truth"]["temperature"]
    assert 80 < temperature < 95


def test_the_models_see_observations_not_the_truth():
    result = _run(460, 4)
    motor = result["state"]["components"]["Motor"]
    # Readings exist only for service visits (every 6 months).
    months = [reading["month"] for reading in motor["readings"]]
    assert all(b - a == ref.SERVICE_INTERVAL_MONTHS for a, b in zip(months, months[1:], strict=False))


def test_predictions_drive_maintenance_and_record_their_lead_time():
    result = _run(1000, 20)
    kpis = result["results"]["kpis"]
    assert kpis["proactive_replacements"] > 0
    assert kpis["warnings_raised"] > 0
    kinds = {event["kind"] for event in result["state"]["events"]}
    assert {"warning", "replace_proactive"} <= kinds
    assert kpis["average_warning_lead_months"] is not None


def test_series_carries_true_and_estimated_wear_per_month():
    result = engine.advance(None, 460, 6)
    assert [point["month"] for point in result["series"]] == [1, 2, 3, 4, 5, 6]
    assert {"true_wear", "estimated"} <= set(result["series"][-1]["Motor"])


def test_ai_classifier_runs_at_service_visits():
    result = engine.advance(None, 460, 6)
    assert all(c["ai"] for c in result["results"]["components"].values())


def test_reference_says_where_every_value_comes_from():
    profile = ref.reference_profile()
    sources = {
        item["source"]
        for group in ("lift", "traffic", "environment")
        for item in profile[group].values()
    }
    assert sources <= {"kone_api", "standard", "physics", "assumption"}
    # No credentials in the test environment: the values are the recorded examples.
    assert profile["api_values_are_real"] is False


@pytest.mark.parametrize("load", [-1, ref.MAX_LOAD_KG + 1])
def test_load_outside_the_lift_rating_is_refused(load):
    with pytest.raises(ValueError):
        engine.advance(None, load, 1)


def test_tampered_state_is_refused():
    state = engine.new_state(start=START)
    del state["components"]["Governor"]
    with pytest.raises(ValueError):
        engine.advance(state, 460, 1)


# --------------------------------------------------------------- API
def test_api_round_trip(client):
    reference = client.get("/api/v1/simulation/reference").json()
    assert reference["components"] == list(engine.COMPONENTS)

    first = client.post("/api/v1/simulation/advance", json={"load_kg": 460, "months": 6})
    assert first.status_code == 200, first.text
    second = client.post(
        "/api/v1/simulation/advance",
        json={"state": first.json()["state"], "load_kg": 800, "months": 3},
    ).json()
    assert second["results"]["month"] == 9
    assert second["results"]["load_kg"] == 800


def test_api_rejects_overload(client):
    response = client.post("/api/v1/simulation/advance", json={"load_kg": 5000, "months": 1})
    assert response.status_code == 422


def test_api_requires_sign_in(anonymous_client):
    assert anonymous_client.get("/api/v1/simulation/reference").status_code == 401


# --------------------------------------------------------------------------
# KONE API first; simulate only what KONE does not publish
# --------------------------------------------------------------------------
def test_month_zero_starts_from_the_kone_record():
    record = ref.kone_record()
    state = engine.new_state(start=START)
    start = record["start"]
    for component in state["components"].values():
        assert component["service_count"] == start["service_count"]
        assert component["repair_count"] == start["repair_count"]
        assert component["failure_history"] == start["failure_history"]
        parameters = engine.parameters(state, component)
        assert parameters["inspection_score"] == start["inspection_score"]
        assert parameters["days_since_last_service"] == pytest.approx(start["days_since_last_service"], abs=1)


def test_only_vibration_temperature_and_age_are_simulated_from_the_start():
    basis = engine.parameter_basis()
    simulated = {name for name, row in basis.items() if row["source"] == "simulated"}
    assert simulated == {"vibration", "temperature", "component_age"}
    kone = {name for name, row in basis.items() if row["source"] == "kone_api"}
    assert kone == {
        "operating_hours", "load_cycles", "average_load", "service_count", "repair_count",
        "failure_history", "inspection_score", "days_since_last_service",
    }


def test_thin_kone_data_falls_back_and_says_so():
    """The recorded example orders hold one preventive visit over ~6 months:
    no interval or fault rate can be derived, and the notes say why."""
    record = ref.kone_record()
    assert record["rates"]["service_interval_months"] is None
    assert "too few" in record["notes"]["service_interval_months"]
    assert record["rates"]["callout_rate_per_month"] is None
    assert "too short" in record["notes"]["callout_rate_per_month"]


def test_a_run_from_a_real_component_does_not_borrow_the_kone_lift():
    state = engine.new_state(start=START, from_kone=False)
    assert state["kone_start"] is None
    assert all(c["service_count"] == 0 for c in state["components"].values())
