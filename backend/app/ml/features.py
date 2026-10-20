"""Feature contract shared by the dataset generator, trainer and inference path.

Keeping the feature list, ordering, dtypes and human-readable metadata in one
module guarantees that training and serving never drift apart - the single most
common source of silent ML bugs in production systems.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd

from app.utils.enums import ComponentType, Material

# --------------------------------------------------------------------------
# Feature contract
# --------------------------------------------------------------------------
CATEGORICAL_FEATURES: List[str] = ["component_type", "material"]

NUMERIC_FEATURES: List[str] = [
    "component_age",
    "operating_hours",
    "load_cycles",
    "average_load",
    "vibration",
    "temperature",
    "service_count",
    "repair_count",
    "failure_history",
    "inspection_score",
    "days_since_last_service",
]

FEATURE_COLUMNS: List[str] = CATEGORICAL_FEATURES + NUMERIC_FEATURES

TARGET_COLUMN: str = "recommendation"

#: Deliberately excluded from the model input to avoid target leakage.
#: ``health_score`` is a transparent function of the same raw features and is
#: computed independently for explanation purposes only.
EXCLUDED_FROM_MODEL: List[str] = ["health_score", "latent_degradation", "component_id"]

#: Known categorical levels, pinned so that one-hot encoding is stable.
CATEGORY_LEVELS: Dict[str, List[str]] = {
    "component_type": ComponentType.values(),
    "material": Material.values(),
}

#: Defaults applied when an inbound payload omits an optional numeric field.
NUMERIC_DEFAULTS: Dict[str, float] = {
    "component_age": 0.0,
    "operating_hours": 0.0,
    "load_cycles": 0.0,
    "average_load": 0.0,
    "vibration": 0.0,
    "temperature": 25.0,
    "service_count": 0.0,
    "repair_count": 0.0,
    "failure_history": 0.0,
    "inspection_score": 100.0,
    "days_since_last_service": 0.0,
}

#: Presentation metadata used by the explainability layer and the UI.
FEATURE_METADATA: Dict[str, Dict[str, Any]] = {
    "component_type": {"label": "Component Type", "unit": "", "higher_is_worse": None},
    "material": {"label": "Material", "unit": "", "higher_is_worse": None},
    "component_age": {"label": "Component Age", "unit": "years", "higher_is_worse": True},
    "operating_hours": {"label": "Operating Hours", "unit": "h", "higher_is_worse": True},
    "load_cycles": {"label": "Load Cycles", "unit": "cycles", "higher_is_worse": True},
    "average_load": {"label": "Average Load", "unit": "kg", "higher_is_worse": True},
    "vibration": {"label": "Vibration", "unit": "mm/s RMS", "higher_is_worse": True},
    "temperature": {"label": "Operating Temperature", "unit": "C", "higher_is_worse": True},
    "service_count": {"label": "Service History", "unit": "visits", "higher_is_worse": False},
    "repair_count": {"label": "Repair Count", "unit": "repairs", "higher_is_worse": True},
    "failure_history": {"label": "Recorded Failures", "unit": "events", "higher_is_worse": True},
    "inspection_score": {"label": "Inspection Score", "unit": "/100", "higher_is_worse": False},
    "days_since_last_service": {
        "label": "Days Since Last Service",
        "unit": "days",
        "higher_is_worse": True,
    },
}

#: Type-specific reference envelopes used for degradation modelling and for
#: turning a raw reading into a human-readable severity statement.
#: PROTOTYPE VALUES - illustrative only, not KONE engineering specifications.
TYPE_REFERENCE: Dict[str, Dict[str, float]] = {
    "Motor": {"design_life_years": 25, "design_hours": 90000, "design_cycles": 1800000,
              "rated_load": 1200, "vibration_limit": 7.0, "temp_limit": 85},
    "Steel Rope": {"design_life_years": 12, "design_hours": 55000, "design_cycles": 1400000,
                   "rated_load": 1600, "vibration_limit": 5.5, "temp_limit": 60},
    "Brake": {"design_life_years": 18, "design_hours": 70000, "design_cycles": 1600000,
              "rated_load": 1400, "vibration_limit": 6.0, "temp_limit": 95},
    "Governor": {"design_life_years": 20, "design_hours": 75000, "design_cycles": 900000,
                 "rated_load": 900, "vibration_limit": 5.0, "temp_limit": 70},
    "Door Operator": {"design_life_years": 15, "design_hours": 60000, "design_cycles": 2600000,
                      "rated_load": 300, "vibration_limit": 8.0, "temp_limit": 65},
    "Sheave": {"design_life_years": 28, "design_hours": 95000, "design_cycles": 1900000,
               "rated_load": 1800, "vibration_limit": 6.5, "temp_limit": 75},
}

DEFAULT_REFERENCE: Dict[str, float] = {
    "design_life_years": 20,
    "design_hours": 80000,
    "design_cycles": 1500000,
    "rated_load": 1000,
    "vibration_limit": 6.0,
    "temp_limit": 75,
}


def reference_for(component_type: str) -> Dict[str, float]:
    """Return the design envelope for a component type (with a safe fallback)."""
    return TYPE_REFERENCE.get(str(component_type), DEFAULT_REFERENCE)


def normalise_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Coerce an arbitrary inbound dict into the exact model feature contract.

    Missing numeric values fall back to :data:`NUMERIC_DEFAULTS`; unknown keys
    are dropped. The result always contains exactly ``FEATURE_COLUMNS``.
    """
    row: Dict[str, Any] = {}
    for name in CATEGORICAL_FEATURES:
        value = payload.get(name)
        row[name] = str(value) if value is not None else "Unknown"
    for name in NUMERIC_FEATURES:
        value = payload.get(name)
        if value is None or (isinstance(value, float) and pd.isna(value)):
            value = NUMERIC_DEFAULTS[name]
        row[name] = float(value)
    return row


def build_frame(payloads: List[Dict[str, Any]]) -> pd.DataFrame:
    """Build a model-ready DataFrame with guaranteed column order and dtypes."""
    rows = [normalise_payload(payload) for payload in payloads]
    frame = pd.DataFrame(rows, columns=FEATURE_COLUMNS)
    for name in NUMERIC_FEATURES:
        frame[name] = pd.to_numeric(frame[name], errors="coerce").fillna(NUMERIC_DEFAULTS[name])
    for name in CATEGORICAL_FEATURES:
        frame[name] = frame[name].astype(str)
    return frame


def component_to_features(component: Any, overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Extract the model feature dict from a Component ORM instance.

    ``overrides`` allows a caller (for example a what-if simulation in the UI)
    to substitute individual readings without mutating the stored record.
    """
    payload = {
        "component_type": component.component_type,
        "material": component.material,
        "component_age": component.component_age,
        "operating_hours": component.operating_hours,
        "load_cycles": component.load_cycles,
        "average_load": component.average_load,
        "vibration": component.vibration,
        "temperature": component.temperature,
        "service_count": component.service_count,
        "repair_count": component.repair_count,
        "failure_history": component.failure_history,
        "inspection_score": component.inspection_score,
        "days_since_last_service": component.days_since_last_service,
    }
    if overrides:
        payload.update({k: v for k, v in overrides.items() if v is not None})
    return normalise_payload(payload)
