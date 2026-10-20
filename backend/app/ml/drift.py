"""Feature-drift detection: is live traffic still shaped like the training data.

A model's accuracy figure describes performance on the distribution it was
evaluated against. If the population being scored later shifts - a new
component-type mix, a maintenance-policy change, a different climate - that
figure quietly stops being true, with no error and no warning. This module
gives the "no warning" part an alarm.

Two complementary statistics, both computed independently per numeric
feature:

* **PSI** (Population Stability Index) - bins both distributions the same
  way and compares bin populations. The industry-standard thresholds below
  are widely used in credit-risk model monitoring and are a reasonable
  starting point here: no formal validation of these exact cutoffs has been
  done for this domain.
* **KS** (two-sample Kolmogorov-Smirnov statistic) - the maximum gap between
  the two empirical CDFs, with a p-value under the null hypothesis that both
  samples are drawn from the same distribution.

Categorical features (component_type, material) get a simpler population
comparison: the change in each category's share.
"""

from __future__ import annotations

from typing import Any, Dict, List

import numpy as np
import pandas as pd
from scipy import stats

from app.ml.features import CATEGORICAL_FEATURES, NUMERIC_FEATURES

#: PSI interpretation thresholds (credit-risk-monitoring convention).
PSI_NO_SHIFT = 0.1
PSI_MODERATE_SHIFT = 0.25


def _psi(reference: np.ndarray, current: np.ndarray, bins: int = 10) -> float:
    """Population Stability Index between two samples of one numeric feature."""
    reference = reference[~np.isnan(reference)]
    current = current[~np.isnan(current)]
    if len(reference) == 0 or len(current) == 0:
        return 0.0

    edges = np.quantile(reference, np.linspace(0, 1, bins + 1))
    edges = np.unique(edges)
    if len(edges) < 2:
        return 0.0
    edges[0], edges[-1] = -np.inf, np.inf

    reference_counts, _ = np.histogram(reference, bins=edges)
    current_counts, _ = np.histogram(current, bins=edges)

    reference_ratio = np.clip(reference_counts / max(len(reference), 1), 1e-6, None)
    current_ratio = np.clip(current_counts / max(len(current), 1), 1e-6, None)

    return float(np.sum((current_ratio - reference_ratio) * np.log(current_ratio / reference_ratio)))


def _psi_band(psi: float) -> str:
    if psi < PSI_NO_SHIFT:
        return "no_shift"
    if psi < PSI_MODERATE_SHIFT:
        return "moderate_shift"
    return "significant_shift"


def numeric_feature_drift(reference: pd.DataFrame, current: pd.DataFrame) -> List[Dict[str, Any]]:
    """PSI + KS per numeric feature present in both frames."""
    results = []
    for column in NUMERIC_FEATURES:
        if column not in reference.columns or column not in current.columns:
            continue
        ref_values = reference[column].to_numpy(dtype=float)
        cur_values = current[column].to_numpy(dtype=float)

        psi = _psi(ref_values, cur_values)
        ks_result = stats.ks_2samp(ref_values, cur_values)

        results.append(
            {
                "feature": column,
                "psi": round(psi, 4),
                "psi_band": _psi_band(psi),
                "ks_statistic": round(float(ks_result.statistic), 4),
                "ks_pvalue": round(float(ks_result.pvalue), 6),
                "reference_mean": round(float(np.nanmean(ref_values)), 3),
                "current_mean": round(float(np.nanmean(cur_values)), 3),
            }
        )
    return sorted(results, key=lambda row: row["psi"], reverse=True)


def categorical_feature_drift(reference: pd.DataFrame, current: pd.DataFrame) -> List[Dict[str, Any]]:
    """Share-of-population change per category, for each categorical feature."""
    results = []
    for column in CATEGORICAL_FEATURES:
        if column not in reference.columns or column not in current.columns:
            continue
        ref_shares = reference[column].value_counts(normalize=True)
        cur_shares = current[column].value_counts(normalize=True)
        categories = sorted(set(ref_shares.index) | set(cur_shares.index))

        max_abs_change = 0.0
        by_category = {}
        for category in categories:
            ref_share = float(ref_shares.get(category, 0.0))
            cur_share = float(cur_shares.get(category, 0.0))
            change = cur_share - ref_share
            max_abs_change = max(max_abs_change, abs(change))
            by_category[category] = {
                "reference_share": round(ref_share, 4),
                "current_share": round(cur_share, 4),
                "change": round(change, 4),
            }
        results.append(
            {
                "feature": column,
                "max_abs_share_change": round(max_abs_change, 4),
                "by_category": by_category,
            }
        )
    return results


def drift_report(reference: pd.DataFrame, current: pd.DataFrame) -> Dict[str, Any]:
    """Full drift report comparing `current` against `reference` (training) data."""
    numeric = numeric_feature_drift(reference, current)
    categorical = categorical_feature_drift(reference, current)

    significant = [row["feature"] for row in numeric if row["psi_band"] == "significant_shift"]
    moderate = [row["feature"] for row in numeric if row["psi_band"] == "moderate_shift"]

    return {
        "reference_records": int(len(reference)),
        "current_records": int(len(current)),
        "numeric_features": numeric,
        "categorical_features": categorical,
        "features_with_significant_shift": significant,
        "features_with_moderate_shift": moderate,
        "alert": bool(significant),
        "psi_thresholds": {
            "no_shift_below": PSI_NO_SHIFT,
            "significant_shift_at_or_above": PSI_MODERATE_SHIFT,
        },
        "method": "PSI (population stability index) + two-sample KS test, per numeric feature",
    }
