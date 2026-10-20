"""Weak disposition labels harvested from KONE service orders (K-3).

Why this matters more than the feature work
-------------------------------------------
K-1 and K-2 upgrade the model's *inputs* from synthetic to real. Neither
touches the *target*. Every accuracy figure this platform publishes still
describes a simulator, and will until the model is scored against
dispositions somebody actually made. This module is the only route to
those that does not require a pilot.

What KONE's API can and cannot tell us
--------------------------------------
Reading the Service Info API carefully produces an uncomfortable finding
that is better surfaced than buried:

``technicianActionCode`` records what the technician did to the
**equipment**, not what happened to the **component that came out**. So:

* ``INSPECTED`` / ``ADJUSTED`` / ``REPAIRED`` -> the component stayed in
  the shaft. That is a real, directly observed "this part was good enough
  to keep in service" label.
* ``REPLACED`` -> the component was removed. **KONE publishes nothing
  about where it went.** Parts recovered, material recovered, or
  landfilled are indistinguishable in this data.

The consequence is structural, not a gap to be tuned away: this label
source is **censored on exactly the classes that matter most**. It can
supply CONTINUE_USING labels in quantity and can supply almost nothing about
MATERIAL_RECOVERY or DISPOSE. A model retrained on these alone would drift
optimistic - toward putting parts back into service - which is the precise
error direction ``app.ml.cost_matrix`` prices highest.

So these are *weak, partially observed* labels for measuring agreement,
not a training set. :func:`label_coverage` reports the censoring explicitly
so nobody mistakes volume for coverage.

Assumed mappings
----------------
KONE publishes no enumeration of ``technicianActionCode`` values in its
reference implementation, so the codes below are assumed from the examples
plus ordinary service vocabulary. They are versioned and overridable for
the same reason the standards clauses carry ``CLAUSE_UNVERIFIED``: the
shape of the reasoning is right, the specific tokens need confirming
against a real code list.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from app.utils.enums import WorkshopOutcome

#: Bump when a mapping below changes, so a harvested label can be traced
#: to the rules that produced it.
LABEL_RULES_VERSION = "v1"

#: Action codes meaning the component stayed in service. ASSUMED - see the
#: module docstring.
_KEPT_IN_SERVICE = frozenset(
    {"INSPECTED", "ADJUSTED", "REPAIRED", "SERVICED", "CLEANED", "LUBRICATED", "TESTED"}
)

#: Action codes meaning the component came out. What happened to it next is
#: not published anywhere in the API.
_REMOVED = frozenset({"REPLACED", "REMOVED", "EXCHANGED", "RENEWED"})

#: Condition-on-departure codes that count as "left working".
_HEALTHY_ON_DEPARTURE = frozenset({"1", "2"})

#: How much a harvested label is worth.
#:
#: ``observed``  - the order states it directly. Usable for agreement
#:                 scoring at full weight.
#: ``inferred``  - reasoned from failure context, not stated. Carries real
#:                 inferential risk and is down-weighted accordingly.
#: ``unknown``   - the order proves a removal happened and nothing else.
#:                 Deliberately produces NO label rather than a guess.
LABEL_WEIGHTS: Dict[str, float] = {"observed": 1.0, "inferred": 0.4, "unknown": 0.0}


def _parse(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def derive_label(order: Dict[str, Any]) -> Dict[str, Any]:
    """Derive a weak workshop outcome from one KONE service-order detail.

    Always returns a dict. ``outcome`` is ``None`` when the order cannot
    support a label, with ``reason`` saying why - a censored observation
    recorded as censored, rather than dropped silently or filled in.
    """
    action = str(order.get("technicianActionCode") or "").strip().upper()
    departure = str(order.get("equipmentConditionOnDeparture") or "").strip()
    arrival_desc = str(order.get("equipmentConditionOnArrivalDesc") or "").strip().upper()
    failure = order.get("equipmentFailureReason")
    entrapment = bool(order.get("entrapment"))

    base: Dict[str, Any] = {
        "service_order_number": order.get("serviceOrderNumber"),
        "performed_at": _parse(
            order.get("finishedDateTime") or order.get("actualArrivalDateTime")
        ),
        "failed_component_code": order.get("failedComponentCode"),
        "technician_action_code": action or None,
        "rules_version": LABEL_RULES_VERSION,
    }

    if action in _KEPT_IN_SERVICE and departure in _HEALTHY_ON_DEPARTURE:
        return {
            **base,
            "outcome": WorkshopOutcome.CONTINUED_IN_SERVICE.value,
            "confidence": "observed",
            "weight": LABEL_WEIGHTS["observed"],
            "reason": (
                f"Technician action '{action}' with the equipment departing in "
                f"condition {departure}: the component was not removed, which "
                "is a directly observed decision to keep it in service."
            ),
        }

    if action in _REMOVED:
        # The component came out. KONE publishes nothing about where it went.
        if failure or entrapment or arrival_desc == "OUT_OF_SERVICE":
            return {
                **base,
                "outcome": WorkshopOutcome.FAILED_INSPECTION.value,
                "confidence": "inferred",
                "weight": LABEL_WEIGHTS["inferred"],
                "reason": (
                    f"Replaced after a recorded failure "
                    f"({failure or ('entrapment' if entrapment else arrival_desc)}). "
                    "The removed component had failed in service - but whether it "
                    "then had parts or material recovered, or was scrapped, is NOT published, "
                    "so this labels its condition, not its disposition."
                ),
            }
        return {
            **base,
            "outcome": None,
            "confidence": "unknown",
            "weight": LABEL_WEIGHTS["unknown"],
            "reason": (
                "Component was replaced with no failure recorded. KONE publishes "
                "no disposition for a removed part, so component recovery / material recovery / "
                "dispose are indistinguishable here. Censored, not guessed."
            ),
        }

    return {
        **base,
        "outcome": None,
        "confidence": "unknown",
        "weight": LABEL_WEIGHTS["unknown"],
        "reason": (
            f"No disposition can be read from technician action "
            f"'{action or 'none recorded'}'."
        ),
    }


def harvest(orders: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Derive a label for every service order, censored ones included."""
    return [derive_label(order) for order in orders]


