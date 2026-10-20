"""Inference: score a component and apply the mandatory safety gate.

Pipeline
--------
    payload -> feature contract -> cached calibrated pipeline -> class
            probabilities -> transparent health score -> explainability
            factors (blended + SHAP) -> ABSTENTION RULE -> DECISION FLOW
            -> SAFETY GATE -> advisory recommendation

Decision flow
-------------
The classifier's probabilities are not reported as the category directly.
``app.ml.decision_flow`` runs the four gates in order - still suitable for
the current application (Continue Using - No Changes Required), else usable
sub-components (Component Recovery), else useful material (Material
Recovery), else Dispose - on the probabilities, the inspection result, the
component type's separable sub-components and its material / recorded grade.
The model's own argmax is kept as ``underlying_recommendation``.

Safety gate
-----------
Safety-critical component types (steel rope, brake, governor) can never be
released on an AI recommendation alone. The gate does not change the model
output - it attaches a mandatory human-inspection requirement that the API and
the UI must surface verbatim.

Abstention
----------
Independently of the safety gate, ``app.ml.abstention`` can turn the reported
``recommendation`` into ``DEFER_TO_INSPECTION`` when the calibrated top-class
confidence is low or the conformal prediction set is ambiguous. The model's
own best guess is preserved as ``underlying_recommendation`` either way.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from app.core.metrics import record_prediction
from app.ml import abstention, cost_matrix, decision_flow, r_ladder
from app.ml.explain import build_factors, explanation_notice, shap_factors
from app.ml.features import build_frame, normalise_payload
from app.ml.model_registry import registry
from app.services.health_service import compute_health
from app.utils.enums import (
    RECOMMENDATION_DESCRIPTIONS,
    RECOMMENDATION_DISCLAIMER,
    SAFETY_GATE_MESSAGE,
    SYNTHETIC_DATA_NOTICE,
    Recommendation,
    is_safety_critical,
    recommendation_label,
)

#: Health-score cut-offs used only when no trained model is available.
HEURISTIC_BANDS = [
    (78.0, Recommendation.CONTINUE_USING.value),
    (58.0, Recommendation.COMPONENT_RECOVERY.value),
    (34.0, Recommendation.MATERIAL_RECOVERY.value),
]


def _heuristic_recommendation(health: float) -> str:
    """Deterministic fallback disposition derived from the health score."""
    for threshold, label in HEURISTIC_BANDS:
        if health >= threshold:
            return label
    return Recommendation.DISPOSE.value


def _apply_safety_gate(component_type: str, result: Dict[str, Any]) -> Dict[str, Any]:
    """Attach the mandatory human-inspection requirement where applicable."""
    critical = is_safety_critical(component_type)
    result["safety_flag"] = critical
    result["safety_message"] = SAFETY_GATE_MESSAGE if critical else None
    result["safety_note"] = (
        (
            f"AI recommendation: {recommendation_label(result['recommendation'])}. "
            "Human inspection required before any continued-use or recovery decision. "
            "This component "
            "type is safety-critical and cannot be released on an AI "
            "recommendation alone."
        )
        if critical
        else "No mandatory safety flag for this component type."
    )
    result["disclaimer"] = RECOMMENDATION_DISCLAIMER
    return result


def predict_disposition(
    payload: Dict[str, Any],
    top_n: int = 4,
    importance: Optional[Dict[str, float]] = None,
    grade: Optional[str] = None,
) -> Dict[str, Any]:
    """Score one component and return the full, explainable assessment.

    ``grade`` is the component's *recorded* material grade, if any. It is
    not a model feature (``normalise_payload`` drops it), but the decision
    flow uses it to name recoverable sub-components and to judge material
    recoverability. Without it the wording stays generic.

    The function never raises when the model is missing: it degrades to the
    transparent health-score heuristic and reports ``model_available = False``
    so the client can show an honest banner.
    """
    started = time.perf_counter()
    features = normalise_payload(payload)
    health = compute_health(features)
    component_type = features["component_type"]

    probabilities: Dict[str, float] = {}
    model_available = registry.is_available
    abstention_decision: Optional[Dict[str, Any]] = None
    cost_decision: Optional[Dict[str, Any]] = None
    shap_result: Optional[List[Dict[str, Any]]] = None

    if model_available:
        bundle = registry.bundle
        pipeline = bundle["pipeline"]
        frame = build_frame([features])
        proba_row = pipeline.predict_proba(frame)[0]
        classes: List[str] = [str(label) for label in bundle["classes"]]
        probabilities = {
            label: round(float(score), 4) for label, score in zip(classes, proba_row, strict=True)
        }
        best_index = int(proba_row.argmax())
        underlying_recommendation = classes[best_index]
        confidence = round(float(proba_row[best_index]), 4)
        model_version = str(bundle.get("model_version"))
        importance = importance if importance is not None else registry.feature_importance

        abstention_decision = abstention.decide(probabilities, registry.conformal_q_hat)
        cost_decision = cost_matrix.best_decision(probabilities, component_type)
        shap_result = shap_factors(
            features,
            registry.explainer_pipeline,
            registry.shap_explainer,
            underlying_recommendation,
            top_n=top_n,
        )
    else:
        underlying_recommendation = _heuristic_recommendation(health["health_score"])
        confidence = 0.5
        probabilities = {underlying_recommendation: 0.5}
        model_version = f"{registry.model_version} (heuristic fallback)"
        importance = importance or {}

    flow = decision_flow.decide(
        probabilities,
        component_type,
        features["material"],
        inspection_score=features.get("inspection_score"),
        grade=grade,
    )
    abstained = bool(abstention_decision["abstain"]) if abstention_decision else False
    recommendation = Recommendation.DEFER_TO_INSPECTION.value if abstained else flow["recommendation"]

    result: Dict[str, Any] = {
        "recommendation": recommendation,
        "recommendation_label": recommendation_label(recommendation),
        "recommendation_text": (
            RECOMMENDATION_DESCRIPTIONS[recommendation] if abstained else flow["text"]
        ),
        "decision_flow": {
            "recommendation": flow["recommendation"],
            "label": flow["label"],
            "steps": flow["steps"],
            "subcomponents": flow["subcomponents"],
            "material": flow["material"],
            "applied": not abstained,
        },
        "underlying_recommendation": underlying_recommendation,
        "confidence": confidence,
        "abstained": abstained,
        "prediction_set": abstention_decision["prediction_set"] if abstention_decision else None,
        "health_score": health["health_score"],
        "health_band": health["band"],
        "degradation_index": health["degradation_index"],
        "probabilities": probabilities,
        "key_factors": build_factors(features, importance=importance, top_n=top_n),
        "shap_factors": shap_result,
        "cost_analysis": cost_decision,
        "circular_strategy": r_ladder.refine(
            recommendation,
            features,
            health["health_score"],
            abstained=abstained,
        ),
        "model_version": model_version,
        "model_available": model_available,
        "health_breakdown": health["breakdown"],
        "health_methodology": health["methodology"],
        "explanation_method": explanation_notice(),
        "data_notice": SYNTHETIC_DATA_NOTICE,
        "input_snapshot": features,
    }
    result = _apply_safety_gate(component_type, result)
    record_prediction(
        recommendation=result["recommendation"],
        abstained=result["abstained"],
        duration_seconds=time.perf_counter() - started,
    )
    return result


def predict_batch(payloads: List[Dict[str, Any]], top_n: int = 4) -> List[Dict[str, Any]]:
    """Score many components, loading the model importance only once."""
    importance = registry.feature_importance if registry.is_available else {}
    return [predict_disposition(payload, top_n=top_n, importance=importance) for payload in payloads]
