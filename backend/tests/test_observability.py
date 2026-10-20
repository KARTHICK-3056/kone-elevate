"""Request-id propagation and the Prometheus /metrics endpoint (P4)."""

from __future__ import annotations


def test_every_response_carries_a_request_id(anonymous_client):
    response = anonymous_client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.headers.get("X-Request-ID")


def test_a_supplied_request_id_is_echoed_back(anonymous_client):
    response = anonymous_client.get(
        "/api/v1/health", headers={"X-Request-ID": "test-fixed-id-123"}
    )
    assert response.headers.get("X-Request-ID") == "test-fixed-id-123"


def test_metrics_endpoint_is_public_and_prometheus_shaped(anonymous_client):
    response = anonymous_client.get("/api/v1/metrics")
    assert response.status_code == 200
    body = response.text
    assert "prediction_latency_seconds" in body
    assert "predictions_total" in body
    assert "audit_chain_verification_valid" in body


def test_predicting_increments_the_metrics_counter(client, prediction_payload):
    before = client.get("/api/v1/metrics").text
    response = client.post("/api/v1/predict", json=prediction_payload)
    assert response.status_code == 200, response.text
    after = client.get("/api/v1/metrics").text
    assert before != after


def test_verifying_the_chain_updates_the_gauge(client):
    response = client.get("/api/v1/audit/verify")
    assert response.status_code == 200
    metrics = client.get("/api/v1/metrics").text
    assert "audit_chain_verification_valid 1.0" in metrics
