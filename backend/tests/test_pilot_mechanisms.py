"""P6 pilot mechanisms: shadow mode and technician trust rating.

None of these have real removals or a real pilot behind them yet - what is
tested here is that the mechanism itself is correct, so it is ready the
moment real data starts flowing through it. See docs/shadow-mode.md and
docs/pilot-protocol.md for the honest scope.
"""

from __future__ import annotations


# --------------------------------------------------------------------------
# Shadow mode
# --------------------------------------------------------------------------
def test_shadow_assessment_does_not_change_the_displayed_recommendation(
    client, created_component
):
    component_id = created_component["component_id"]
    before = client.get(f"/api/v1/components/{component_id}").json()

    shadow = client.post(f"/api/v1/components/{component_id}/predict/shadow")
    assert shadow.status_code == 200, shadow.text
    assert shadow.json()["shadow"] is True

    after = client.get(f"/api/v1/components/{component_id}").json()
    assert after["latest_prediction"]["recommendation"] == before["latest_prediction"]["recommendation"]
    assert after["latest_prediction"]["predicted_at"] == before["latest_prediction"]["predicted_at"]


def test_shadow_assessment_is_excluded_from_recent_predictions(client, created_component):
    component_id = created_component["component_id"]
    shadow = client.post(f"/api/v1/components/{component_id}/predict/shadow").json()

    recent = client.get("/api/v1/predictions/recent?limit=100").json()
    assert all(entry["id"] != shadow["prediction_id"] for entry in recent)


def test_shadow_assessment_still_appears_in_full_prediction_history(client, created_component):
    component_id = created_component["component_id"]
    shadow = client.post(f"/api/v1/components/{component_id}/predict/shadow").json()

    history = client.get(f"/api/v1/components/{component_id}/predictions").json()
    assert any(item["id"] == shadow["prediction_id"] for item in history["items"])


# --------------------------------------------------------------------------
# Technician trust rating
# --------------------------------------------------------------------------
def test_rating_a_prediction_stores_the_score(client, created_component):
    prediction_id = created_component["latest_prediction"]["id"]
    response = client.post(
        f"/api/v1/predictions/{prediction_id}/feedback",
        json={"trust_rating": 4, "notes": "Matches what I saw on inspection."},
    )
    assert response.status_code == 200, response.text
    assert response.json()["trust_rating"] == 4


def test_rating_an_unknown_prediction_404s(client):
    response = client.post("/api/v1/predictions/999999/feedback", json={"trust_rating": 3})
    assert response.status_code == 404


def test_rating_out_of_range_is_rejected(client, created_component):
    prediction_id = created_component["latest_prediction"]["id"]
    response = client.post(
        f"/api/v1/predictions/{prediction_id}/feedback", json={"trust_rating": 7}
    )
    assert response.status_code == 422