def label_coverage(labels: List[Dict[str, Any]]) -> Dict[str, Any]:
    """What this label source can and cannot see.

    The headline is ``censored_percent`` and ``classes_never_observed``.
    Reporting only the labels that came out would make a source that is
    blind to every disposal route look like a usable training set.
    """
    total = len(labels)
    by_confidence: Dict[str, int] = {}
    by_outcome: Dict[str, int] = {}
    for label in labels:
        by_confidence[label["confidence"]] = by_confidence.get(label["confidence"], 0) + 1
        if label["outcome"]:
            by_outcome[label["outcome"]] = by_outcome.get(label["outcome"], 0) + 1

    censored = sum(1 for label in labels if label["outcome"] is None)
    observed_classes = set(by_outcome)
    never = [
        value
        for value in (
            WorkshopOutcome.PARTS_RECOVERED.value,
            WorkshopOutcome.MATERIAL_RECOVERED.value,
            WorkshopOutcome.DISPOSED.value,
        )
        if value not in observed_classes
    ]

    return {
        "orders": total,
        "labelled": total - censored,
        "censored": censored,
        "censored_percent": round(100.0 * censored / total, 1) if total else 0.0,
        "by_confidence": by_confidence,
        "by_outcome": by_outcome,
        "classes_never_observed": never,
        "usable_for_training": False,
        "structural_limitation": (
            "KONE's technicianActionCode records what was done to the "
            "EQUIPMENT, not where a removed COMPONENT went. This source can "
            "say a part was kept in service; it cannot distinguish component "
            "recovery from material recovery from scrapping. It is therefore censored on exactly "
            "the disposal classes, and a model retrained on it alone would "
            "drift optimistic - the error direction app.ml.cost_matrix prices "
            "highest. Use it to measure agreement, not to train."
        ),
        "rules_version": LABEL_RULES_VERSION,
        "assumption_notice": (
            "KONE publishes no enumeration of technicianActionCode values. The "
            "codes these rules match on are assumed from the reference "
            "implementation's examples plus ordinary service vocabulary, and "
            "need confirming against a real code list - the same posture the "
            "standards clauses take with CLAUSE_UNVERIFIED."
        ),
    }


def agreement_input(labels: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Just the labels worth scoring agreement against.

    Censored observations are excluded here rather than counted as
    disagreements: a removal whose destination nobody recorded is missing
    data, and scoring it as a miss would understate the model on exactly
    the cases this source cannot see.
    """
    return [label for label in labels if label["outcome"] and label["weight"] > 0]
