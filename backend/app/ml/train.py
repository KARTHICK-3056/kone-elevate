"""Random Forest training pipeline for the disposition recommender.

The trainer is deliberately end-to-end and reproducible:

    load/generate data -> validate -> three-way stratified split ->
    fit calibrated pipeline -> evaluate -> calibration diagnostics ->
    conformal threshold -> cohort validation -> importances (Gini,
    permutation, SHAP) -> persist bundle + metrics.json + feature_importance.json

The preprocessing (one-hot encoding of the two categorical features) lives
inside a scikit-learn ``Pipeline``, and the *whole pipeline* is wrapped in a
``CalibratedClassifierCV`` and serialised. Inference therefore always applies
exactly the preprocessing and calibration that training used - there is no
separate, drift-prone transform step at serving time.

Three-way split
----------------
``test`` (held out, 20% of all data) is used ONLY for the final reported
metrics (accuracy, confusion matrix, calibration, permutation importance).
``dev`` (64%) is what ``CalibratedClassifierCV(cv=5)`` is fitted on - it
internally holds out folds of *this* split to fit the isotonic calibrators.
``conformal_calib`` (16%) is disjoint from both and is used only to compute
the split-conformal threshold (:mod:`app.ml.conformal`), so the coverage
guarantee is not contaminated by data the classifier or calibrators have
seen.
"""

from __future__ import annotations

import json
import platform
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import joblib
import numpy as np
import pandas as pd
import shap
import sklearn
from sklearn.calibration import CalibratedClassifierCV
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.inspection import permutation_importance
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from app.core.config import settings
from app.core.logging_config import get_logger
from app.ml import conformal, life_calibration
from app.ml import cost_matrix as cost_matrix_module
from app.ml.abstention import abstention_report
from app.ml.calibration_metrics import brier_score_per_class, expected_calibration_error
from app.ml.features import (
    CATEGORICAL_FEATURES,
    CATEGORY_LEVELS,
    FEATURE_COLUMNS,
    NUMERIC_FEATURES,
    TARGET_COLUMN,
)
from app.ml.generate_dataset import generate_dataset, save_dataset
from app.utils.enums import Recommendation

logger = get_logger(__name__)

CLASS_ORDER: List[str] = [
    Recommendation.CONTINUE_USING.value,
    Recommendation.COMPONENT_RECOVERY.value,
    Recommendation.MATERIAL_RECOVERY.value,
    Recommendation.DISPOSE.value,
]

DEFAULT_HYPERPARAMETERS: Dict[str, Any] = {
    "n_estimators": 400,
    "max_depth": 16,
    "min_samples_split": 8,
    "min_samples_leaf": 3,
    "max_features": "sqrt",
    "class_weight": "balanced_subsample",
    "n_jobs": -1,
    "random_state": 42,
}

#: Marginal miscoverage rate for the split-conformal prediction sets - 0.1
#: targets 90% coverage (see app.ml.conformal).
CONFORMAL_ALPHA = 0.1

#: A component is treated as "installed" this many years before a fixed
#: reference year, purely so cohort validation has a temporal axis to split
#: on. This is synthetic data with no real installation calendar; the
#: reference year is fixed (not "now") so results are reproducible.
COHORT_REFERENCE_YEAR = 2026

#: How many rows to sample for the (comparatively expensive) SHAP pass.
SHAP_SAMPLE_SIZE = 300


@dataclass
class TrainingResult:
    """Everything produced by a training run."""

    pipeline: Any  # CalibratedClassifierCV
    metrics: Dict[str, Any]
    feature_importance: Dict[str, float]
    model_version: str
    trained_at: str
    explainer_pipeline: Optional[Pipeline] = None
    conformal_q_hat: Optional[float] = None
    model_path: Optional[Path] = None
    metrics_path: Optional[Path] = None
    importance_path: Optional[Path] = None
    warnings: List[str] = field(default_factory=list)


