"""Prediction, health score, explainability and safety-gate tests."""

from __future__ import annotations

import pytest

from app.ml import abstention
from app.ml.predict import predict_disposition
from app.services.health_service import compute_health

VALID_RECOMMENDATIONS = {"CONTINUE_USING", "COMPONENT_RECOVERY", "MATERIAL_RECOVERY", "DISPOSE"}


# --------------------------------------------------------------------------
# API
# --------------------------------------------------------------------------
def test_predict_returns_a_complete_explainable_assessment(client, prediction_payload):
    response = client.post("/api/v1/predict", json=prediction_payload)
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["recommendation"] in VALID_RECOMMENDATIONS
    assert 0.0 <= body["confidence"] <= 1.0
    assert 0.0 <= body["health_score"] <= 100.0
    assert body["health_band"] in {"EXCELLENT", "GOOD", "FAIR", "POOR", "CRITICAL"}
    assert body["model_version"]
    assert body["safety_flag"] is False

    assert len(body["key_factors"]) >= 1
    for factor in body["key_factors"]:
        assert factor["factor"]
        assert factor["impact"] in {"positive", "low", "moderate", "high", "critical"}
        assert factor["description"]

    # Honest-language guarantees.
    assert "advisory" in body["disclaimer"].lower()
    assert "synthetic" in body["data_notice"].lower()
    assert "shap" in body["explanation_method"].lower()


def test_predict_probabilities_are_a_distribution(client, prediction_payload):
    body = client.post("/api/v1/predict", json=prediction_payload).json()
    if not body["model_available"]:
        pytest.skip("No trained model available in this environment")
    assert set(body["probabilities"]) <= VALID_RECOMMENDATIONS
    assert sum(body["probabilities"].values()) == pytest.approx(1.0, abs=0.01)
    assert body["confidence"] == pytest.approx(max(body["probabilities"].values()), abs=1e-6)


def test_predict_rejects_invalid_payloads(client, prediction_payload):
    assert client.post("/api/v1/predict", json={}).status_code == 422

    bad_type = {**prediction_payload, "component_type": "Warp Core"}
    assert client.post("/api/v1/predict", json=bad_type).status_code == 422

    bad_material = {**prediction_payload, "material": "Unobtainium"}
    assert client.post("/api/v1/predict", json=bad_material).status_code == 422

    negative_vibration = {**prediction_payload, "vibration": -3}
    assert client.post("/api/v1/predict", json=negative_vibration).status_code == 422

    bad_inspection = {**prediction_payload, "inspection_score": 101}
    assert client.post("/api/v1/predict", json=bad_inspection).status_code == 422


@pytest.mark.parametrize("component_type", ["Steel Rope", "Brake", "Governor"])
def test_safety_gate_flags_every_safety_critical_type(client, prediction_payload, component_type):
    """Even a pristine safety-critical component must require human inspection."""
    payload = {
        **prediction_payload,
        "component_type": component_type,
        "material": "Steel",
        "component_age": 1.0,
        "operating_hours": 2500,
        "load_cycles": 60000,
        "vibration": 0.9,
        "temperature": 30,
        "repair_count": 0,
        "failure_history": 0,
        "inspection_score": 98,
        "days_since_last_service": 15,
    }
    body = client.post("/api/v1/predict", json=payload).json()

    assert body["safety_flag"] is True
    assert body["safety_message"] == "MANDATORY HUMAN INSPECTION"
    assert "human inspection required" in body["safety_note"].lower()
    # The AI output is still reported - the gate never silently overrides it.
    assert body["recommendation"] in VALID_RECOMMENDATIONS


def test_safety_gate_is_not_applied_to_ordinary_components(client, prediction_payload):
    body = client.post(
        "/api/v1/predict", json={**prediction_payload, "component_type": "Door Operator"}
    ).json()
    assert body["safety_flag"] is False
    assert body["safety_message"] is None


def test_component_assessment_is_persisted_and_audited(client, created_component):
    component_id = created_component["component_id"]

    response = client.post(f"/api/v1/components/{component_id}/predict")
    assert response.status_code == 200
    body = response.json()
    assert body["component_id"] == component_id
    assert body["prediction_id"] is not None
    assert body["impact"]["estimated_recovery_value"] >= 0

    history = client.get(f"/api/v1/components/{component_id}/predictions").json()
    assert history["total"] >= 2  # creation assessment + this one

    trail = client.get(f"/api/v1/audit/component/{component_id}").json()
    assert any(entry["action"] == "PREDICT" for entry in trail)


def test_predict_for_missing_component_returns_404(client):
    assert client.post("/api/v1/components/KE-NOPE-000000/predict").status_code == 404


def test_batch_prediction(client, prediction_payload):
    response = client.post(
        "/api/v1/predict/batch",
        json=[prediction_payload, {**prediction_payload, "component_type": "Brake"}],
    )
    assert response.status_code == 200
    results = response.json()
    assert len(results) == 2
    assert results[1]["safety_flag"] is True


def test_model_info_and_metrics_endpoints(client):
    info = client.get("/api/v1/model/info").json()
    assert info["data_source"] == "synthetic"
    assert "synthetic" in info["data_notice"].lower()

    importance = client.get("/api/v1/model/feature-importance").json()
    assert "shap" in importance["method"].lower()
    if info["model_available"]:
        assert len(importance["gini"]) >= 10
        assert len(importance["permutation"]) >= 10
        assert len(importance["shap"]) >= 10
        metrics = client.get("/api/v1/model/metrics").json()
        assert 0.0 < metrics["accuracy"] <= 1.0
        assert metrics["data_source"] == "synthetic"

        calibration = client.get("/api/v1/model/calibration").json()
        assert calibration["model_available"] is True
        bins = calibration["reliability"]["bins"]
        assert sum(bin_["count"] for bin_ in bins) == metrics["test_records"]
        assert 0.0 <= calibration["reliability"]["expected_calibration_error"] <= 1.0
        assert 0.0 <= calibration["abstention"]["abstention_rate"] <= 1.0


