"""The decision cost matrix: what each prediction error actually costs.

Why this file exists
---------------------
Every metric on the pitch deck (accuracy, macro F1) weighs all four
recommendation classes, and all sixteen possible (actual, predicted) pairs,
identically. They are not identical. Two examples from the confusion matrix
in ``models/metrics.json``:

* A component that is no longer suitable (true category COMPONENT_RECOVERY)
  but is predicted CONTINUE_USING stays in service when it should not. That
  is an *optimistic* error - it keeps a part running (or sends material to a
  processor, for DISPOSE-predicted-as-MATERIAL_RECOVERY) when it should not.
  Safety-critical types make this worse.
* A component still suitable for its application (true CONTINUE_USING) but
  predicted COMPONENT_RECOVERY costs money (an unnecessary removal and
  dismantling) but not safety.

Macro F1 scores these two mistakes as interchangeable. A quality engineer at
a safety-regulated buyer will not, and should not.

This module is the reviewed artefact plan.md P1 asks for: an explicit,
named, versioned cost table, not a constant buried inside a metric
calculation. Changing it requires a code review, same as any other decision
that changes what the model is allowed to recommend.

How costs are chosen
---------------------
Costs are in **arbitrary relative units**, not currency - the point is the
*ratio* between error types, not an absolute rupee figure (that would need
real incident/liability data this prototype does not have).

"Optimistic" means the predicted disposition is less conservative than the
true one (predicted CONTINUE_USING when the truth was COMPONENT_RECOVERY,
MATERIAL_RECOVERY or DISPOSE, or predicted COMPONENT_RECOVERY when the truth
was MATERIAL_RECOVERY/DISPOSE, etc.) - i.e. the
model would let a worse-condition part travel further down a lower-scrutiny
path than it should. "Conservative" is the opposite: unnecessary work, and
recoverable value destroyed.

Three named cost terms (v2)
----------------------------
``cost_breakdown`` splits every cost into terms that can be argued about
separately, because a single number cannot show whether the table is
dominated by safety or by circularity:

* **operational** - the work an error causes either way.
* **safety** - charged only on an optimistic error, and only on a
  safety-critical type, where it dominates everything else.
* **circularity** - charged only on a conservative error: value that was
  still recoverable and got destroyed anyway.

The circularity term is new in v2 and is the substance of the change. v1
priced a conservative error at roughly a third of the equivalent optimistic
one and never named the reason, which meant the decision layer treated
shredding a good part as nearly free - a defensible safety trade-off that
nobody had actually made on purpose. See ``CIRCULARITY_RATIONALE`` and
``safety_circularity_exchange_rate()``, which publishes the resulting
ratio so it can be challenged rather than inherited.

Resulting ordering, cheapest to most expensive:

    correct decision                                             0
    adjacent conservative error (work + circularity loss)     ~ 2.8x
    adjacent optimistic error, non-safety-critical            ~ 3x
    two-class-distant conservative error                      ~ 5x
    three-class-distant conservative error                    ~ 7.7x
    adjacent optimistic error on a safety-critical type       ~ 12x
"""

from __future__ import annotations

from typing import Any, Dict, List

from app.utils.enums import Recommendation, is_safety_critical

#: Disposition severity order, least to most conservative. Index position is
#: used to classify an error as "optimistic" (predicted index < actual index)
#: or "conservative" (predicted index > actual index).
CLASS_ORDER: List[str] = [
    Recommendation.CONTINUE_USING.value,
    Recommendation.COMPONENT_RECOVERY.value,
    Recommendation.MATERIAL_RECOVERY.value,
    Recommendation.DISPOSE.value,
]

#: version this file - bump whenever the cost table changes, so a stored
#: prediction's "expected cost" can be traced to the table that produced it.
#:
#: v2 (CE-4) split the conservative-error cost into a named operational term
#: and a named **circularity-loss** term. See CIRCULARITY_RATIONALE below.
COST_MATRIX_VERSION = "v2"

_BASE_COST: Dict[int, float] = {
    0: 0.0,   # correct
    1: 3.0,   # one class apart
    2: 5.0,   # two classes apart
    3: 8.0,   # three classes apart (CONTINUE_USING<->DISPOSE, the worst case)
}

#: Conservative errors (predicted MORE cautious than truth) cost less than
#: optimistic ones of the same distance - removing a part that could have
#: continued costs money; keeping a part in service that should have come
#: out costs safety.
_CONSERVATIVE_DISCOUNT = 0.55

#: Multiplier applied to any OPTIMISTIC error on a safety-critical component
#: type (steel rope, brake, governor). This is a decision-support multiplier
#: only - it does not change the safety gate itself, which always requires
#: human inspection for these types regardless of cost.
_SAFETY_CRITICAL_OPTIMISTIC_MULTIPLIER = 4.0

#: Cost, per rung pushed down the disposition order, of destroying value that
#: was still recoverable. Sending a part that could have continued in service
#: to material recovery is not a free mistake, and pricing it at zero is what made this table quietly
#: anti-circular before v2.
_CIRCULARITY_LOSS_PER_STEP = 1.1

