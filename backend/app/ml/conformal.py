"""Split-conformal prediction sets for the disposition classifier.

Why
---
A confidence number invites a technician to read 0.74 as "74% likely
correct." Calibration (``app.ml.train``) makes that reading approximately
true on average, but it says nothing about *this specific* prediction sitting
on a class boundary. Conformal prediction adds a second, complementary
signal: instead of one point estimate, it returns a **set** of plausible
classes with a guaranteed marginal coverage property - e.g. "the true class is
in this set at least 90% of the time, across the whole population" - without
assuming the probabilities are perfectly calibrated.

When that set contains more than one class, the model is genuinely ambiguous
about this component, and ``app.ml.predict`` abstains (``DEFER_TO_INSPECTION``)
rather than presenting a single confident-looking answer.

Method: Least Ambiguous Set-Valued Classifier (LAC / split-conformal,
Sadinle, Lei & Wasserman 2019). Simpler adaptive variants (APS) exist but LAC
is the standard first implementation and is exact under exchangeability.

This is NOT the same guarantee as calibration and is deliberately kept
independent of it: the nonconformity score is computed from whatever
``predict_proba`` the wrapped estimator returns (calibrated, in this
pipeline), and the conformal calibration split is *disjoint* from both the
data used to fit the base classifier and the data used to fit the isotonic
calibrators.
"""

from __future__ import annotations

import math
from typing import Dict, List, Sequence

import numpy as np


def conformal_threshold(
    calibration_probabilities: np.ndarray,
    calibration_labels: Sequence[str],
    classes: Sequence[str],
    alpha: float = 0.1,
) -> float:
    """Compute q_hat, the (1 - alpha) conformal quantile of nonconformity scores.

    Parameters
    ----------
    calibration_probabilities:
        ``predict_proba`` output on a held-out calibration split, shape
        ``(n_samples, n_classes)``, columns ordered as ``classes``.
    calibration_labels:
        True label for each calibration row.
    classes:
        Class label for each column of ``calibration_probabilities``.
    alpha:
        Miscoverage rate. ``alpha=0.1`` targets 90% marginal coverage: across
        the whole population, the true class is in the returned prediction
        set at least 90% of the time.
    """
    class_index = {label: index for index, label in enumerate(classes)}
    n = len(calibration_labels)
    if n == 0:
        raise ValueError("Need at least one calibration row to compute q_hat")

    # Nonconformity score = 1 - P(true class). Higher means "more surprising".
    scores = np.array(
        [
            1.0 - calibration_probabilities[row, class_index[label]]
            for row, label in enumerate(calibration_labels)
        ]
    )
    # Finite-sample-corrected quantile level, per Sadinle/Lei/Wasserman.
    level = math.ceil((n + 1) * (1 - alpha)) / n
    level = min(level, 1.0)
    return float(np.quantile(scores, level, method="higher"))


def prediction_set(
    probabilities: Dict[str, float], q_hat: float
) -> List[str]:
    """The conformal prediction set for one example: every class whose
    probability is high enough that excluding it would exceed the allowed
    miscoverage rate, i.e. ``P(class) >= 1 - q_hat``.
    """
    threshold = 1.0 - q_hat
    included = [label for label, probability in probabilities.items() if probability >= threshold]
    # Never return an empty set - fall back to the single most likely class.
    if not included:
        included = [max(probabilities, key=probabilities.get)]
    return included
