"""Calibration diagnostics: per-class Brier score, ECE, and reliability bins.

A Random Forest's ``predict_proba`` is a vote fraction, not a probability -
it is well known to be overconfident in the middle of the class distribution
and underconfident at the extremes (Niculescu-Mizil & Caruana, 2005). These
functions measure exactly that gap so it can be reported and, once
``CalibratedClassifierCV`` is applied, checked that the gap has closed.
"""

from __future__ import annotations

from typing import Any, Dict, List, Sequence

import numpy as np


def brier_score_per_class(
    probabilities: np.ndarray, labels: Sequence[str], classes: Sequence[str]
) -> Dict[str, float]:
    """One-vs-rest Brier score for each class: mean((P(class) - is_class)^2).

    Lower is better; 0 is perfect, 0.25 is the score of always predicting 0.5
    for a binary event, ~1.0 is the worst case for a confident wrong call.
    """
    labels_array = np.asarray(labels)
    scores: Dict[str, float] = {}
    for column, class_label in enumerate(classes):
        indicator = (labels_array == class_label).astype(float)
        scores[class_label] = round(float(np.mean((probabilities[:, column] - indicator) ** 2)), 4)
    return scores


def expected_calibration_error(
    probabilities: np.ndarray, labels: Sequence[str], classes: Sequence[str], n_bins: int = 10
) -> Dict[str, Any]:
    """Expected Calibration Error (ECE) over the top-1 (predicted-class) confidence.

    Predictions are bucketed by their top-class confidence into ``n_bins``
    equal-width bins; ECE is the confidence-weighted average gap between mean
    confidence and observed accuracy within each bin. A perfectly calibrated
    model has ECE = 0: in every bin, "we said X% confident" matches "we were
    right X% of the time".
    """
    labels_array = np.asarray(labels)
    class_array = np.asarray(classes)
    top_index = probabilities.argmax(axis=1)
    confidence = probabilities[np.arange(len(probabilities)), top_index]
    predicted = class_array[top_index]
    correct = (predicted == labels_array).astype(float)

    bin_edges = np.linspace(0.0, 1.0, n_bins + 1)
    bins: List[Dict[str, Any]] = []
    ece = 0.0
    n = len(probabilities)

    for i in range(n_bins):
        low, high = bin_edges[i], bin_edges[i + 1]
        is_last_bin = i == n_bins - 1
        in_bin = (confidence >= low) & (confidence <= high if is_last_bin else confidence < high)
        count = int(in_bin.sum())
        if count == 0:
            bins.append(
                {
                    "bin_low": round(float(low), 2),
                    "bin_high": round(float(high), 2),
                    "count": 0,
                    "mean_confidence": None,
                    "observed_accuracy": None,
                }
            )
            continue
        mean_confidence = float(confidence[in_bin].mean())
        observed_accuracy = float(correct[in_bin].mean())
        bins.append(
            {
                "bin_low": round(float(low), 2),
                "bin_high": round(float(high), 2),
                "count": count,
                "mean_confidence": round(mean_confidence, 4),
                "observed_accuracy": round(observed_accuracy, 4),
            }
        )
        ece += (count / n) * abs(mean_confidence - observed_accuracy)

    return {
        "expected_calibration_error": round(float(ece), 4),
        "n_bins": n_bins,
        "bins": bins,
        "overall_accuracy": round(float(correct.mean()), 4),
        "overall_mean_confidence": round(float(confidence.mean()), 4),
    }