CIRCULARITY_RATIONALE = (
    "A conservative error destroys recoverable value: predicting MATERIAL_RECOVERY "
    "for a part that could have continued in service scraps a component with life "
    "left in it. Before v2 "
    "this table priced that at roughly a third of the equivalent optimistic "
    "error and never named it, so the model's decision layer treated "
    "destroying value as nearly free - a defensible safety trade-off that "
    "nobody had actually argued. v2 adds an explicit circularity-loss term so "
    "the trade-off is visible and reviewable. Safety still dominates, and "
    "should: see safety_circularity_exchange_rate() for by how much."
)


def cost_breakdown(actual: str, predicted: str, component_type: str) -> Dict[str, float]:
    """The named components of a decision cost.

    Splitting this out is the point of CE-4: a single number cannot show
    whether the table is dominated by safety or by circularity, and a
    reviewer has to be able to see which lever they are pulling.
    """
    empty = {"operational": 0.0, "safety": 0.0, "circularity": 0.0, "total": 0.0}
    if actual not in CLASS_ORDER or predicted not in CLASS_ORDER:
        return empty

    actual_index = CLASS_ORDER.index(actual)
    predicted_index = CLASS_ORDER.index(predicted)
    distance = abs(predicted_index - actual_index)
    if distance == 0:
        return empty

    base = _BASE_COST[distance]
    optimistic = predicted_index < actual_index

    if optimistic:
        # Under-calling the disposition: the part travels further down a
        # lower-scrutiny path than it should. This is the safety-relevant
        # direction, and on a safety-critical type it is multiplied.
        operational = base
        safety = (
            base * (_SAFETY_CRITICAL_OPTIMISTIC_MULTIPLIER - 1.0)
            if is_safety_critical(component_type)
            else 0.0
        )
        circularity = 0.0
    else:
        # Over-calling it: unnecessary work, plus recoverable value destroyed.
        operational = base * _CONSERVATIVE_DISCOUNT
        safety = 0.0
        circularity = distance * _CIRCULARITY_LOSS_PER_STEP

    return {
        "operational": round(operational, 4),
        "safety": round(safety, 4),
        "circularity": round(circularity, 4),
        "total": round(operational + safety + circularity, 4),
    }


def cost_of(actual: str, predicted: str, component_type: str) -> float:
    """Cost of predicting ``predicted`` when the true disposition was ``actual``."""
    return cost_breakdown(actual, predicted, component_type)["total"]


def safety_circularity_exchange_rate() -> Dict[str, Any]:
    """How much more this table charges for a safety error than a circularity one.

    Published rather than left implicit so the trade-off can be challenged.
    Both figures compare errors of the *same* magnitude (one class apart),
    which is the only comparison that means anything.
    """
    continue_using, recovery = Recommendation.CONTINUE_USING.value, Recommendation.COMPONENT_RECOVERY.value
    optimistic_plain = cost_of(recovery, continue_using, "Motor")
    optimistic_critical = cost_of(recovery, continue_using, "Steel Rope")
    conservative = cost_of(continue_using, recovery, "Motor")
    return {
        "optimistic_error_cost_standard_type": optimistic_plain,
        "optimistic_error_cost_safety_critical_type": optimistic_critical,
        "conservative_error_cost": conservative,
        "exchange_rate_standard": (
            round(optimistic_plain / conservative, 2) if conservative else None
        ),
        "exchange_rate_safety_critical": (
            round(optimistic_critical / conservative, 2) if conservative else None
        ),
        "interpretation": (
            "On a safety-critical type this table charges "
            f"{round(optimistic_critical / conservative, 1) if conservative else '?'}x "
            "as much for keeping a worn part in service as it does for "
            "needlessly destroying a good one. That ordering is deliberate and "
            "should stay; the point of publishing it is that it is now a "
            "reviewed decision rather than an accident of the weights."
        ),
        "rationale": CIRCULARITY_RATIONALE,
        "cost_matrix_version": COST_MATRIX_VERSION,
    }


def full_matrix(component_type: str) -> Dict[str, Dict[str, float]]:
    """The full 4x4 (actual x predicted) cost table for one component type."""
    return {
        actual: {predicted: cost_of(actual, predicted, component_type) for predicted in CLASS_ORDER}
        for actual in CLASS_ORDER
    }


def expected_cost(probabilities: Dict[str, float], predicted: str, component_type: str) -> float:
    """Expected cost of choosing ``predicted``, given the model's class probabilities.

    ``sum over actual classes of P(actual) * cost(actual, predicted)``. This is
    the quantity decision thresholds are tuned against in
    :mod:`app.ml.decision`, instead of the argmax-of-probability rule that
    optimises accuracy/F1 but ignores error asymmetry.
    """
    return round(
        sum(
            float(probabilities.get(actual, 0.0)) * cost_of(actual, predicted, component_type)
            for actual in CLASS_ORDER
        ),
        4,
    )


def best_decision(probabilities: Dict[str, float], component_type: str) -> Dict[str, object]:
    """Pick the class-probability-weighted minimum-expected-cost disposition.

    Returns the chosen class together with the expected cost of every
    candidate, so a caller (or an auditor) can see why the arg-min-cost choice
    was not simply the arg-max-probability choice.
    """
    candidates = {
        predicted: expected_cost(probabilities, predicted, component_type) for predicted in CLASS_ORDER
    }
    chosen = min(candidates, key=candidates.get)
    return {
        "cost_optimal_recommendation": chosen,
        "expected_cost_by_class": candidates,
        "cost_matrix_version": COST_MATRIX_VERSION,
        "safety_circularity_exchange_rate": safety_circularity_exchange_rate(),
    }
