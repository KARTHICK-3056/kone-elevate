"""Train and backtest the end-of-life forecaster.

Pipeline
--------
    generate/load survival data -> preprocess (one-hot + scale) ->
    fit Weibull AFT -> backtest per component type and horizon ->
    persist bundle + forecast_metrics.json

The backtest is the part that matters. A survival model will happily produce
confident-looking probabilities for horizons it has no support for, so
``backtest`` only scores rows whose follow-up window is long enough that the
outcome at that horizon is actually *known* - a row censored at 2 years tells
you nothing about what happened at 5, and including it would quietly flatter
the error.
"""

from __future__ import annotations

import json
import platform
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from app.core.config import settings
from app.core.logging_config import get_logger
from app.ml.features import CATEGORICAL_FEATURES, CATEGORY_LEVELS, FEATURE_COLUMNS, NUMERIC_FEATURES
from app.ml.generate_dataset import generate_survival_dataset, summarise_survival
from app.ml.survival import WeibullAFT

logger = get_logger(__name__)

#: Horizons the planner asks about, in months (plan.md P2).
HORIZON_MONTHS: List[int] = [3, 6, 12, 24]

MONTHS_PER_YEAR = 12.0


def build_preprocessor() -> ColumnTransformer:
    """One-hot the categoricals, standardise the numerics.

    Scaling matters more here than for the forest: the AFT is fitted by
    gradient-based optimisation, and operating_hours (~50,000) alongside
    vibration (~5) is badly enough conditioned to slow or stall convergence.
    """
    encoder = OneHotEncoder(
        categories=[CATEGORY_LEVELS[name] for name in CATEGORICAL_FEATURES],
        handle_unknown="ignore",
        sparse_output=False,
        drop="first",  # avoid the dummy trap - the AFT has an explicit intercept
    )
    return ColumnTransformer(
        transformers=[
            ("categorical", encoder, CATEGORICAL_FEATURES),
            ("numeric", StandardScaler(), NUMERIC_FEATURES),
        ],
        remainder="drop",
        verbose_feature_names_out=False,
    )


def load_or_generate_survival(
    path: Optional[Path] = None,
    n_records: Optional[int] = None,
    seed: Optional[int] = None,
    regenerate: bool = False,
) -> Tuple[pd.DataFrame, str]:
    """Load the survival dataset, generating it first if necessary."""
    path = Path(path or (settings.dataset_file.parent / "survival.csv"))
    n_records = n_records or settings.DATASET_RECORDS
    seed = settings.DATASET_SEED if seed is None else seed

    if path.exists() and not regenerate:
        return pd.read_csv(path), f"loaded from {path}"

    logger.info("Survival dataset not found - generating %s records", f"{n_records:,}")
    frame = generate_survival_dataset(n_records=n_records, seed=seed)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)
    return frame, f"generated ({n_records:,} records) and saved to {path}"


def backtest(
    model: WeibullAFT,
    preprocessor: ColumnTransformer,
    frame: pd.DataFrame,
    horizons_months: Optional[List[int]] = None,
) -> Dict[str, Any]:
    """Compare predicted event counts against observed, per type and horizon.

    Only rows with ``followup_years >= horizon`` are scored: for anyone else
    the true outcome at that horizon is unknown, and counting them as
    "no event" would make the model look better than it is.
    """
    horizons_months = horizons_months or HORIZON_MONTHS
    design = preprocessor.transform(frame[FEATURE_COLUMNS])

    by_horizon: List[Dict[str, Any]] = []
    per_type_errors: Dict[str, List[float]] = {}

    for months in horizons_months:
        horizon_years = months / MONTHS_PER_YEAR
        known = frame["followup_years"].to_numpy() >= horizon_years
        if known.sum() == 0:
            continue

        predicted_probability = model.event_probability_within(design[known], horizon_years)
        actual_event = (
            (frame.loc[known, "event_observed"].to_numpy() == 1)
            & (frame.loc[known, "duration_years"].to_numpy() <= horizon_years)
        )

        predicted_count = float(predicted_probability.sum())
        actual_count = float(actual_event.sum())
        ape = (
            abs(predicted_count - actual_count) / actual_count * 100.0 if actual_count > 0 else None
        )

        types = frame.loc[known, "component_type"].to_numpy()
        per_type: Dict[str, Any] = {}
        for component_type in sorted(set(types)):
            mask = types == component_type
            type_predicted = float(predicted_probability[mask].sum())
            type_actual = float(actual_event[mask].sum())
            if type_actual > 0:
                type_ape = abs(type_predicted - type_actual) / type_actual * 100.0
                per_type_errors.setdefault(component_type, []).append(type_ape)
            else:
                type_ape = None
            per_type[component_type] = {
                "predicted_events": round(type_predicted, 1),
                "actual_events": int(type_actual),
                "absolute_percentage_error": round(type_ape, 2) if type_ape is not None else None,
                "scored_records": int(mask.sum()),
            }

        by_horizon.append(
            {
                "horizon_months": months,
                "scored_records": int(known.sum()),
                "predicted_events": round(predicted_count, 1),
                "actual_events": int(actual_count),
                "absolute_percentage_error": round(ape, 2) if ape is not None else None,
                "by_component_type": per_type,
            }
        )

    mape_by_type = {
        component_type: round(float(np.mean(errors)), 2)
        for component_type, errors in sorted(per_type_errors.items())
    }
    all_errors = [e for errors in per_type_errors.values() for e in errors]

    return {
        "method": (
            "Predicted expected event count (sum of per-component probabilities) vs. "
            "observed events, on the held-out split. Only rows whose follow-up window "
            "covers the horizon are scored, so a censored row is never silently "
            "counted as a non-event."
        ),
        "by_horizon": by_horizon,
        "mape_by_component_type": mape_by_type,
        "mape_overall": round(float(np.mean(all_errors)), 2) if all_errors else None,
    }