# --------------------------------------------------------------------------
# Data loading and validation
# --------------------------------------------------------------------------
def load_or_generate(
    dataset_path: Optional[Path] = None,
    n_records: Optional[int] = None,
    seed: Optional[int] = None,
    regenerate: bool = False,
) -> Tuple[pd.DataFrame, str]:
    """Load the dataset from disk, generating it first if necessary."""
    dataset_path = Path(dataset_path or settings.dataset_file)
    n_records = n_records or settings.DATASET_RECORDS
    seed = settings.DATASET_SEED if seed is None else seed

    if dataset_path.exists() and not regenerate:
        frame = pd.read_csv(dataset_path)
        return frame, f"loaded from {dataset_path}"

    logger.info("Dataset not found - generating %s synthetic records", f"{n_records:,}")
    frame = generate_dataset(n_records=n_records, seed=seed)
    save_dataset(frame, dataset_path, split=True, seed=seed)
    return frame, f"generated ({n_records:,} records) and saved to {dataset_path}"


def validate_dataset(frame: pd.DataFrame) -> List[str]:
    """Fail fast on structural problems; return non-fatal warnings."""
    missing = [column for column in FEATURE_COLUMNS + [TARGET_COLUMN] if column not in frame.columns]
    if missing:
        raise ValueError(f"Dataset is missing required columns: {missing}")

    if frame.empty:
        raise ValueError("Dataset is empty - nothing to train on")

    present_classes = set(frame[TARGET_COLUMN].unique())
    unexpected = present_classes - set(CLASS_ORDER)
    if unexpected:
        raise ValueError(f"Dataset contains unknown target classes: {sorted(unexpected)}")
    if len(present_classes) < 2:
        raise ValueError("Dataset must contain at least two target classes")

    warnings: List[str] = []
    if len(present_classes) < len(CLASS_ORDER):
        warnings.append(
            f"Only {len(present_classes)} of {len(CLASS_ORDER)} classes present: "
            f"{sorted(present_classes)}"
        )
    if len(frame) < 1000:
        warnings.append(f"Small dataset ({len(frame)} rows) - metrics will be unstable")

    null_counts = frame[FEATURE_COLUMNS].isna().sum()
    nulls = {name: int(count) for name, count in null_counts.items() if count}
    if nulls:
        warnings.append(f"Null feature values were imputed with column medians: {nulls}")

    leakage = [column for column in ("health_score", "latent_degradation") if column in FEATURE_COLUMNS]
    if leakage:  # pragma: no cover - guards against a bad edit to features.py
        raise ValueError(f"Target leakage risk: {leakage} must not be model features")

    return warnings


def _impute(frame: pd.DataFrame) -> pd.DataFrame:
    """Fill any residual nulls so the estimator never sees NaN."""
    frame = frame.copy()
    for column in NUMERIC_FEATURES:
        if frame[column].isna().any():
            frame[column] = frame[column].fillna(frame[column].median())
    for column in CATEGORICAL_FEATURES:
        if frame[column].isna().any():
            frame[column] = frame[column].fillna("Unknown")
    return frame


# --------------------------------------------------------------------------
# Pipeline
# --------------------------------------------------------------------------
def build_pipeline(hyperparameters: Optional[Dict[str, Any]] = None) -> Pipeline:
    """Assemble the preprocessing + Random Forest pipeline."""
    params = {**DEFAULT_HYPERPARAMETERS, **(hyperparameters or {})}

    encoder = OneHotEncoder(
        categories=[CATEGORY_LEVELS[name] for name in CATEGORICAL_FEATURES],
        handle_unknown="ignore",
        sparse_output=False,
    )
    preprocessor = ColumnTransformer(
        transformers=[
            ("categorical", encoder, CATEGORICAL_FEATURES),
            ("numeric", "passthrough", NUMERIC_FEATURES),
        ],
        remainder="drop",
        verbose_feature_names_out=False,
    )
    return Pipeline(
        steps=[
            ("preprocessor", preprocessor),
            ("classifier", RandomForestClassifier(**params)),
        ]
    )


def _encoded_name_to_original(encoded_name: str) -> Optional[str]:
    """Map a one-hot encoded column name back to its original feature name."""
    for original in CATEGORICAL_FEATURES:
        if encoded_name == original or encoded_name.startswith(f"{original}_"):
            return original
    return encoded_name if encoded_name in FEATURE_COLUMNS else None


