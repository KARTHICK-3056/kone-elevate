"""AI-recommendation vs. outcome agreement (P6).

Scores the AI's recommendations against the weak labels harvested from KONE
service orders (``app.integrations.kone_labels``). The workshop-outcome
report that read outcomes recorded on Recovery Exchange listings was removed
with the exchange.
"""

from __future__ import annotations

from typing import Any, Dict, List


#: Which AI recommendation is consistent with which real-world outcome.
#: DEFER_TO_INSPECTION is excluded on purpose - an abstention is neither an
#: agreement nor a disagreement, it is the model correctly declining to
#: have an opinion.
COMPATIBLE_OUTCOMES = {
    "CONTINUE_USING": {"CONTINUED_IN_SERVICE"},
    "COMPONENT_RECOVERY": {"PARTS_RECOVERED"},
    "MATERIAL_RECOVERY": {"MATERIAL_RECOVERED"},
    "DISPOSE": {"DISPOSED"},
}

#: Recommendations that keep a component or its parts in use. A mismatch
#: where the AI said one of these and the real outcome was a failed
#: inspection or an end-of-life route is the *optimistic* error direction.
OPTIMISTIC_RECOMMENDATIONS = {"CONTINUE_USING", "COMPONENT_RECOVERY"}


def score_weak_labels(pairs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Score AI recommendations against *weak* labels (K-3).

    Uses ``COMPATIBLE_OUTCOMES`` and ``OPTIMISTIC_RECOMMENDATIONS``, so
    "agreement" means one thing in this codebase. Two properties matter:

    * These labels are **harvested, not recorded.** A KONE-derived label is
      this platform inferring an outcome from a service order, not somebody
      stating what they did, and is reported as such.
    * They are **weighted**. An ``inferred`` label counts for 0.4 of an
      ``observed`` one (see ``app.integrations.kone_labels``), so the rate
      here is weighted and the unweighted count is reported beside it.

    ``pairs`` is ``[{"recommendation": ..., "label": <harvested label>}]``.
    The caller supplies the join because **the join key does not exist in
    this build**: KONE addresses equipment by KEN, this platform addresses
    components, and nothing maps one to the other. That mapping is a real
    deployment's problem and is called out in docs/kone-assumptions.md.
    """
    rows: List[Dict[str, Any]] = []
    for pair in pairs:
        recommendation = pair.get("recommendation")
        label = pair.get("label") or {}
        outcome = label.get("outcome")
        weight = float(label.get("weight") or 0.0)
        if not outcome or weight <= 0:
            # Censored: no disposition was published. Excluded rather than
            # scored as a miss - see kone_labels.agreement_input.
            continue

        if recommendation == "DEFER_TO_INSPECTION":
            verdict = "ABSTAINED"
        elif outcome in COMPATIBLE_OUTCOMES.get(recommendation, set()):
            verdict = "AGREE"
        else:
            verdict = "DISAGREE"

        rows.append(
            {
                "service_order_number": label.get("service_order_number"),
                "ai_recommendation": recommendation,
                "harvested_outcome": outcome,
                "confidence": label.get("confidence"),
                "weight": weight,
                "verdict": verdict,
                "optimistic_miss": (
                    verdict == "DISAGREE"
                    and recommendation in OPTIMISTIC_RECOMMENDATIONS
                    and outcome in {"FAILED_INSPECTION", "DISPOSED", "MATERIAL_RECOVERED"}
                ),
            }
        )

    scored = [row for row in rows if row["verdict"] != "ABSTAINED"]
    weight_total = sum(row["weight"] for row in scored)
    weight_agree = sum(row["weight"] for row in scored if row["verdict"] == "AGREE")

    return {
        "label_source": "kone-service-orders",
        "pairs_supplied": len(pairs),
        "scored": len(scored),
        "censored_or_unusable": len(pairs) - len(rows),
        "weighted_agreement_rate": (
            round(weight_agree / weight_total, 4) if weight_total else None
        ),
        "unweighted_agreement_rate": (
            round(len([r for r in scored if r["verdict"] == "AGREE"]) / len(scored), 4)
            if scored
            else None
        ),
        "optimistic_misses": len([row for row in scored if row["optimistic_miss"]]),
        "rows": rows,
        "caveat": (
            "Weak labels harvested from KONE service orders, not workshop "
            "records. This source is censored on every disposal class (see "
            "kone_labels.label_coverage), so a high agreement rate here means "
            "the model agrees on the cases KONE happens to publish - "
            "overwhelmingly 'the part was kept in service' - and says nothing "
            "about the disposal decisions. Not comparable with the pilot "
            "agreement rate, and not a substitute for it."
        ),
    }
