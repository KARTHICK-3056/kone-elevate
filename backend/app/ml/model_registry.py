"""In-process model registry.

The serialised scikit-learn pipeline is loaded exactly once per process and
cached in memory. Loading a joblib bundle on every request would add tens of
milliseconds and a lot of GC churn for no benefit.

The registry degrades gracefully: if the model file is missing (for example on
a fresh clone before ``train_model.py`` has been run) the API stays up and the
prediction service falls back to the transparent health-score heuristic, with
``model_available = false`` reported to the client.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

import joblib
import sklearn

from app.core.config import settings
from app.core.logging_config import get_logger

logger = get_logger(__name__)

BUNDLE_KEYS = (
    "pipeline",
    "explainer_pipeline",
    "feature_columns",
    "categorical_features",
    "numeric_features",
    "classes",
    "model_version",
    "trained_at",
    "metrics",
    "feature_importance",
    "conformal_q_hat",
    "conformal_alpha",
)

#: Set ALLOW_MODEL_VERSION_MISMATCH=1 only for local debugging of a bundle
#: trained on a different machine. Never set it in a deployed environment -
#: silently unpickling a model with a mismatched scikit-learn/joblib version
#: is the exact class of bug this check exists to catch.
_ALLOW_VERSION_MISMATCH = os.environ.get("ALLOW_MODEL_VERSION_MISMATCH") == "1"


class ModelNotAvailableError(RuntimeError):
    """Raised when a caller requires a trained model that is not present."""


class ModelVersionMismatchError(RuntimeError):
    """Raised when a bundle was pickled by a different scikit-learn/joblib.

    A joblib-pickled scikit-learn estimator is only guaranteed to unpickle
    correctly under the exact library versions that created it. Loading it
    anyway can succeed while silently producing wrong predictions - a failure
    mode with no stack trace and no error message. Failing loudly here trades
    an inconvenient restart for that risk.
    """


class ModelRegistry:
    """Thread-safe lazy loader for the trained Random Forest bundle."""

    def __init__(self, model_path: Optional[Path] = None) -> None:
        self._model_path = Path(model_path) if model_path else settings.model_file
        self._bundle: Optional[Dict[str, Any]] = None
        self._lock = threading.Lock()
        self._load_error: Optional[str] = None
        self._shap_explainer: Optional[Any] = None

    # ------------------------------------------------------------------ io
    @property
    def model_path(self) -> Path:
        return self._model_path

    def load(self, force: bool = False) -> Optional[Dict[str, Any]]:
        """Load (or reload) the bundle from disk. Returns None when missing."""
        if self._bundle is not None and not force:
            return self._bundle

        with self._lock:
            if self._bundle is not None and not force:
                return self._bundle
            if not self._model_path.exists():
                self._load_error = f"Model file not found at {self._model_path}"
                logger.warning(
                    "%s - prediction API will fall back to the heuristic scorer.",
                    self._load_error,
                )
                return None
            try:
                bundle = joblib.load(self._model_path)
            except Exception as exc:  # pragma: no cover - corrupted artefact
                self._load_error = f"Failed to load model: {exc}"
                logger.exception("Could not load model bundle")
                return None

            missing = [key for key in ("pipeline", "feature_columns", "classes") if key not in bundle]
            if missing:
                self._load_error = f"Model bundle is missing keys: {missing}"
                logger.error(self._load_error)
                return None

            trained_sklearn = bundle.get("sklearn_version")
            trained_joblib = bundle.get("joblib_version")
            mismatches = []
            if trained_sklearn and trained_sklearn != sklearn.__version__:
                mismatches.append(f"scikit-learn: trained {trained_sklearn}, running {sklearn.__version__}")
            if trained_joblib and trained_joblib != joblib.__version__:
                mismatches.append(f"joblib: trained {trained_joblib}, running {joblib.__version__}")
            if mismatches and not _ALLOW_VERSION_MISMATCH:
                self._load_error = (
                    "Model bundle version mismatch - refusing to load: "
                    + "; ".join(mismatches)
                    + ". Retrain with the installed versions (python scripts/train_model.py) "
                    "or install the exact pinned versions from requirements.lock."
                )
                logger.error(self._load_error)
                raise ModelVersionMismatchError(self._load_error)

            self._bundle = bundle
            self._load_error = None
            logger.info(
                "Loaded model %s (trained %s) from %s",
                bundle.get("model_version"),
                bundle.get("trained_at"),
                self._model_path,
            )
            return self._bundle

    def reload(self) -> Optional[Dict[str, Any]]:
        """Force a reload from disk (used after retraining)."""
        self._bundle = None
        self._shap_explainer = None
        return self.load(force=True)

    # -------------------------------------------------------------- access
    @property
    def is_available(self) -> bool:
        return self.load() is not None

    @property
    def bundle(self) -> Dict[str, Any]:
        bundle = self.load()
        if bundle is None:
            raise ModelNotAvailableError(
                self._load_error
                or "No trained model available. Run: python scripts/train_model.py"
            )
        return bundle

    @property
    def pipeline(self):
        """The calibrated model (CalibratedClassifierCV) used for predict_proba."""
        return self.bundle["pipeline"]

    @property
    def explainer_pipeline(self):
        """One representative fitted fold Pipeline, used for SHAP/Gini explanations.

        Distinct from ``pipeline`` (the full calibrated ensemble) because SHAP's
        TreeExplainer needs a single tree-based estimator, not a calibration
        wrapper. See app.ml.train.shap_importance_table for the same tradeoff
        made at training time.
        """
        return self.bundle.get("explainer_pipeline")

    @property
    def conformal_q_hat(self) -> Optional[float]:
        """Split-conformal threshold for prediction sets (app.ml.conformal)."""
        bundle = self.load()
        return None if bundle is None else bundle.get("conformal_q_hat")

    @property
    def conformal_alpha(self) -> Optional[float]:
        bundle = self.load()
        return None if bundle is None else bundle.get("conformal_alpha")

    @property
    def shap_explainer(self):
        """Lazily-built, cached SHAP TreeExplainer over ``explainer_pipeline``.

        Building a TreeExplainer walks every tree in the forest, so it is
        constructed once per process rather than per request.
        """
        with self._lock:
            if self._shap_explainer is None:
                explainer_pipeline = self.explainer_pipeline
                if explainer_pipeline is None:
                    return None
                import shap

                classifier = explainer_pipeline.named_steps["classifier"]
                self._shap_explainer = shap.TreeExplainer(classifier)
            return self._shap_explainer

    @property
    def classes(self) -> List[str]:
        return list(self.bundle["classes"])

    @property
    def model_version(self) -> str:
        bundle = self.load()
        if bundle is None:
            return f"{settings.MODEL_VERSION}-unavailable"
        return str(bundle.get("model_version", settings.MODEL_VERSION))

    @property
    def feature_importance(self) -> Dict[str, float]:
        """Aggregated feature importance keyed by original feature name."""
        bundle = self.load()
        if bundle is None:
            return {}
        return dict(bundle.get("feature_importance", {}))

    def metadata(self) -> Dict[str, Any]:
        """Summary used by the /health and /predict endpoints."""
        bundle = self.load()
        if bundle is None:
            return {
                "model_available": False,
                "model_version": self.model_version,
                "model_path": str(self._model_path),
                "error": self._load_error,
            }
        metrics = bundle.get("metrics", {}) or {}
        return {
            "model_available": True,
            "model_version": bundle.get("model_version", settings.MODEL_VERSION),
            "model_path": str(self._model_path),
            "trained_at": bundle.get("trained_at"),
            "classes": list(bundle.get("classes", [])),
            "n_features": len(bundle.get("feature_columns", [])),
            "accuracy": metrics.get("accuracy"),
            "f1_macro": metrics.get("f1_macro"),
            "training_records": metrics.get("training_records"),
            "data_source": "synthetic",
        }

    def metrics(self) -> Dict[str, Any]:
        """Full evaluation metrics, preferring the on-disk metrics.json."""
        metrics_path = settings.metrics_file
        if metrics_path.exists():
            try:
                return json.loads(metrics_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:  # pragma: no cover
                logger.warning("metrics.json is not valid JSON: %s", metrics_path)
        bundle = self.load()
        return dict(bundle.get("metrics", {})) if bundle else {}


#: Process-wide singleton used by the services and API layers.
registry = ModelRegistry()