def _single_pipeline_importance(pipeline: Pipeline) -> Dict[str, float]:
    """Gini importance for one fitted Pipeline, aggregated onto original features."""
    classifier: RandomForestClassifier = pipeline.named_steps["classifier"]
    preprocessor: ColumnTransformer = pipeline.named_steps["preprocessor"]
    encoded_names = list(preprocessor.get_feature_names_out())
    importances = classifier.feature_importances_

    aggregated: Dict[str, float] = {name: 0.0 for name in FEATURE_COLUMNS}
    for encoded_name, importance in zip(encoded_names, importances, strict=True):
        target = _encoded_name_to_original(encoded_name)
        if target is None:  # pragma: no cover - defensive
            continue
        aggregated[target] += float(importance)
    return aggregated


def fold_pipelines(calibrated: CalibratedClassifierCV) -> List[Pipeline]:
    """The fitted base Pipeline for each internal CalibratedClassifierCV fold."""
    return [fold.estimator for fold in calibrated.calibrated_classifiers_]


def average_feature_importance(pipelines: List[Pipeline]) -> Dict[str, float]:
    """Gini importance averaged across every calibration fold's fitted pipeline.

    Averaging (rather than picking one fold) uses the full ensemble the
    calibrated model actually predicts with, not an arbitrary single fold.
    """
    totals: Dict[str, float] = {name: 0.0 for name in FEATURE_COLUMNS}
    for pipeline in pipelines:
        for name, value in _single_pipeline_importance(pipeline).items():
            totals[name] += value
    n = max(len(pipelines), 1)
    averaged = {name: value / n for name, value in totals.items()}
    total = sum(averaged.values()) or 1.0
    return {
        name: round(value / total, 6)
        for name, value in sorted(averaged.items(), key=lambda item: item[1], reverse=True)
    }


def permutation_importance_table(
    calibrated: CalibratedClassifierCV, x_test: pd.DataFrame, y_test: pd.Series, seed: int
) -> Dict[str, float]:
    """Permutation importance of the deployed (calibrated) model on the test set.

    Unlike Gini importance, this is not biased toward high-cardinality
    features: it measures the actual drop in held-out f1_macro when a
    feature's values are shuffled, on the exact model that gets deployed.
    """
    result = permutation_importance(
        calibrated, x_test, y_test, n_repeats=10, random_state=seed, scoring="f1_macro", n_jobs=-1
    )
    raw = {
        column: max(float(value), 0.0)
        for column, value in zip(x_test.columns, result.importances_mean, strict=True)
    }
    total = sum(raw.values()) or 1.0
    return {
        name: round(value / total, 6)
        for name, value in sorted(raw.items(), key=lambda item: item[1], reverse=True)
    }


def shap_importance_table(
    explainer_pipeline: Pipeline, x_test: pd.DataFrame, seed: int, sample_size: int = SHAP_SAMPLE_SIZE
) -> Dict[str, float]:
    """Mean |SHAP value| per original feature, from one representative fold.

    Computed on a random sample of the held-out test set (SHAP's exact
    TreeExplainer is fast for a single forest, but scales with sample size x
    tree count x classes). Labelled everywhere it is surfaced as coming from
    "one representative fold of the 5-fold calibrated ensemble", not the full
    ensemble - see docs/model-card.md for the full disclosure.
    """
    rng = np.random.default_rng(seed)
    sample = x_test if len(x_test) <= sample_size else x_test.sample(sample_size, random_state=seed)
    preprocessor: ColumnTransformer = explainer_pipeline.named_steps["preprocessor"]
    classifier: RandomForestClassifier = explainer_pipeline.named_steps["classifier"]

    transformed = preprocessor.transform(sample)
    encoded_names = list(preprocessor.get_feature_names_out())

    explainer = shap.TreeExplainer(classifier)
    shap_values = explainer.shap_values(transformed)  # (n_samples, n_features, n_classes)
    # Mean absolute contribution per feature, averaged over samples AND classes -
    # a feature that matters for any disposition should rank highly overall.
    mean_abs = np.abs(shap_values).mean(axis=(0, 2))

    aggregated: Dict[str, float] = {name: 0.0 for name in FEATURE_COLUMNS}
    for encoded_name, value in zip(encoded_names, mean_abs, strict=True):
        target = _encoded_name_to_original(encoded_name)
        if target is None:  # pragma: no cover - defensive
            continue
        aggregated[target] += float(value)

    total = sum(aggregated.values()) or 1.0
    _ = rng  # reserved for future stochastic sampling strategies
    return {
        name: round(value / total, 6)
        for name, value in sorted(aggregated.items(), key=lambda item: item[1], reverse=True)
    }