# --------------------------------------------------------------------------
# Health score and degradation ordering
# --------------------------------------------------------------------------
def test_health_score_breakdown_is_transparent_and_bounded():
    result = compute_health(
        {
            "component_type": "Motor",
            "material": "Steel",
            "component_age": 5.2,
            "operating_hours": 18000,
            "load_cycles": 140000,
            "average_load": 650,
            "vibration": 3.8,
            "temperature": 52,
            "service_count": 5,
            "repair_count": 1,
            "failure_history": 0,
            "inspection_score": 82,
            "days_since_last_service": 90,
        }
    )
    assert 0.0 <= result["health_score"] <= 100.0
    assert len(result["breakdown"]) == 10
    assert sum(item["weight"] for item in result["breakdown"]) == pytest.approx(1.0)
    assert "requires engineering validation" in result["methodology"]


def test_worse_condition_produces_a_lower_health_score():
    good = {
        "component_type": "Motor",
        "material": "Steel",
        "component_age": 2.0,
        "operating_hours": 6000,
        "load_cycles": 120000,
        "average_load": 400,
        "vibration": 1.2,
        "temperature": 38,
        "service_count": 5,
        "repair_count": 0,
        "failure_history": 0,
        "inspection_score": 96,
        "days_since_last_service": 30,
    }
    bad = {
        **good,
        "component_age": 24.0,
        "operating_hours": 105000,
        "load_cycles": 2100000,
        "vibration": 9.5,
        "temperature": 88,
        "repair_count": 7,
        "failure_history": 4,
        "inspection_score": 18,
        "days_since_last_service": 900,
    }
    assert compute_health(good)["health_score"] > compute_health(bad)["health_score"]
    assert compute_health(bad)["health_score"] < 45


@pytest.mark.ml
def test_degraded_component_is_never_recommended_for_reuse():
    result = predict_disposition(
        {
            "component_type": "Sheave",
            "material": "Cast Iron",
            "component_age": 22.0,
            "operating_hours": 88000,
            "load_cycles": 1800000,
            "average_load": 1500,
            "vibration": 5.8,
            "temperature": 70,
            "service_count": 9,
            "repair_count": 6,
            "failure_history": 4,
            "inspection_score": 19,
            "days_since_last_service": 760,
        }
    )
    assert result["recommendation"] in {"MATERIAL_RECOVERY", "DISPOSE"}
    assert result["health_score"] < 45


@pytest.mark.ml
def test_healthy_component_is_recommended_for_reuse():
    result = predict_disposition(
        {
            "component_type": "Motor",
            "material": "Steel",
            "component_age": 3.0,
            "operating_hours": 9600,
            "load_cycles": 190000,
            "average_load": 520,
            "vibration": 1.6,
            "temperature": 42,
            "service_count": 7,
            "repair_count": 0,
            "failure_history": 0,
            "inspection_score": 94,
            "days_since_last_service": 45,
        }
    )
    assert result["recommendation"] == "CONTINUE_USING"
    assert result["health_score"] > 85
    assert result["safety_flag"] is False


# --------------------------------------------------------------------------
# Abstention (DEFER_TO_INSPECTION)
# --------------------------------------------------------------------------
def test_abstention_triggers_below_the_confidence_threshold():
    probabilities = {"CONTINUE_USING": 0.3, "COMPONENT_RECOVERY": 0.3, "MATERIAL_RECOVERY": 0.25, "DISPOSE": 0.15}
    decision = abstention.decide(probabilities, q_hat=0.0)  # q_hat=0 -> conformal set is always singleton
    assert decision["abstain"] is True
    assert decision["trigger"] == "low_confidence"
    assert decision["argmax_class"] == "CONTINUE_USING"


def test_abstention_triggers_on_an_ambiguous_conformal_set():
    probabilities = {"CONTINUE_USING": 0.55, "COMPONENT_RECOVERY": 0.45, "MATERIAL_RECOVERY": 0.0, "DISPOSE": 0.0}
    # q_hat=0.6 -> prediction set includes every class with P >= 1 - 0.6 = 0.4, i.e. both.
    # Top confidence (0.55) is still above CONFIDENCE_THRESHOLD, isolating this to the
    # conformal-set trigger specifically.
    decision = abstention.decide(probabilities, q_hat=0.6)
    assert decision["abstain"] is True
    assert decision["trigger"] == "ambiguous_prediction_set"
    assert set(decision["prediction_set"]) == {"CONTINUE_USING", "COMPONENT_RECOVERY"}


def test_no_abstention_for_a_clear_cut_high_confidence_case():
    probabilities = {"CONTINUE_USING": 0.95, "COMPONENT_RECOVERY": 0.05, "MATERIAL_RECOVERY": 0.0, "DISPOSE": 0.0}
    decision = abstention.decide(probabilities, q_hat=0.1)
    assert decision["abstain"] is False
    assert decision["trigger"] == "none"
    assert decision["prediction_set"] == ["CONTINUE_USING"]


def test_prediction_never_claims_certification(client, prediction_payload):
    """Guard against unsupported claims creeping into the API surface."""
    body = client.post("/api/v1/predict", json=prediction_payload).json()
    text = " ".join(
        [body["disclaimer"], body["safety_note"], body["data_notice"], body["health_methodology"]]
    ).lower()
    for forbidden in ("100% accurate", "guaranteed safe", "ai approved", "certified safe"):
        assert forbidden not in text
