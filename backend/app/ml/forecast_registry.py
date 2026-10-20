"""In-process registry for the end-of-life forecaster.

Mirrors ``app.ml.model_registry`` - lazy, thread-safe, cached for the life of
the process, and degrading gracefully when the artefact is absent so a fresh
clone that has not run ``scripts/train_forecast.py`` still serves the rest of
the API instead of failing at import.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

import joblib

from app.core.config import settings
from app.core.logging_config import get_logger

logger = get_logger(__name__)


class ForecastRegistry:
    """Thread-safe lazy loader for the serialised Weibull AFT bundle."""

    def __init__(self, model_path: Optional[Path] = None) -> None:
        self._model_path = Path(model_path) if model_path else settings.forecast_model_file
        self._bundle: Optional[Dict[str, Any]] = None
        self._lock = threading.Lock()
        self._load_error: Optional[str] = None

    def load(self, force: bool = False) -> Optional[Dict[str, Any]]:
        if self._bundle is not None and not force:
            return self._bundle
        with self._lock:
            if self._bundle is not None and not force:
                return self._bundle
            if not self._model_path.exists():
                self._load_error = f"Forecast model not found at {self._model_path}"
                logger.warning("%s - forecast endpoints will report unavailable.", self._load_error)
                return None
            try:
                bundle = joblib.load(self._model_path)
            except Exception as exc:  # pragma: no cover - corrupted artefact
                self._load_error = f"Failed to load forecast model: {exc}"
                logger.exception("Could not load forecast bundle")
                return None
            self._bundle = bundle
            self._load_error = None
            logger.info(
                "Loaded forecast model %s (trained %s)",
                bundle.get("model_version"),
                bundle.get("trained_at"),
            )
            return self._bundle

    def reload(self) -> Optional[Dict[str, Any]]:
        self._bundle = None
        return self.load(force=True)

    @property
    def is_available(self) -> bool:
        return self.load() is not None

    @property
    def model(self):
        bundle = self.load()
        return None if bundle is None else bundle.get("model")

    @property
    def preprocessor(self):
        bundle = self.load()
        return None if bundle is None else bundle.get("preprocessor")

    @property
    def model_version(self) -> str:
        bundle = self.load()
        if bundle is None:
            return f"{settings.FORECAST_MODEL_VERSION}-unavailable"
        return str(bundle.get("model_version", settings.FORECAST_MODEL_VERSION))

    @property
    def horizons_months(self) -> List[int]:
        bundle = self.load()
        return list(bundle.get("horizons_months", [3, 6, 12, 24])) if bundle else [3, 6, 12, 24]

    def metadata(self) -> Dict[str, Any]:
        bundle = self.load()
        if bundle is None:
            return {
                "forecast_available": False,
                "model_version": self.model_version,
                "model_path": str(self._model_path),
                "error": self._load_error,
                "hint": "Run: python scripts/train_forecast.py",
            }
        metrics = bundle.get("metrics", {}) or {}
        backtest = metrics.get("backtest", {}) or {}
        return {
            "forecast_available": True,
            "model": bundle.get("metrics", {}).get("model", "WeibullAFT"),
            "model_version": bundle.get("model_version"),
            "model_path": str(self._model_path),
            "trained_at": bundle.get("trained_at"),
            "horizons_months": self.horizons_months,
            "training_records": metrics.get("training_records"),
            "censoring_rate": metrics.get("censoring_rate"),
            "shape_k": (metrics.get("fit", {}) or {}).get("shape_k"),
            "mape_overall": backtest.get("mape_overall"),
            "data_source": "synthetic",
        }

    def metrics(self) -> Dict[str, Any]:
        """Full metrics, preferring the on-disk forecast_metrics.json."""
        path = settings.forecast_metrics_file
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:  # pragma: no cover
                logger.warning("forecast_metrics.json is not valid JSON: %s", path)
        bundle = self.load()
        return dict(bundle.get("metrics", {})) if bundle else {}


#: Process-wide singleton used by the forecast service and API.
forecast_registry = ForecastRegistry()
