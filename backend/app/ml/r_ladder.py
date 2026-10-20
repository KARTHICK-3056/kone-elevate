"""The R-ladder: where each end-of-use category sits in the circular hierarchy.

The circular-economy field ranks value-retention strategies R0-R9, tightest
loop first. This platform's four categories map onto it directly:

* ``CONTINUE_USING``     -> R4  the component is maintained and keeps working
                                in its current application.
* ``COMPONENT_RECOVERY`` -> R7  usable sub-components are recovered, tested and
                                used in technically suitable lower-demand
                                applications - parts with a new function.
* ``MATERIAL_RECOVERY``  -> R8  useful material is recovered.
* ``DISPOSE``            -> R9  energy recovery or disposal.

Three rungs are deliberately **not offered**: transferring a complete
component to another user (R3), restoring a complete component for further
supply (R5), and rebuilding one to as-new (R6). The platform never
recommends moving, restoring or supplying a complete component anywhere
else, so no rule may place a component on those rungs.

Version 1 of this module refined dispositions onto R4/R6/R7 with prototype
rules (e.g. "rebuild this motor to as-new", "move this sheave to a
low-rise"). Those rules recommended exactly the complete-component routes the
platform no longer offers, so they were removed; the decision itself is made
by ``app.ml.decision_flow``.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.utils.enums import Recommendation, is_safety_critical

#: Bump whenever the mapping changes.
R_LADDER_VERSION = "v2"

#: The ordered hierarchy. Lower number = tighter loop = more value retained.
R_LADDER: List[Dict[str, Any]] = [
    {"rung": "R0", "name": "Refuse", "in_scope": False},
    {"rung": "R1", "name": "Rethink", "in_scope": False},
    {"rung": "R2", "name": "Reduce", "in_scope": False},
    {"rung": "R3", "name": "Transfer complete component to another user (not offered)", "in_scope": False},
    {"rung": "R4", "name": "Maintain and continue using", "in_scope": True},
    {"rung": "R5", "name": "Restore complete component for supply (not offered)", "in_scope": False},
    {"rung": "R6", "name": "Rebuild complete component to as-new (not offered)", "in_scope": False},
    {"rung": "R7", "name": "Recover sub-components for lower-demand use", "in_scope": True},
    {"rung": "R8", "name": "Material recovery", "in_scope": True},
    {"rung": "R9", "name": "Energy recovery / disposal", "in_scope": True},
]

#: Where each category sits.
BASE_RUNG: Dict[str, str] = {
    Recommendation.CONTINUE_USING.value: "R4",
    Recommendation.COMPONENT_RECOVERY.value: "R7",
    Recommendation.MATERIAL_RECOVERY.value: "R8",
    Recommendation.DISPOSE.value: "R9",
}

_RUNG_NAME: Dict[str, str] = {entry["rung"]: entry["name"] for entry in R_LADDER}


def refine(
    recommendation: str,
    features: Dict[str, Any],
    health_score: float,
    abstained: bool = False,
) -> Dict[str, Any]:
    """Place a category on the R-ladder.

    Kept under its original name for its callers. There is no longer any
    refinement: the rung follows the category the decision flow chose.
    """
    component_type = str(features.get("component_type") or "")
    base = BASE_RUNG.get(recommendation)
    if abstained or base is None:
        return {
            "rung": None,
            "name": None,
            "base_rung": base,
            "refined": False,
            "rule": None,
            "eligible": False,
            "reason_not_eligible": (
                "The model abstained; no strategy is placed on top of a deferred decision."
                if abstained
                else "No R-ladder rung maps to this recommendation."
            ),
            "version": R_LADDER_VERSION,
        }
    return {
        "rung": base,
        "name": _RUNG_NAME[base],
        "base_rung": base,
        "refined": False,
        "rule": None,
        "eligible": True,
        "reason_not_eligible": None,
        "safety_note": (
            "Safety-critical component: mandatory human inspection applies, and parts "
            "recovered from it are not used in a safety function."
            if is_safety_critical(component_type)
            else None
        ),
        "version": R_LADDER_VERSION,
        "notice": "Where the recommended category sits on the circular-economy ladder.",
    }


def ladder_reference() -> Dict[str, Any]:
    """The hierarchy itself, and which rungs this platform can reach."""
    reachable = set(BASE_RUNG.values())
    return {
        "version": R_LADDER_VERSION,
        "rungs": [
            {**entry, "reachable_by_this_platform": entry["rung"] in reachable}
            for entry in R_LADDER
        ],
        "note": (
            "R0-R2 are design-stage decisions taken before a component is installed. R3, R5 "
            "and R6 would move, restore or rebuild a complete component for use elsewhere; "
            "this platform does not offer them."
        ),
    }


def distribution(rows: List[Optional[str]]) -> Dict[str, Any]:
    """Count components per rung, ordered tightest loop first."""
    counts: Dict[str, int] = {}
    unplaced = 0
    for rung in rows:
        if rung is None:
            unplaced += 1
            continue
        counts[rung] = counts.get(rung, 0) + 1

    total = sum(counts.values())
    ordered = [entry["rung"] for entry in R_LADDER if entry["rung"] in counts]
    return {
        "by_rung": [
            {
                "rung": rung,
                "name": _RUNG_NAME[rung],
                "components": counts[rung],
                "share_percent": round(100.0 * counts[rung] / total, 1) if total else 0.0,
            }
            for rung in ordered
        ],
        "placed": total,
        "unplaced": unplaced,
        "unplaced_note": (
            "Components with no current assessment, or whose assessment was an "
            "abstention, are not placed on the ladder."
        ),
        "version": R_LADDER_VERSION,
    }
