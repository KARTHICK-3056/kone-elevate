"""Pre-emptive issue forecast (app.ml.early_warning) and its assessment wiring."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.ml import early_warning

TODAY = date(2026, 9, 24)


def _rope(**overrides):
    """A 7-year-old rope at design duty, healthy today."""
    base = {
        "component_type": "Steel Rope",
        "material": "Steel",
        "material_grade": None,
        "installation_date": date(2019, 9, 24),
        "operating_hours": 55000 / 12 * 7,
        "load_cycles": int(1400000 / 12 * 7),
        "average_load": 960,
        "vibration": 2.0,
        "temperature": 30.0,
        "inspection_score": 85.0,
        "repair_count": 0,
        "failure_history": 0,
        "last_service_date": TODAY - timedelta(days=30),
        "days_since_last_service": 30,
    }
    base.update(overrides)
    return base


def _history(indicator, start, step, visits=6, every_days=180):
    """Service readings ending just before today, changing by ``step`` per visit."""
    first = TODAY - timedelta(days=every_days * visits)
    return [
        {"event_date": first + timedelta(days=every_days * i), indicator: start + step * i}
        for i in range(visits)
    ]


def test_falling_inspection_trend_predicts_the_discard_date_before_it_arrives():
    # Score falls 5 points every 6 months: 95, 90, 85, 80, 75, 70 -> ~10/yr.
    events = _history("inspection_score", 95.0, -5.0)
    rope = _rope(inspection_score=65.0)
    result = early_warning.forecast(rope, events, today=TODAY)

    issue = next(i for i in result["issues"] if i["code"] == "ROPE_DISCARD_CRITERIA")
    assert issue["present"] is False
    assert 300 < issue["days_until"] < 900
    assert issue["evidence"]["kind"] == "trend"
    assert issue["evidence"]["r2"] > 0.9
    # Act-by leaves the rope lead time before the predicted date.
    assert (date.fromisoformat(issue["predicted_date"]) - date.fromisoformat(issue["act_by"])).days == 60
    assert issue["measures"]
    assert "predicted ahead" in result["headline"]


def test_stable_readings_raise_nothing():
    events = _history("inspection_score", 86.0, 0.0)
    result = early_warning.forecast(_rope(inspection_score=86.0), events, today=TODAY)
    assert not [i for i in result["issues"] if i["code"] == "ROPE_DISCARD_CRITERIA"]
    status = next(i for i in result["indicators"] if i["indicator"] == "inspection_score")
    assert status["status"] == "stable"


def test_too_little_history_is_reported_not_extrapolated():
    events = _history("vibration", 2.0, 0.5, visits=2)
    result = early_warning.forecast(_rope(last_service_date=None), events, today=TODAY)
    status = next(i for i in result["indicators"] if i["indicator"] == "vibration")
    assert status["status"] == "insufficient_history"


def test_a_crossed_limit_is_labelled_present_not_predicted():
    events = _history("vibration", 4.0, 0.5)  # 4.0 -> 6.5, limit 5.5
    result = early_warning.forecast(_rope(vibration=7.0), events, today=TODAY)
    issue = next(i for i in result["issues"] if i["code"] == "ROPE_TENSION_IMBALANCE")
    assert issue["present"] is True
    assert issue["urgency"] == "PRESENT"
    assert "already crossed" in result["headline"]


def test_confidence_rises_when_independent_signals_agree():
    events = _history("inspection_score", 95.0, -5.0)
    quiet = early_warning.forecast(
        _rope(inspection_score=65.0), events, latest_recommendation="CONTINUE_USING",
        survival_probability_12m=0.05, today=TODAY,
    )
    loud = early_warning.forecast(
        _rope(inspection_score=65.0, repair_count=2), events, latest_recommendation="COMPONENT_RECOVERY",
        survival_probability_12m=0.6, today=TODAY,
    )
    code = "ROPE_DISCARD_CRITERIA"
    quiet_issue = next(i for i in quiet["issues"] if i["code"] == code)
    loud_issue = next(i for i in loud["issues"] if i["code"] == code)
    assert loud_issue["confidence"] > quiet_issue["confidence"]
    signals = {s["signal"]: s["agrees"] for s in loud_issue["justification"]}
    assert signals["AI recommendation (classifier and decision flow)"] is True
    assert signals["Survival model (fleet statistics)"] is True
    assert signals["Service record"] is True


def test_usage_life_milestone_becomes_an_issue_within_the_horizon():
    # Ten years into a twelve-year design life: the replace band (80%) is close.
    rope = _rope(
        installation_date=date(2016, 9, 24),
        operating_hours=55000 / 12 * 10,
        load_cycles=int(1400000 / 12 * 10),
        inspection_score=90.0,
    )
    result = early_warning.forecast(rope, [], today=TODAY)
    issue = next(i for i in result["issues"] if i["code"] == "ROPE_END_OF_LIFE")
    assert issue["evidence"]["kind"] == "life"
    assert issue["safety_critical"] is True


def test_other_component_types_are_declined():
    result = early_warning.forecast({"component_type": "Handrail"}, [], today=TODAY)
    assert result["supported"] is False


def test_audit_summary_records_what_was_predicted():
    events = _history("inspection_score", 95.0, -5.0)
    summary = early_warning.audit_summary(
        early_warning.forecast(_rope(inspection_score=65.0), events, today=TODAY)
    )
    assert summary and {"code", "predicted_date", "act_by", "confidence", "present"} <= set(summary[0])


# --------------------------------------------------------------- API wiring
def test_assessment_returns_the_forecast_and_audits_it(client, component_payload):
    created = client.post("/api/v1/components", json=component_payload).json()
    component_id = created["component_id"]
    body = client.post(f"/api/v1/components/{component_id}/predict").json()
    assert body["early_warning"]["supported"] is True
    assert "headline" in body["early_warning"]

    audit = client.get(
        "/api/v1/audit", params={"entity_type": "component", "action": "PREDICT", "page_size": 200}
    ).json()
    predicts = [e for e in audit["items"] if e["entity_id"] == component_id]
    assert predicts and "predicted_issues" in predicts[0]["data_snapshot"]


def test_life_endpoint_carries_the_forecast(client, created_component):
    body = client.get(f"/api/v1/passports/{created_component['component_id']}/life").json()
    assert body["early_warning"]["supported"] is True


@pytest.mark.parametrize("component_type", ["Motor", "Sheave", "Brake", "Steel Rope"])
def test_every_focus_type_has_failure_modes_and_lead_time(component_type):
    assert component_type in early_warning.FAILURE_MODES
    assert "life" in early_warning.FAILURE_MODES[component_type]
    assert component_type in early_warning.LEAD_TIME_DAYS
