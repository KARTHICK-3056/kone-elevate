"""P6 pilot metrics (app.services.pilot_service, GET /pilot/metrics).

Every metric here is exercised against real data created through the API in
each test - not fixtures asserting on a hand-built dict - so a broken query
shape fails the suite the same way test_dashboard.py's analytics regression
was caught.
"""

from __future__ import annotations


def test_pilot_metrics_endpoint_shape(client, created_component):
    response = client.get("/api/v1/pilot/metrics")
    assert response.status_code == 200, response.text
    body = response.json()
    for key in (
        "diversion_rate",
        "technician_trust_score",
        "mass_diverted",
    ):
        assert key in body
    # Computed from the removed Recovery Exchange; no longer reported.
    for key in ("recovered_parts_yield", "decision_reversal_rate", "value_recovered"):
        assert key not in body


def test_diversion_rate_counts_assessed_components(client, created_component):
    body = client.get("/api/v1/pilot/metrics").json()
    assert body["diversion_rate"]["assessed_components"] >= 1


def test_technician_trust_score_averages_ratings(client, created_component):
    prediction_id = created_component["latest_prediction"]["id"]
    client.post(f"/api/v1/predictions/{prediction_id}/feedback", json={"trust_rating": 5})
    body = client.get("/api/v1/pilot/metrics").json()
    trust = body["technician_trust_score"]
    assert trust["ratings_submitted"] >= 1
    assert 1 <= trust["average_rating_1_to_5"] <= 5


def test_mass_diverted_is_non_negative(client, created_component):
    body = client.get("/api/v1/pilot/metrics").json()
    assert body["mass_diverted"]["mass_diverted_kg"] >= 0