# --------------------------------------------------------------------------
# Evaluation
# --------------------------------------------------------------------------
def evaluate(
    estimator: Any,
    x_test: pd.DataFrame,
    y_test: pd.Series,
    labels: List[str],
) -> Dict[str, Any]:
    """Compute the full evaluation report for a fitted estimator."""
    predictions = estimator.predict(x_test)
    probabilities = estimator.predict_proba(x_test)

    report = classification_report(
        y_test, predictions, labels=labels, output_dict=True, zero_division=0
    )
    matrix = confusion_matrix(y_test, predictions, labels=labels)

    per_class = {
        label: {
            "precision": round(float(report[label]["precision"]), 4),
            "recall": round(float(report[label]["recall"]), 4),
            "f1": round(float(report[label]["f1-score"]), 4),
            "support": int(report[label]["support"]),
        }
        for label in labels
        if label in report
    }

    max_probability = probabilities.max(axis=1)
    correct = predictions == y_test.to_numpy()

    correct_confidence = round(float(max_probability[correct].mean()), 4) if correct.any() else None
    incorrect_confidence = (
        round(float(max_probability[~correct].mean()), 4) if (~correct).any() else None
    )

    return {
        "accuracy": round(float(accuracy_score(y_test, predictions)), 4),
        "precision_macro": round(
            float(precision_score(y_test, predictions, average="macro", zero_division=0)), 4
        ),
        "recall_macro": round(
            float(recall_score(y_test, predictions, average="macro", zero_division=0)), 4
        ),
        "f1_macro": round(float(f1_score(y_test, predictions, average="macro", zero_division=0)), 4),
        "f1_weighted": round(
            float(f1_score(y_test, predictions, average="weighted", zero_division=0)), 4
        ),
        "per_class": per_class,
        "labels": labels,
        "confusion_matrix": matrix.tolist(),
        "classification_report_text": classification_report(
            y_test, predictions, labels=labels, zero_division=0
        ),
        "test_records": int(len(y_test)),
        "mean_confidence": round(float(max_probability.mean()), 4),
        "mean_confidence_correct": correct_confidence,
        "mean_confidence_incorrect": incorrect_confidence,
    }


def cost_analysis(
    estimator: Any, x_test: pd.DataFrame, y_test: pd.Series, labels: List[str]
) -> Dict[str, Any]:
    """Compare the argmax-probability decision against the cost-optimal one.

    Reports mean expected cost (app.ml.cost_matrix) for both strategies and
    how often they disagree, and the realised mean cost of each strategy's
    actual choices against the true labels - the number a quality engineer
    will ask for instead of macro F1.
    """
    probabilities = estimator.predict_proba(x_test)
    classes = list(estimator.classes_)
    component_types = x_test["component_type"].to_numpy()
    true_labels = y_test.to_numpy()

    argmax_expected, cost_optimal_expected = [], []
    argmax_realised, cost_optimal_realised = [], []
    disagreements = 0

    for row_index in range(len(x_test)):
        probability_map = {label: float(probabilities[row_index, col]) for col, label in enumerate(classes)}
        component_type = component_types[row_index]
        actual = true_labels[row_index]

        argmax_choice = max(probability_map, key=probability_map.get)
        decision = cost_matrix_module.best_decision(probability_map, component_type)
        cost_optimal_choice = decision["cost_optimal_recommendation"]

        argmax_expected.append(decision["expected_cost_by_class"][argmax_choice])
        cost_optimal_expected.append(decision["expected_cost_by_class"][cost_optimal_choice])
        argmax_realised.append(cost_matrix_module.cost_of(actual, argmax_choice, component_type))
        cost_optimal_realised.append(cost_matrix_module.cost_of(actual, cost_optimal_choice, component_type))
        if argmax_choice != cost_optimal_choice:
            disagreements += 1

    n = max(len(x_test), 1)
    return {
        "cost_matrix_version": cost_matrix_module.COST_MATRIX_VERSION,
        "argmax_mean_expected_cost": round(float(np.mean(argmax_expected)), 4),
        "cost_optimal_mean_expected_cost": round(float(np.mean(cost_optimal_expected)), 4),
        "argmax_mean_realised_cost": round(float(np.mean(argmax_realised)), 4),
        "cost_optimal_mean_realised_cost": round(float(np.mean(cost_optimal_realised)), 4),
        "decisions_where_cost_optimal_differs_from_argmax": disagreements,
        "decisions_where_cost_optimal_differs_from_argmax_percent": round(100.0 * disagreements / n, 2),
        "labels": labels,
        "disclaimer": (
            "Costs are relative units reflecting error-type asymmetry (optimistic vs "
            "conservative, safety-critical vs not), not currency - see app.ml.cost_matrix."
        ),
    }


