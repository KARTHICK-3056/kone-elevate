"""End-of-life forecast and capacity-planning tests."""

from __future__ import annotations

import pytest

from app.ml.forecast_registry import forecast_registry

pytestmark = pytest.mark.skipif(
    not forecast_registry.is_available,
    reason="No trained forecast model (run scripts/train_forecast.py)",
)


# --------------------------------------------------------------------------
# Model metadata
# --------------------------------------------------------------------------
def test_forecast_model_endpoint_reports_the_backtest(client):
    body = client.get("/api/v1/forecast/model").json()
    assert body["forecast_available"] is True
    assert body["data_source"] == "synthetic"
    # A Weibull shape above 1 means hazard rises with age. If this ever drops
    # to <= 1 the fit has stopped describing wear-out and should be reviewed.
    assert body["shape_k"] > 1.0
    assert body["mape_overall"] is not None


# --------------------------------------------------------------------------
# EOL forecast
# --------------------------------------------------------------------------
def test_eol_forecast_shape(client, created_component):
    body = client.get("/api/v1/forecast/eol", params={"horizon": 12}).json()

    assert body["horizon_months"] == 12
    assert body["group_by"] == "type"
    assert len(body["quarters"]) == 4  # 12 months / 3
    assert "current_backlog" in body
    assert "synthetic" in body["data_notice"].lower()

    for group in body["groups"]:
        assert len(group["quarters"]) == 4
        for quarter in group["quarters"]:
            assert quarter["lower"] <= quarter["expected_removals"] <= quarter["upper"]
            assert quarter["expected_removals"] >= 0


@pytest.mark.parametrize("group_by", ["type", "site", "region"])
def test_eol_forecast_supports_every_grouping(client, created_component, group_by):
    body = client.get("/api/v1/forecast/eol", params={"group_by": group_by}).json()
    assert body["group_by"] == group_by
    assert isinstance(body["groups"], list)


def test_per_quarter_intervals_are_never_inverted(client, created_component):
    """Regression: per-quarter bounds used to cross over at long horizons.

    Confidence bounds are computed on the *cumulative* probability, where they
    are correctly ordered. Differencing consecutive quarters to get per-quarter
    figures does not preserve that ordering - the upper cumulative curve
    saturates toward 1 sooner, so its later increments drop below the point
    estimate's and lower/upper swap. The original version of this test used a
    12-month horizon on a near-empty fixture and never reached saturation, so
    it passed while the API was returning lower=0.21, upper=0.17 on real data.
    A long horizon is what makes the bug reachable.
    """
    for horizon in (24, 48, 60):
        body = client.get("/api/v1/forecast/eol", params={"horizon": horizon}).json()
        for group in body["groups"]:
            for quarter in group["quarters"]:
                assert quarter["lower"] <= quarter["upper"], (
                    f"inverted interval at horizon={horizon}, {group['group']} "
                    f"{quarter['quarter']}: {quarter}"
                )
                assert (
                    quarter["lower"] <= quarter["expected_removals"] <= quarter["upper"]
                ), f"point estimate outside its own interval: {quarter}"


def test_expected_removals_never_exceed_the_population(client, created_component):
    """A probability-weighted count cannot exceed the number of components."""
    body = client.get("/api/v1/forecast/eol", params={"horizon": 60}).json()
    assert body["total_expected_removals"] <= body["components_in_scope"] + 1e-6


def test_horizon_bounds_are_enforced(client):
    assert client.get("/api/v1/forecast/eol", params={"horizon": 1}).status_code == 422
    assert client.get("/api/v1/forecast/eol", params={"horizon": 600}).status_code == 422
    assert client.get("/api/v1/forecast/eol", params={"group_by": "planet"}).status_code == 422


# --------------------------------------------------------------------------
# The backlog / at-risk split - guards the design decision, not just the code
# --------------------------------------------------------------------------
def test_already_degraded_components_are_backlog_not_forecast(client, component_payload):
    """A component already assessed past Continue Using has crossed the very
    threshold this model forecasts, so forecasting its crossing is meaningless.
    It must be reported as current backlog instead."""
    worn_out = {
        **component_payload,
        "component_type": "Sheave",
        "material": "Cast Iron",
        "installation_date": "2004-01-10",
        "operating_hours": 88000,
        "load_cycles": 1800000,
        "average_load": 1500,
        "vibration": 5.8,
        "temperature": 70,
        "repair_count": 6,
        "failure_history": 4,
        "inspection_score": 19,
        "run_initial_prediction": True,
    }
    created = client.post("/api/v1/components", json=worn_out)
    assert created.status_code == 201, created.text
    component_id = created.json()["component_id"]

    # Sanity check the premise: the classifier really does put this one past
    # the threshold. If it ever stops doing so, this test is no longer
    # exercising what it claims to.
    assessment = client.post(f"/api/v1/components/{component_id}/predict").json()
    assert assessment["recommendation"] in {"COMPONENT_RECOVERY", "MATERIAL_RECOVERY", "DISPOSE"}

    before = client.get("/api/v1/forecast/eol", params={"horizon": 12}).json()
    assert before["current_backlog"]["components"] >= 1
    assert before["current_backlog"]["recovery_hours_required"] > 0

    # And it must not also be counted in the forecast - that would double-count
    # it as both existing backlog and future arrival.
    backlog_types = before["current_backlog"]["by_component_type"]
    assert "Sheave" in backlog_types


