"""Explainability layer for the disposition recommender.

Two independent explanation methods
------------------------------------
1. **Blended factors** (``build_factors``): global Random Forest feature
   importance combined with *local* deviation analysis - how far each reading
   sits from the documented design envelope for that component type. Fast,
   always available (even without a trained model), and readable by a
   technician without any ML background.
2. **SHAP TreeExplainer** (``shap_factors``): genuine per-prediction Shapley
   value attribution for the predicted class, computed from one
   representative fold of the calibrated 5-fold ensemble (see
   ``app.ml.train.shap_importance_table`` for why one fold, not all five).
   This is a real, additive, game-theoretically-grounded local explanation -
   a materially different and complementary signal to (1), not a replacement.

Both are surfaced side by side and clearly labelled; neither is presented as
the other.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd

from app.ml.features import FEATURE_METADATA, normalise_payload, reference_for
from app.services.health_service import FACTOR_WEIGHTS, _factor_ratios
from app.utils.enums import ImpactLevel

#: Severity thresholds applied to a normalised deviation ratio.
SEVERITY_BANDS = [
    (1.0, ImpactLevel.CRITICAL.value),
    (0.80, ImpactLevel.HIGH.value),
    (0.55, ImpactLevel.MODERATE.value),
    (0.30, ImpactLevel.LOW.value),
]

DEFAULT_TOP_N = 4


def _severity(ratio: float) -> str:
    """Map a deviation ratio to a qualitative impact level."""
    for threshold, level in SEVERITY_BANDS:
        if ratio >= threshold:
            return level
    return ImpactLevel.POSITIVE.value


def _describe(name: str, value: float, ratio: float, component_type: str) -> str:
    """Produce a plain-language sentence for one factor."""
    ref = reference_for(component_type)
    level = _severity(ratio)
    percent = int(round(ratio * 100))

    if name == "component_age":
        limit = ref["design_life_years"]
        if level == ImpactLevel.POSITIVE.value:
            return f"Age of {value:.1f} years is well within the {limit:.0f}-year design life."
        return f"Age of {value:.1f} years is {percent}% of the {limit:.0f}-year design life."

    if name == "operating_hours":
        limit = ref["design_hours"]
        if level == ImpactLevel.POSITIVE.value:
            return f"{value:,.0f} operating hours - light lifecycle usage against a {limit:,.0f}h envelope."
        return f"{value:,.0f} operating hours is {percent}% of the {limit:,.0f}h design envelope."

    if name == "load_cycles":
        limit = ref["design_cycles"]
        return f"{value:,.0f} load cycles is {percent}% of the {limit:,.0f}-cycle design envelope."

    if name == "average_load":
        limit = ref["rated_load"]
        return f"Average load of {value:,.0f} kg is {percent}% of the {limit:,.0f} kg rated load."

    if name == "vibration":
        limit = ref["vibration_limit"]
        if level in (ImpactLevel.CRITICAL.value, ImpactLevel.HIGH.value):
            return (
                f"Vibration of {value:.2f} mm/s exceeds or approaches the "
                f"{limit:.1f} mm/s reference limit - a strong wear indicator."
            )
        if level == ImpactLevel.MODERATE.value:
            return f"Vibration of {value:.2f} mm/s is elevated but not severe (limit {limit:.1f} mm/s)."
        if level == ImpactLevel.LOW.value:
            return f"Vibration of {value:.2f} mm/s sits in the normal band (limit {limit:.1f} mm/s)."
        return f"Vibration of {value:.2f} mm/s is well below the {limit:.1f} mm/s reference limit."

    if name == "temperature":
        limit = ref["temp_limit"]
        if level == ImpactLevel.POSITIVE.value:
            return f"Operating temperature of {value:.0f} C sits comfortably below the {limit:.0f} C limit."
        return f"Operating temperature of {value:.0f} C is approaching the {limit:.0f} C limit."

    if name == "inspection_score":
        if value >= 80:
            return f"Last inspection scored {value:.0f}/100 - condition assessed as good."
        if value >= 60:
            return f"Last inspection scored {value:.0f}/100 - moderate defects recorded."
        return f"Last inspection scored {value:.0f}/100 - poor assessed condition."

    if name == "repair_count":
        if value == 0:
            return "No repairs recorded against this component."
        if value <= 2:
            return f"{value:.0f} recorded repair(s) - limited intervention history."
        return f"{value:.0f} recorded repairs indicate repeated corrective intervention."

    if name == "failure_history":
        if value == 0:
            return "No in-service failures recorded."
        return f"{value:.0f} recorded in-service failure event(s) increase residual risk."

    if name == "days_since_last_service":
        if value <= 200:
            return f"Serviced {value:.0f} days ago - maintenance is current."
        return f"{value:.0f} days since the last service visit - maintenance interval exceeded."

    if name == "service_count":
        return f"{value:.0f} preventive-maintenance visits recorded."

    return f"{FEATURE_METADATA.get(name, {}).get('label', name)}: {value}"


def build_factors(
    payload: Dict[str, Any],
    importance: Optional[Dict[str, float]] = None,
    top_n: int = DEFAULT_TOP_N,
) -> List[Dict[str, Any]]:
    """Rank and describe the factors driving a recommendation.

    The ranking score blends the model-wide importance of a feature with how
    far this particular component deviates from its design envelope, so a
    high-importance feature that happens to be perfectly healthy does not crowd
    out a mid-importance feature that is clearly out of bounds.
    """
    features = normalise_payload(payload)
    ratios = _factor_ratios(features)
    importance = importance or {}
    component_type = features["component_type"]

    scored: List[Dict[str, Any]] = []
    for name, ratio in ratios.items():
        clamped = max(0.0, min(ratio, 1.6))
        model_importance = float(importance.get(name, FACTOR_WEIGHTS.get(name, 0.05)))
        # Blend: how far out of envelope this component is, weighted against
        # how much the trained model actually relies on that feature.
        rank_score = (0.55 * min(clamped, 1.25) / 1.25) + (0.45 * model_importance)

        raw_value = features[name]
        scored.append(
            {
                "factor": FEATURE_METADATA.get(name, {}).get("label", name),
                "feature": name,
                "impact": _severity(clamped),
                "description": _describe(name, raw_value, clamped, component_type),
                "value": round(raw_value, 3),
                "unit": FEATURE_METADATA.get(name, {}).get("unit", ""),
                "deviation_ratio": round(ratio, 3),
                "model_importance": round(model_importance, 4),
                "rank_score": round(rank_score, 4),
            }
        )

    scored.sort(key=lambda item: item["rank_score"], reverse=True)
    return scored[: max(top_n, 1)]


def global_importance_table(importance: Dict[str, float]) -> List[Dict[str, Any]]:
    """Format the global feature-importance dict for the analytics UI."""
    return [
        {
            "feature": name,
            "label": FEATURE_METADATA.get(name, {}).get("label", name),
            "importance": round(float(value), 6),
        }
        for name, value in sorted(importance.items(), key=lambda item: item[1], reverse=True)
    ]


def explanation_notice() -> str:
    """Disclosure string shown wherever explanations are surfaced."""
    return (
        "key_factors blends Random Forest feature importance with deviation from "
        "documented design envelopes. shap_factors is a second, independent method: "
        "genuine per-prediction SHAP (Shapley value) attribution from one "
        "representative fold of the calibrated model."
    )


def shap_factors(
    payload: Dict[str, Any],
    explainer_pipeline: Any,
    shap_explainer: Any,
    predicted_class: str,
    top_n: int = DEFAULT_TOP_N,
) -> Optional[List[Dict[str, Any]]]:
    """Per-prediction SHAP attribution for the predicted class.

    Returns ``None`` when no trained model/explainer is available - callers
    should treat that as "not computed for this request", not as an empty
    result.
    """
    if explainer_pipeline is None or shap_explainer is None:
        return None

    features = normalise_payload(payload)
    preprocessor = explainer_pipeline.named_steps["preprocessor"]
    classifier = explainer_pipeline.named_steps["classifier"]

    frame = pd.DataFrame([features])
    transformed = preprocessor.transform(frame)
    encoded_names = list(preprocessor.get_feature_names_out())

    classes = list(classifier.classes_)
    if predicted_class not in classes:
        return None
    class_index = classes.index(predicted_class)

    shap_values = shap_explainer.shap_values(transformed)  # (1, n_encoded_features, n_classes)
    row_values = shap_values[0, :, class_index]

    aggregated: Dict[str, float] = {}
    for encoded_name, value in zip(encoded_names, row_values, strict=True):
        target = None
        for original in FEATURE_METADATA:
            if encoded_name == original or encoded_name.startswith(f"{original}_"):
                target = original
                break
        if target is None:
            continue
        aggregated[target] = aggregated.get(target, 0.0) + float(value)

    def _direction(value: float) -> str:
        if value > 0:
            return "increases_risk"
        if value < 0:
            return "decreases_risk"
        return "neutral"

    def _raw_value(name: str) -> Any:
        raw = features.get(name)
        return round(float(raw), 3) if isinstance(raw, (int, float)) else raw

    ranked = sorted(aggregated.items(), key=lambda item: abs(item[1]), reverse=True)[: max(top_n, 1)]
    return [
        {
            "factor": FEATURE_METADATA.get(name, {}).get("label", name),
            "feature": name,
            "shap_value": round(value, 4),
            "direction": _direction(value),
            "value": _raw_value(name),
            "unit": FEATURE_METADATA.get(name, {}).get("unit", ""),
        }
        for name, value in ranked
    ]
