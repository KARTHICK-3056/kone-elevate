"""Calibrate the life model's nominal operating conditions from fleet data.

A design life is quoted for *typical* operation: the load a lift of that
type usually carries and the maintenance it usually gets. The life model
scales life up or down relative to that nominal point, so if the nominal
point is wrong every component is aged wrongly in the same direction.

It was wrong. The model assumed design life at 60% of rated load and a
service every 180 days, while components in the training data typically run
at about 67% of rated load and are serviced every ~260 days. Every component
therefore carried a load penalty and a maintenance penalty it had not
earned, and predicted (effective) age ran ~20-40% ahead of calendar age
across the board.

This module fits the nominal point from data instead - the median load
utilisation and median service interval per component type in the training
set - and stores it in ``models/life_calibration.json``. The life model reads
it; without the file it falls back to the documented defaults.

The same applies to the inspection score. The life model converted a score
to life consumed assuming a new part scores 100 and a worn-out one 35; in the
data new parts score about 89 (inspectors grade conservatively and some wear
is present from installation), so every inspection over-aged young parts.
The conversion is fitted too: a robust line of inspection score against the
usage model's life-consumed estimate, pooled across types.

It is fitted on ``train.csv`` and evaluated on ``test.csv`` so the reported
improvement is not measured on the data it was fitted to. On real fleet data
the same fit gives the real fleet's nominal duty.
"""

from __future__ import annotations

import json
import statistics
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd

from app.core.config import settings
from app.ml.features import reference_for

CALIBRATION_FILE = "life_calibration.json"

#: Fewer rows than this per type and the type keeps the default.
MIN_ROWS = 50


def calibration_path() -> Path:
    return Path(settings.model_file).parent / CALIBRATION_FILE


def fit(frame: pd.DataFrame, source: str = "training data") -> Dict[str, Any]:
    """Median utilisation and service interval per component type."""
    types: Dict[str, Dict[str, Any]] = {}
    for component_type, group in frame.groupby("component_type"):
        group = group[group["component_age"] >= 1.0]
        if len(group) < MIN_ROWS:
            continue
        rated = float(reference_for(component_type)["rated_load"])
        utilisation = (group["average_load"] / rated).tolist()
        serviced = group[group["service_count"] > 0]
        intervals = (serviced["component_age"] * 365.25 / serviced["service_count"]).tolist()
        types[str(component_type)] = {
            "reference_utilisation": round(statistics.median(utilisation), 4),
            "service_interval_days": round(statistics.median(intervals), 1) if intervals else None,
            "rows": int(len(group)),
        }
    calibration = {
        "source": source,
        "method": (
            "Median load utilisation and median service interval per component type; "
            "inspection score vs usage-model life consumed fitted by least squares."
        ),
        "types": types,
    }
    calibration["inspection"] = _fit_inspection(frame, calibration)
    return calibration


def _fit_inspection(frame: pd.DataFrame, calibration: Dict[str, Any]) -> Optional[Dict[str, float]]:
    """score = intercept - slope x D, fitted against the usage model's D.

    Uses the utilisation/interval just fitted (so the usage model is itself
    calibrated when D is computed), and the middle of the life range where
    both estimates are informative.
    """
    from datetime import date, timedelta

    import numpy as np

    from app.ml import life_model

    previous = load.__wrapped__  # the uncached loader
    today = date(2026, 1, 1)
    xs, ys = [], []
    load.cache_clear()
    _override["value"] = calibration
    try:
        sample = frame[frame["component_type"].isin(life_model.FOCUS_TYPES)]
        sample = sample.sample(min(len(sample), 3000), random_state=0) if len(sample) > 3000 else sample
        for _, row in sample.iterrows():
            record = row.to_dict()
            if record["component_age"] < 1.0:
                continue
            record["installation_date"] = today - timedelta(days=round(record["component_age"] * 365.25))
            record["material_grade"] = None
            assessment = life_model.assess(record, today=today)
            usage = assessment["life_consumed"]["usage_model"]
            if 0.1 <= usage <= 1.0:
                xs.append(usage)
                ys.append(float(record["inspection_score"]))
    finally:
        _override["value"] = None
        load.cache_clear()
    del previous
    if len(xs) < 100:
        return None
    x, y = np.array(xs), np.array(ys)
    slope, intercept = np.polyfit(x, y, 1)
    if slope >= 0:  # a score that does not fall with wear is not usable
        return None
    residual_sd = float(np.std(y - (slope * x + intercept), ddof=2))
    return {
        "intercept": round(float(intercept), 2),
        "slope": round(float(-slope), 2),
        # Grading scatter, in life-consumed units: how far one inspection can
        # sit from the usage estimate by noise alone.
        "scatter": round(residual_sd / float(-slope), 4),
        "rows": len(xs),
    }


def save(calibration: Dict[str, Any], path: Optional[Path] = None) -> Path:
    path = path or calibration_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(calibration, indent=2), encoding="utf-8")
    load.cache_clear()
    return path


#: Lets ``fit`` evaluate the life model under a calibration not yet saved.
_override: Dict[str, Optional[Dict[str, Any]]] = {"value": None}


@lru_cache(maxsize=1)
def load() -> Dict[str, Any]:
    """The stored calibration, or an empty one if none has been fitted."""
    if _override["value"] is not None:
        return _override["value"]
    path = calibration_path()
    if not path.exists():
        return {"types": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):  # pragma: no cover - corrupt file falls back to defaults
        return {"types": {}}


def for_type(component_type: str) -> Dict[str, Any]:
    return load().get("types", {}).get(str(component_type), {})


def inspection_mapping() -> Optional[Dict[str, float]]:
    """Fitted (intercept, slope) of inspection score vs life consumed, if any."""
    return load().get("inspection")