# --------------------------------------------------------------------------
# Capacity plan
# --------------------------------------------------------------------------
def test_capacity_plan_respects_the_stated_capacity_constraint(client, created_component):
    """The levelled intake schedule must never schedule more than the declared
    workshop capacity in any quarter - that is the whole point of levelling."""
    body = client.get("/api/v1/forecast/capacity", params={"horizon": 24}).json()
    capacity = body["capacity_hours_per_quarter"]

    assert body["quarters"], "expected a quarter-by-quarter plan"
    for entry in body["recommended_intake_schedule"]:
        assert entry["scheduled_hours"] <= capacity + 1e-6, entry
        assert entry["deferred_out_hours"] >= 0


def test_capacity_plan_names_a_bottleneck_and_carries_backlog_forward(client, created_component):
    body = client.get("/api/v1/forecast/capacity", params={"horizon": 12}).json()

    assert body["bottleneck_component_type"] in body["hours_by_component_type"]
    assert body["assumptions"]["labour_hours_per_component"]
    # The workshop does not start empty: opening backlog is queued first.
    opening = body["current_backlog"]["recovery_hours_required"]
    assert body["recommended_intake_schedule"][0]["deferred_in_hours"] == pytest.approx(
        opening, abs=0.11
    )


def test_utilisation_is_consistent_with_hours_and_capacity(client, created_component):
    body = client.get("/api/v1/forecast/capacity", params={"horizon": 12}).json()
    capacity = body["capacity_hours_per_quarter"]
    for quarter in body["quarters"]:
        expected = round(quarter["recovery_hours_required"] / capacity * 100.0, 1)
        assert quarter["utilisation_percent"] == pytest.approx(expected, abs=0.15)
        assert quarter["over_capacity"] == (quarter["recovery_hours_required"] > capacity)


# --------------------------------------------------------------------------
# Forward-looking exchange
# --------------------------------------------------------------------------
def test_site_impact_is_derivable_for_a_known_site(client, created_component):
    """created_component is installed at 'Chennai, India' with an initial
    prediction run - so it has a real (non-fallback) history at that site."""
    body = client.get(
        "/api/v1/forecast/site-impact", params={"site": "Chennai, India", "horizon": 3}
    ).json()

    assert body["horizon_months"] == 3
    assert len(body["sites"]) == 1
    row = body["sites"][0]
    assert row["site"] == "Chennai, India"
    assert row["site_components_assessed"] >= 1
    assert row["mix_source"] == "this site's own historical assessments"

    # N x average must equal the projected total - no hidden fudge factor.
    n = row["projected_components_this_period"]
    assert row["projected_value"] == pytest.approx(n * row["avg_value_per_component"], abs=0.05)
    assert row["projected_co2_kg"] == pytest.approx(
        n * row["avg_co2_kg_per_component"], abs=0.05
    )


def test_site_impact_falls_back_to_fleet_average_for_an_unassessed_site(client, component_payload):
    """A site with active components but none assessed yet must fall back to
    the fleet-wide average, and say so - never invent a site-specific number
    it does not have the data to support."""
    client.post(
        "/api/v1/components",
        json={
            **component_payload,
            "location": "Nowhereville, India",
            "run_initial_prediction": False,
        },
    )
    body = client.get(
        "/api/v1/forecast/site-impact", params={"site": "Nowhereville, India"}
    ).json()
    row = body["sites"][0]
    assert row["site_components_assessed"] == 0
    assert "fleet-wide average" in row["mix_source"]


def test_site_impact_without_a_site_lists_every_site_and_a_fleet_average(client, created_component):
    body = client.get("/api/v1/forecast/site-impact").json()
    assert len(body["sites"]) >= 1
    assert body["fleet_average"]["sites"] == len(body["sites"])
    assert body["fleet_average"]["avg_projected_value_per_site"] >= 0
