"""The abstention rule: when the model should say "I don't know" instead.

A component sitting on a class boundary gets the same confident-looking
presentation as a clear-cut case today - that is worse than another two
points of accuracy for a decision-support tool in a safety-regulated
industry. This module is the single place the rule is defined, so
``app.ml.train`` (which reports what the rule *would* have done on the test
set) and ``app.ml.predict`` (which applies it live) can never drift apart.

Rule: abstain (``DEFER_TO_INSPECTION``) when EITHER
  * the calibrated top-class probability is below ``CONFIDENCE_THRESHOLD``, OR
  * the split-conformal prediction set (app.ml.conformal) contains more than
    one plausible class.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

import numpy as np

from app.ml.conformal import prediction_set

#: Below this top-class probability, abstain regardless of the conformal set.
#: Chosen relative to a 4-class problem (0.25 = random guessing): 0.5 means
#: "the model's own best guess is not even an outright majority verdict".
CONFIDENCE_THRESHOLD = 0.5


def decide(probabilities: Dict[str, float], q_hat: Optional[float]) -> Dict[str, Any]:
    """Apply the abstention rule to one prediction's probability distribution."""
    top_class = max(probabilities, key=probabilities.get)
    top_confidence = probabilities[top_class]

    if q_hat is None:
        pset = [top_class]
    else:
        pset = prediction_set(probabilities, q_hat)

    low_confidence = top_confidence < CONFIDENCE_THRESHOLD
    ambiguous_set = len(pset) > 1
    abstain = low_confidence or ambiguous_set

    return {
        "abstain": abstain,
        "argmax_class": top_class,
        "argmax_confidence": round(float(top_confidence), 4),
        "prediction_set": pset,
        "prediction_set_size": len(pset),
        "trigger": (
            "low_confidence_and_ambiguous_set"
            if low_confidence and ambiguous_set
            else "low_confidence"
            if low_confidence
            else "ambiguous_prediction_set"
            if ambiguous_set
            else "none"
        ),
    }


def abstention_report(
    probability_matrix: np.ndarray,
    true_labels: Sequence[str],
    classes: List[str],
    q_hat: float,
) -> Dict[str, Any]:
    """Summarise what the abstention rule would do across an evaluation set.

    Reports the number/rate of abstained cases, and - the number that matters
    most - accuracy on the answered subset versus what accuracy would have
    been on the abstained subset had the model been forced to answer anyway.
    """
    n = len(true_labels)
    predicted = np.array(classes)[probability_matrix.argmax(axis=1)]
    correct = predicted == np.asarray(true_labels)

    abstained = np.zeros(n, dtype=bool)
    for row in range(n):
        probabilities = {label: float(probability_matrix[row, col]) for col, label in enumerate(classes)}
        abstained[row] = decide(probabilities, q_hat)["abstain"]

    answered = ~abstained
    answered_count = int(answered.sum())
    abstained_count = int(abstained.sum())

    return {
        "confidence_threshold": CONFIDENCE_THRESHOLD,
        "total_records": n,
        "abstained_records": abstained_count,
        "abstention_rate": round(abstained_count / n, 4) if n else 0.0,
        "answered_records": answered_count,
        "accuracy_without_abstention": round(float(correct.mean()), 4) if n else None,
        "accuracy_on_answered_subset": (
            round(float(correct[answered].mean()), 4) if answered_count else None
        ),
        "accuracy_on_abstained_subset_if_forced": (
            round(float(correct[abstained].mean()), 4) if abstained_count else None
        ),
        "note": (
            "accuracy_on_answered_subset is the number that matters: it is the "
            "accuracy a technician actually experiences when the model does not "
            "abstain. accuracy_on_abstained_subset_if_forced shows why those "
            "cases were flagged - it is markedly lower."
        ),
    }
