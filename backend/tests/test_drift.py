"""Feature-drift detection tests (app.ml.drift)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.ml.drift import drift_report
from app.ml.features import CATEGORICAL_FEATURES, NUMERIC_FEATURES


def _synthetic_frame(rng: np.random.Generator, n: int, vibration_scale: float = 1.0) -> pd.DataFrame:
    data = {name: rng.normal(50, 10, n) for name in NUMERIC_FEATURES}
    data["vibration"] = rng.normal(3.0, 0.5, n) * vibration_scale
    data["component_type"] = rng.choice(["Motor", "Steel Rope", "Brake"], n)
    data["material"] = rng.choice(["Steel", "Cast Iron"], n)
    return pd.DataFrame(data)


def test_identically_distributed_samples_show_no_alert():
    rng = np.random.default_rng(7)
    reference = _synthetic_frame(rng, 2000)
    current = _synthetic_frame(rng, 500)

    report = drift_report(reference, current)

    assert report["alert"] is False
    assert report["features_with_significant_shift"] == []
    assert {row["feature"] for row in report["numeric_features"]} >= set(NUMERIC_FEATURES)


def test_a_shifted_feature_is_flagged_and_alerts():
    rng = np.random.default_rng(11)
    reference = _synthetic_frame(rng, 2000)
    current = _synthetic_frame(rng, 500, vibration_scale=4.0)

    report = drift_report(reference, current)

    assert report["alert"] is True
    assert "vibration" in report["features_with_significant_shift"]
    vibration_row = next(row for row in report["numeric_features"] if row["feature"] == "vibration")
    assert vibration_row["psi_band"] == "significant_shift"
    assert vibration_row["ks_pvalue"] < 0.01


def test_categorical_drift_reports_share_changes():
    rng = np.random.default_rng(3)
    reference = _synthetic_frame(rng, 1000)
    current = reference.copy()
    current["component_type"] = "Steel Rope"  # every row now one category

    report = drift_report(reference, current)
    component_row = next(row for row in report["categorical_features"] if row["feature"] == "component_type")
    assert component_row["max_abs_share_change"] > 0.5
    assert set(CATEGORICAL_FEATURES) == {row["feature"] for row in report["categorical_features"]}