def train_forecast_model(
    dataset_path: Optional[Path] = None,
    n_records: Optional[int] = None,
    seed: Optional[int] = None,
    test_size: float = 0.25,
    regenerate: bool = False,
    save: bool = True,
) -> Dict[str, Any]:
    """Fit the Weibull AFT, backtest it, and persist the artefacts."""
    seed = seed if seed is not None else settings.DATASET_SEED
    frame, provenance = load_or_generate_survival(dataset_path, n_records, seed, regenerate)

    missing = [c for c in FEATURE_COLUMNS + ["duration_years", "event_observed"] if c not in frame.columns]
    if missing:
        raise ValueError(f"Survival dataset is missing required columns: {missing}")

    train_frame, test_frame = train_test_split(
        frame, test_size=test_size, random_state=seed, stratify=frame["event_observed"]
    )

    preprocessor = build_preprocessor()
    x_train = preprocessor.fit_transform(train_frame[FEATURE_COLUMNS])
    feature_names = list(preprocessor.get_feature_names_out())

    model = WeibullAFT().fit(
        x_train,
        train_frame["duration_years"].to_numpy(),
        train_frame["event_observed"].to_numpy(),
        feature_names=feature_names,
    )

    trained_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    metrics: Dict[str, Any] = {
        "model": "WeibullAFT",
        "model_version": settings.FORECAST_MODEL_VERSION,
        "trained_at": trained_at,
        "data_source": "synthetic",
        "data_provenance": provenance,
        "total_records": int(len(frame)),
        "training_records": int(len(train_frame)),
        "test_records": int(len(test_frame)),
        "event_rate": round(float(frame["event_observed"].mean()), 4),
        "censoring_rate": round(1.0 - float(frame["event_observed"].mean()), 4),
        "horizons_months": HORIZON_MONTHS,
        "fit": model.summary(),
        "backtest": backtest(model, preprocessor, test_frame),
        "sklearn_version": sklearn.__version__,
        "python_version": platform.python_version(),
        "disclaimer": (
            "Forecasts are derived from synthetic degradation data. They describe "
            "the simulator's wear physics, not observed KONE removals."
        ),
    }

    if save:
        model_path = Path(settings.forecast_model_file)
        model_path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(
            {
                "model": model,
                "preprocessor": preprocessor,
                "feature_columns": FEATURE_COLUMNS,
                "horizons_months": HORIZON_MONTHS,
                "model_version": settings.FORECAST_MODEL_VERSION,
                "trained_at": trained_at,
                "metrics": metrics,
                "data_source": "synthetic",
                "sklearn_version": sklearn.__version__,
                "joblib_version": joblib.__version__,
                "python_version": platform.python_version(),
            },
            model_path,
            compress=3,
        )
        metrics_path = Path(settings.forecast_metrics_file)
        metrics_path.parent.mkdir(parents=True, exist_ok=True)
        metrics_path.write_text(json.dumps(metrics, indent=2, default=str), encoding="utf-8")
        metrics["model_path"] = str(model_path)
        metrics["metrics_path"] = str(metrics_path)

    return metrics


def format_forecast_report(metrics: Dict[str, Any], frame: Optional[pd.DataFrame] = None) -> str:
    """Console summary of a forecast training run."""
    fit = metrics["fit"]
    backtest_result = metrics["backtest"]
    lines = [
        "=" * 72,
        "KONE ELEVATE - end-of-life forecast training report",
        "=" * 72,
        "DATA SOURCE      : SYNTHETIC (not trained on real KONE removals)",
        f"Provenance       : {metrics['data_provenance']}",
        f"Records          : {metrics['total_records']:,} "
        f"(train {metrics['training_records']:,} / test {metrics['test_records']:,})",
        f"Events / censored: {metrics['event_rate'] * 100:.1f}% / {metrics['censoring_rate'] * 100:.1f}%",
        "-" * 72,
        f"Weibull shape k  : {fit['shape_k']}",
        f"                   {fit['shape_interpretation']}",
        f"Converged        : {fit['converged']}   log-likelihood {fit['log_likelihood']}",
        "-" * 72,
        "Backtest - predicted vs actual event counts on the held-out split:",
        f"{'horizon':>9}{'scored':>9}{'predicted':>12}{'actual':>9}{'APE %':>9}",
    ]
    for row in backtest_result["by_horizon"]:
        ape = row["absolute_percentage_error"]
        lines.append(
            f"{str(row['horizon_months']) + 'm':>9}{row['scored_records']:>9,}"
            f"{row['predicted_events']:>12,.1f}{row['actual_events']:>9,}"
            f"{(f'{ape:.2f}' if ape is not None else 'n/a'):>9}"
        )
    lines += ["-" * 72, "MAPE by component type (mean across horizons):"]
    for component_type, mape in backtest_result["mape_by_component_type"].items():
        lines.append(f"    {component_type:<18}{mape:>8.2f}%")
    lines.append(f"    {'OVERALL':<18}{backtest_result['mape_overall']:>8.2f}%")

    if frame is not None:
        lines += ["-" * 72, summarise_survival(frame)]

    lines += [
        "-" * 72,
        f"Model saved      : {metrics.get('model_path')}",
        f"Metrics saved    : {metrics.get('metrics_path')}",
        "=" * 72,
    ]
    return "\n".join(str(line) for line in lines)