def cohort_validation(
    frame: pd.DataFrame, hyperparameters: Optional[Dict[str, Any]], seed: int
) -> Dict[str, Any]:
    """Train/test split by (synthetic) installation year instead of randomly.

    A random split lets the model see components from every era in training;
    a real deployment has to generalise from older installations to newer
    ones it has never seen. This fits a fresh, uncalibrated pipeline on the
    "older" cohort and evaluates it on the "newer" one, so the honest,
    harder-won number sits next to the random-split metrics rather than
    replacing them.
    """
    working = frame.copy()
    working["_installation_year"] = (
        COHORT_REFERENCE_YEAR - working["component_age"].round()
    ).astype(int)
    cutoff = int(working["_installation_year"].quantile(0.7))

    older = working[working["_installation_year"] <= cutoff]
    newer = working[working["_installation_year"] > cutoff]

    if len(older) < 50 or len(newer) < 50 or newer[TARGET_COLUMN].nunique() < 2:
        return {
            "status": "skipped",
            "reason": "insufficient rows in one cohort to fit/evaluate",
            "cutoff_installation_year": cutoff,
        }

    labels = [label for label in CLASS_ORDER if label in set(newer[TARGET_COLUMN].unique())]
    pipeline = build_pipeline(hyperparameters)
    pipeline.fit(older[FEATURE_COLUMNS], older[TARGET_COLUMN])
    result = evaluate(pipeline, newer[FEATURE_COLUMNS], newer[TARGET_COLUMN], labels)
    result.pop("classification_report_text", None)
    result.pop("confusion_matrix", None)

    return {
        "status": "ok",
        "cutoff_installation_year": cutoff,
        "older_cohort_records": int(len(older)),
        "newer_cohort_records": int(len(newer)),
        "note": (
            "Trained on components with synthetic installation_year <= cutoff, "
            "evaluated on installation_year > cutoff. Expect these numbers to be "
            "lower than the random-split metrics - that drop is the honest signal "
            "of temporal generalisation difficulty, not a bug."
        ),
        **result,
    }


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------
def train_model(
    dataset_path: Optional[Path] = None,
    n_records: Optional[int] = None,
    seed: Optional[int] = None,
    test_size: float = 0.2,
    hyperparameters: Optional[Dict[str, Any]] = None,
    cross_validate: bool = True,
    regenerate: bool = False,
    save: bool = True,
    model_path: Optional[Path] = None,
) -> TrainingResult:
    """Run the complete training pipeline and (optionally) persist artefacts."""
    seed = seed if seed is not None else settings.DATASET_SEED
    frame, provenance = load_or_generate(dataset_path, n_records, seed, regenerate)
    warnings = validate_dataset(frame)
    frame = _impute(frame)

    features = frame[FEATURE_COLUMNS]
    target = frame[TARGET_COLUMN]
    labels = [label for label in CLASS_ORDER if label in set(target.unique())]

    # Three-way split: test (final metrics) / conformal_calib (conformal
    # threshold only) / dev (fed into CalibratedClassifierCV's internal cv=5).
    x_trainval, x_test, y_trainval, y_test = train_test_split(
        features, target, test_size=test_size, random_state=seed, stratify=target
    )
    x_dev, x_conformal, y_dev, y_conformal = train_test_split(
        x_trainval, y_trainval, test_size=0.2, random_state=seed, stratify=y_trainval
    )

    calibrated = CalibratedClassifierCV(build_pipeline(hyperparameters), method="isotonic", cv=5)
    calibrated.fit(x_dev, y_dev)
    classes = list(calibrated.classes_)

    metrics = evaluate(calibrated, x_test, y_test, labels)
    metrics["training_records"] = int(len(x_dev))
    metrics["conformal_calibration_records"] = int(len(x_conformal))
    metrics["total_records"] = int(len(frame))
    metrics["class_distribution"] = {
        label: int(count) for label, count in target.value_counts().items()
    }
    metrics["data_provenance"] = provenance
    metrics["data_source"] = "synthetic"
    metrics["hyperparameters"] = {**DEFAULT_HYPERPARAMETERS, **(hyperparameters or {})}
    metrics["feature_columns"] = FEATURE_COLUMNS
    metrics["sklearn_version"] = sklearn.__version__
    metrics["python_version"] = platform.python_version()
    metrics["calibration_method"] = "isotonic"
    metrics["calibration_cv_folds"] = 5

    if cross_validate:
        # Robustness check only (not used for calibration or thresholds):
        # 5-fold f1_macro of an uncalibrated pipeline, restricted to x_trainval
        # so the held-out test set never leaks into a reported CV number.
        from sklearn.model_selection import cross_val_score

        scores = cross_val_score(
            build_pipeline(hyperparameters), x_trainval, y_trainval, cv=5, scoring="f1_macro", n_jobs=-1
        )
        metrics["cv_f1_macro_mean"] = round(float(scores.mean()), 4)
        metrics["cv_f1_macro_std"] = round(float(scores.std()), 4)
        metrics["cv_folds"] = 5

    # -- calibration diagnostics ------------------------------------------
    test_probabilities = calibrated.predict_proba(x_test)
    metrics["brier_score_per_class"] = brier_score_per_class(
        test_probabilities, y_test.to_numpy(), classes
    )
    metrics["calibration"] = expected_calibration_error(test_probabilities, y_test.to_numpy(), classes)

    # -- split-conformal threshold (disjoint calibration split) -----------
    conformal_probabilities = calibrated.predict_proba(x_conformal)
    q_hat = conformal.conformal_threshold(
        conformal_probabilities, y_conformal.to_numpy(), classes, alpha=CONFORMAL_ALPHA
    )
    metrics["conformal"] = {
        "alpha": CONFORMAL_ALPHA,
        "target_coverage": round(1 - CONFORMAL_ALPHA, 4),
        "q_hat": round(q_hat, 4),
        "calibration_records": int(len(x_conformal)),
        "method": "split-conformal (LAC / Sadinle-Lei-Wasserman 2019)",
    }

    # -- abstention: what DEFER_TO_INSPECTION would do on the test set -----
    metrics["abstention"] = abstention_report(test_probabilities, y_test.to_numpy(), classes, q_hat)

    # -- importances: Gini (avg across folds), permutation, SHAP ----------
    folds = fold_pipelines(calibrated)
    gini_importance = average_feature_importance(folds)
    metrics["feature_importance"] = gini_importance
    metrics["permutation_importance"] = permutation_importance_table(calibrated, x_test, y_test, seed)
    metrics["shap_importance"] = shap_importance_table(folds[0], x_test, seed)
    metrics["explanation_methods"] = ["gini", "permutation", "shap_treeexplainer"]

    # -- cost-sensitive decision analysis ----------------------------------
    metrics["cost_analysis"] = cost_analysis(calibrated, x_test, y_test, labels)

    # -- cohort (temporal) validation, published beside the random split ---
    metrics["cohort_validation"] = cohort_validation(frame, hyperparameters, seed)

    trained_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    model_version = settings.MODEL_VERSION
    metrics["model_version"] = model_version
    metrics["trained_at"] = trained_at

    result = TrainingResult(
        pipeline=calibrated,
        metrics=metrics,
        feature_importance=gini_importance,
        model_version=model_version,
        trained_at=trained_at,
        explainer_pipeline=folds[0],
        conformal_q_hat=q_hat,
        warnings=warnings,
    )

    if save:
        result.model_path = _persist_model(result, classes, model_path)
        if model_path is None:
            # The life model's nominal duty and inspection mapping are fitted
            # on the same training split, so a retrain never leaves them
            # describing a different dataset.
            _refit_life_calibration(Path(dataset_path or settings.dataset_file))
        result.metrics_path = _write_json(settings.metrics_file, metrics)
        result.importance_path = _write_json(
            settings.importance_file,
            {
                "model_version": model_version,
                "trained_at": trained_at,
                "data_source": "synthetic",
                "feature_importance": gini_importance,
                "permutation_importance": metrics["permutation_importance"],
                "shap_importance": metrics["shap_importance"],
            },
        )

    return result


