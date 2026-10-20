"""The R-ladder placement (CE-3) and the circularity cost term (CE-4).

The R-ladder is now a plain mapping of the four categories onto the
circular-economy hierarchy. What these tests hold is that the mapping never
places a component on a rung that would move, restore or supply a complete
component elsewhere (R3, R5, R6), never places an abstention, and rides
alongside the recommendation rather than replacing it.
"""

from __future__ import annotations

import pytest

from app.ml import cost_matrix, r_ladder
from app.utils.enums import Recommendation

CONTINUE = Recommendation.CONTINUE_USING.value
COMPONENT = Recommendation.COMPONENT_RECOVERY.value
MATERIAL = Recommendation.MATERIAL_RECOVERY.value
DISPOSE = Recommendation.DISPOSE.value

NOT_OFFERED = {"R3", "R5", "R6"}


def _features(**overrides):
    base = {"component_type": "Motor", "component_age": 5.0, "inspection_score": 80}
    base.update(overrides)
    return base


# --------------------------------------------------------------------------
# CE-3: placement
# --------------------------------------------------------------------------
def test_each_category_has_its_rung():
    assert r_ladder.BASE_RUNG == {CONTINUE: "R4", COMPONENT: "R7", MATERIAL: "R8", DISPOSE: "R9"}


@pytest.mark.parametrize("category", [CONTINUE, COMPONENT, MATERIAL, DISPOSE])
def test_placement_follows_the_category_and_is_never_refined(category):
    placed = r_ladder.refine(category, _features(), health_score=70.0)
    assert placed["rung"] == r_ladder.BASE_RUNG[category]
    assert placed["refined"] is False
    assert placed["rule"] is None
    assert placed["rung"] not in NOT_OFFERED


def test_no_rung_moves_restores_or_supplies_a_complete_component():
    reference = r_ladder.ladder_reference()
    reachable = {entry["rung"] for entry in reference["rungs"] if entry["reachable_by_this_platform"]}
    assert reachable == {"R4", "R7", "R8", "R9"}
    for entry in reference["rungs"]:
        if entry["rung"] in NOT_OFFERED:
            assert "not offered" in entry["name"]
            assert entry["in_scope"] is False


def test_an_abstention_is_not_placed():
    placed = r_ladder.refine(COMPONENT, _features(), health_score=70.0, abstained=True)
    assert placed["rung"] is None
    assert placed["eligible"] is False


def test_safety_critical_parts_carry_the_safety_note():
    placed = r_ladder.refine(COMPONENT, _features(component_type="Brake"), health_score=70.0)
    assert placed["rung"] == "R7"
    assert "safety function" in placed["safety_note"]
    assert r_ladder.refine(COMPONENT, _features(), health_score=70.0)["safety_note"] is None


def test_the_distribution_is_ordered_tightest_loop_first():
    dist = r_ladder.distribution(["R8", "R4", None, "R7", "R4"])
    assert [row["rung"] for row in dist["by_rung"]] == ["R4", "R7", "R8"]
    assert dist["placed"] == 4
    assert dist["unplaced"] == 1


def test_the_strategy_rides_alongside_the_recommendation_not_instead_of_it(client, created_component):
    response = client.post(f"/api/v1/components/{created_component['component_id']}/predict")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["recommendation"] in {CONTINUE, COMPONENT, MATERIAL, DISPOSE, "DEFER_TO_INSPECTION"}
    strategy = body["circular_strategy"]
    if body["recommendation"] != "DEFER_TO_INSPECTION":
        assert strategy["rung"] == r_ladder.BASE_RUNG[body["recommendation"]]


# --------------------------------------------------------------------------
# CE-4: the circularity cost term
# --------------------------------------------------------------------------
def test_destroying_recoverable_value_now_has_a_named_cost():
    breakdown = cost_matrix.cost_breakdown(CONTINUE, MATERIAL, "Motor")
    assert breakdown["circularity"] > 0
    assert breakdown["safety"] == 0.0
    assert breakdown["total"] == pytest.approx(
        breakdown["operational"] + breakdown["circularity"], abs=1e-6
    )


def test_an_optimistic_error_carries_safety_cost_not_circularity_cost():
    breakdown = cost_matrix.cost_breakdown(MATERIAL, CONTINUE, "Steel Rope")
    assert breakdown["safety"] > 0
    assert breakdown["circularity"] == 0.0


def test_safety_still_dominates_circularity():
    """Keeping a worn part in service has to stay more expensive than
    needlessly recovering a good one."""
    rate = cost_matrix.safety_circularity_exchange_rate()
    assert rate["exchange_rate_safety_critical"] > 1.0
    assert rate["optimistic_error_cost_safety_critical_type"] > rate["conservative_error_cost"]


def test_the_circularity_penalty_scales_with_how_far_value_is_destroyed():
    near = cost_matrix.cost_breakdown(CONTINUE, COMPONENT, "Motor")["circularity"]
    far = cost_matrix.cost_breakdown(CONTINUE, DISPOSE, "Motor")["circularity"]
    assert far > near


def test_the_exchange_rate_is_published_on_the_metrics_endpoint(client):
    body = client.get("/api/v1/model/metrics").json()
    rate = body["safety_circularity_exchange_rate"]
    assert rate["cost_matrix_version"] == cost_matrix.COST_MATRIX_VERSION
    assert "rationale" in rate
