"""Portfolio command centre endpoints.

There was previously no dedicated test file for this router at all - a real
gap, found the hard way while rewriting its aggregation queries for P4:
``GET /dashboard/analytics`` had a live ``NameError`` (a stale
``health_band`` reference left behind by an import cleanup) that the rest
of the suite never exercised, because nothing here ever called it. Every
endpoint below gets at least one smoke-tested call so a broken query shape
fails the suite instead of shipping.
"""

from __future__ import annotations


def test_summary_reflects_a_created_component(client, created_component):
    response = client.get("/api/v1/dashboard/summary")
    assert response.status_code == 200
    body = response.json()
    assert body["total_components"] >= 1
    assert body["assessed_components"] >= 1


def test_disposition_breakdown(client, created_component):
    response = client.get("/api/v1/dashboard/disposition")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] + body["unassessed"] >= 1


def test_health_distribution_has_buckets_and_bands(client, created_component):
    response = client.get("/api/v1/dashboard/health-distribution")
    assert response.status_code == 200
    body = response.json()
    assert len(body["buckets"]) == 5
    assert len(body["bands"]) == 5
    assert body["assessed"] >= 1


def test_component_types_breakdown(client, created_component):
    response = client.get("/api/v1/dashboard/component-types")
    assert response.status_code == 200
    assert response.json()["total"] >= 1


def test_lifecycle_breakdown(client, created_component):
    response = client.get("/api/v1/dashboard/lifecycle")
    assert response.status_code == 200
    assert response.json()["total"] >= 1


def test_confidence_distribution(client, created_component):
    response = client.get("/api/v1/dashboard/confidence")
    assert response.status_code == 200
    body = response.json()
    assert len(body["buckets"]) == 5
    assert body["total"] >= 1


def test_monthly_activity(client, created_component):
    response = client.get("/api/v1/dashboard/monthly-activity?months=6")
    assert response.status_code == 200
    assert isinstance(response.json()["items"], list)


def test_recovery_value_by_type(client, created_component):
    response = client.get("/api/v1/dashboard/recovery-value")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_impact_summary(client, created_component):
    response = client.get("/api/v1/dashboard/impact")
    assert response.status_code == 200
    body = response.json()
    assert "total_recovery_value" in body
    assert "constants" in body


def test_safety_queue(client, created_component):
    response = client.get("/api/v1/dashboard/safety-queue")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_analytics_combined_payload(client, created_component):
    """The one endpoint that had a live NameError with no test to catch it."""
    response = client.get("/api/v1/dashboard/analytics")
    assert response.status_code == 200, response.text
    body = response.json()
    for key in (
        "summary",
        "disposition",
        "health",
        "component_types",
        "lifecycle",
        "confidence",
        "monthly_activity",
        "impact",
        "recovery_value_by_type",
        "safety_queue",
        "feature_importance",
    ):
        assert key in body
    assert body["health"]["assessed"] >= 1
    assert body["confidence"]["total"] >= 1


def test_analytics_with_filters_applied(client, created_component):
    response = client.get(
        "/api/v1/dashboard/analytics",
        params={"component_type": "Motor", "all_units": "true"},
    )
    assert response.status_code == 200
    assert response.json()["filters_applied"]["component_type"] == ["Motor"]


def test_analytics_filters_reach_the_safety_queue_and_activity(client, component_payload):
    """The page's filters applied only to the counters - a Motor filter still
    listed every rope and governor in the safety queue."""
    for component_type in ("Motor", "Governor"):
        created = client.post("/api/v1/components", json={**component_payload, "component_type": component_type})
        assert created.status_code == 201, created.text

    unfiltered = client.get("/api/v1/dashboard/analytics", params={"all_units": "true"}).json()
    assert any(row["component_type"] == "Governor" for row in unfiltered["safety_queue"])

    motors = client.get(
        "/api/v1/dashboard/analytics", params={"component_type": "Motor", "all_units": "true"}
    ).json()
    assert motors["safety_queue"] == []
    governors = client.get(
        "/api/v1/dashboard/analytics", params={"component_type": "Governor", "all_units": "true"}
    ).json()
    assert {row["component_type"] for row in governors["safety_queue"]} == {"Governor"}


def test_monthly_activity_covers_every_month_in_the_window(client, created_component):
    items = client.get("/api/v1/dashboard/monthly-activity?months=6").json()["items"]
    months = [item["month"] for item in items]
    # Exactly six consecutive calendar months, empty ones included, ending this month.
    assert len(months) == 6
    assert months == sorted(set(months))
    for earlier, later in zip(months, months[1:], strict=False):
        year, month = int(earlier[:4]), int(earlier[5:])
        assert later == (f"{year:04d}-{month + 1:02d}" if month < 12 else f"{year + 1:04d}-01")


def test_dashboard_requires_authentication(anonymous_client):
    assert anonymous_client.get("/api/v1/dashboard/summary").status_code == 401
    assert anonymous_client.get("/api/v1/dashboard/analytics").status_code == 401