def _refit_life_calibration(dataset_path: Path) -> Optional[Path]:
    """Refit ``life_calibration.json`` on the training split (``train.csv``)."""
    train_split = dataset_path.with_name("train.csv")
    if not train_split.exists():
        logger.warning("No %s - life calibration left unchanged", train_split)
        return None
    calibration = life_calibration.fit(pd.read_csv(train_split), source="/".join(train_split.parts[-3:]))
    return life_calibration.save(calibration)


def _persist_model(
    result: TrainingResult, classes: List[str], model_path: Optional[Path] = None
) -> Path:
    """Serialise the full bundle (calibrated pipeline + contract + metrics)."""
    path = Path(model_path or settings.model_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    bundle = {
        "pipeline": result.pipeline,
        "explainer_pipeline": result.explainer_pipeline,
        "feature_columns": FEATURE_COLUMNS,
        "categorical_features": CATEGORICAL_FEATURES,
        "numeric_features": NUMERIC_FEATURES,
        "classes": classes,
        "class_order": CLASS_ORDER,
        "model_version": result.model_version,
        "trained_at": result.trained_at,
        "metrics": {
            key: value
            for key, value in result.metrics.items()
            if key not in {"classification_report_text"}
        },
        "feature_importance": result.feature_importance,
        "conformal_q_hat": result.conformal_q_hat,
        "conformal_alpha": CONFORMAL_ALPHA,
        "cost_matrix_version": cost_matrix_module.COST_MATRIX_VERSION,
        "data_source": "synthetic",
        "sklearn_version": sklearn.__version__,
        "joblib_version": joblib.__version__,
        "python_version": platform.python_version(),
    }
    joblib.dump(bundle, path, compress=3)
    return path


def _write_json(path: Path, payload: Dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialisable = {
        key: value for key, value in payload.items() if key != "classification_report_text"
    }
    path.write_text(json.dumps(serialisable, indent=2, default=str), encoding="utf-8")
    return path


def format_report(result: TrainingResult) -> str:
    """Render a console-friendly training summary."""
    metrics = result.metrics
    lines = [
        "=" * 68,
        "KONE ELEVATE - Random Forest training report",
        "=" * 68,
        "DATA SOURCE      : SYNTHETIC (not trained on real KONE data)",
        f"Provenance       : {metrics.get('data_provenance')}",
        f"Dataset          : {metrics.get('total_records', 0):,} records",
        f"Dev / Conformal / Test : {metrics.get('training_records', 0):,} / "
        f"{metrics.get('conformal_calibration_records', 0):,} / {metrics.get('test_records', 0):,}",
        f"Classes          : {', '.join(metrics.get('labels', []))}",
        "-" * 68,
        "Class distribution:",
    ]
    for label, count in metrics.get("class_distribution", {}).items():
        share = 100.0 * count / max(metrics.get("total_records", 1), 1)
        lines.append(f"    {label:<10} {count:>7,}  ({share:5.1f}%)")

    lines += [
        "-" * 68,
        f"Accuracy         : {metrics['accuracy'] * 100:.2f}%",
        f"Precision (macro): {metrics['precision_macro'] * 100:.2f}%",
        f"Recall (macro)   : {metrics['recall_macro'] * 100:.2f}%",
        f"F1 (macro)       : {metrics['f1_macro'] * 100:.2f}%",
        f"F1 (weighted)    : {metrics['f1_weighted'] * 100:.2f}%",
    ]
    if "cv_f1_macro_mean" in metrics:
        lines.append(
            f"CV F1 (5-fold)   : {metrics['cv_f1_macro_mean'] * 100:.2f}% "
            f"(+/- {metrics['cv_f1_macro_std'] * 100:.2f})"
        )
    lines += [
        f"Mean confidence  : {metrics['mean_confidence']:.3f} "
        f"(correct {metrics.get('mean_confidence_correct')}, "
        f"incorrect {metrics.get('mean_confidence_incorrect')})",
        f"Calibration (ECE): {metrics['calibration']['expected_calibration_error']:.4f} "
        f"({metrics['calibration_method']}, {metrics['calibration_cv_folds']}-fold)",
        f"Conformal q_hat  : {metrics['conformal']['q_hat']:.4f} "
        f"(target coverage {metrics['conformal']['target_coverage'] * 100:.0f}%)",
        f"Abstention rate  : {metrics['abstention']['abstention_rate'] * 100:.1f}% | "
        f"answered accuracy {metrics['abstention']['accuracy_on_answered_subset'] * 100:.1f}% "
        f"(vs {metrics['accuracy'] * 100:.1f}% without abstention)",
        "-" * 68,
        "Classification report:",
        metrics.get("classification_report_text", ""),
        "-" * 68,
        "Confusion matrix (rows = actual, columns = predicted):",
        " " * 10 + "".join(f"{label:>12}" for label in metrics["labels"]),
    ]
    for label, row in zip(metrics["labels"], metrics["confusion_matrix"], strict=True):
        lines.append(f"{label:<10}" + "".join(f"{value:>12,}" for value in row))

    lines += ["-" * 68, "Feature importance (Gini, averaged across calibration folds):"]
    for name, value in list(result.feature_importance.items()):
        bar = "#" * int(round(value * 120))
        lines.append(f"    {name:<26} {value:6.4f}  {bar}")

    cohort = metrics.get("cohort_validation", {})
    lines += ["-" * 68, "Cohort (installation-year) validation:"]
    if cohort.get("status") == "ok":
        lines.append(
            f"    cutoff year {cohort['cutoff_installation_year']} | "
            f"older={cohort['older_cohort_records']:,} newer={cohort['newer_cohort_records']:,} | "
            f"accuracy={cohort['accuracy'] * 100:.2f}% f1_macro={cohort['f1_macro'] * 100:.2f}% "
            f"(random-split accuracy was {metrics['accuracy'] * 100:.2f}%)"
        )
    else:
        lines.append(f"    skipped: {cohort.get('reason')}")

    cost = metrics.get("cost_analysis", {})
    lines += [
        "-" * 68,
        "Cost-sensitive decision analysis (relative units, see app.ml.cost_matrix):",
        f"    mean expected cost, argmax choice       : {cost.get('argmax_mean_expected_cost')}",
        f"    mean expected cost, cost-optimal choice  : {cost.get('cost_optimal_mean_expected_cost')}",
        f"    decisions where they differ              : "
        f"{cost.get('decisions_where_cost_optimal_differs_from_argmax_percent')}%",
    ]

    if result.warnings:
        lines += ["-" * 68, "Warnings:"]
        lines += [f"    ! {warning}" for warning in result.warnings]

    lines += [
        "-" * 68,
        f"Model version    : {result.model_version}",
        f"Model saved      : {result.model_path}",
        f"Metrics saved    : {result.metrics_path}",
        f"Importance saved : {result.importance_path}",
        "=" * 68,
    ]
    return "\n".join(str(line) for line in lines)


def main() -> None:  # pragma: no cover - CLI entry point
    import argparse

    parser = argparse.ArgumentParser(description="Train the KONE ELEVATE Random Forest model.")
    parser.add_argument("--records", type=int, default=None)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--test-size", type=float, default=0.2)
    parser.add_argument("--regenerate", action="store_true", help="Force dataset regeneration")
    parser.add_argument("--no-cv", action="store_true", help="Skip 5-fold cross-validation")
    parser.add_argument("--estimators", type=int, default=None)
    args = parser.parse_args()

    hyperparameters = {"n_estimators": args.estimators} if args.estimators else None
    result = train_model(
        n_records=args.records,
        seed=args.seed,
        test_size=args.test_size,
        hyperparameters=hyperparameters,
        cross_validate=not args.no_cv,
        regenerate=args.regenerate,
    )
    print(format_report(result))


if __name__ == "__main__":  # pragma: no cover
    main()
