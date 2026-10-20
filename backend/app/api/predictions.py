"""Ad-hoc prediction endpoints and model metadata."""

from __future__ import annotations

import csv
import io
from typing import Any, Dict, List

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import current_actor, get_component_or_404
from app.core.database import get_db
from app.ml import cost_matrix, life_model, r_ladder
from app.ml.explain import global_importance_table
from app.ml.model_registry import registry
from app.models.component import Component
from app.models.prediction import Prediction
from app.schemas.prediction import ModelInfo, PredictionFeedback, PredictionRequest, PredictionResponse
from app.services import audit_service, prediction_service
from app.utils.enums import SYNTHETIC_DATA_NOTICE, AuditAction, recommendation_label

router = APIRouter(tags=["Prediction"])


@router.post(
    "/predict",
    response_model=PredictionResponse,
    summary="Assess an ad-hoc component payload",
    description=(
        "Runs the Random Forest disposition recommender on raw feature values "
        "without requiring a stored component. Returns the recommendation, "
        "confidence, transparent health score, ranked explanation factors and "
        "the safety gate result.\n\n"
        "The recommendation is advisory only and is never an authorisation to "
        "operate an elevator."
    ),
    responses={
        200: {
            "description": "Explainable, advisory end-of-use recommendation (one of the four categories)",
            "content": {
                "application/json": {
                    "example": {
                        "recommendation": "COMPONENT_RECOVERY",
                        "recommendation_label": "Component Recovery",
                        "confidence": 0.92,
                        "health_score": 78,
                        "safety_flag": False,
                        "key_factors": [
                            {
                                "factor": "Vibration",
                                "impact": "moderate",
                                "description": "Vibration level is elevated but not severe.",
                            }
                        ],
                        "model_version": "RF-v1.0-synthetic",
                    }
                }
            },
        }
    },
)
def predict(
    payload: PredictionRequest,
    top_factors: int = Query(4, ge=1, le=13, description="How many explanation factors to return"),
) -> PredictionResponse:
    result = prediction_service.assess_payload(payload.model_dump(), top_n=top_factors)
    return PredictionResponse.model_validate(result)


@router.post(
    "/predict/batch",
    response_model=List[PredictionResponse],
    summary="Assess many payloads at once",
    description="Scores up to 200 feature payloads in a single request.",
)
def predict_batch(
    payloads: List[PredictionRequest] = Body(..., max_length=200),
    top_factors: int = Query(3, ge=1, le=13),
) -> List[PredictionResponse]:
    return [
        PredictionResponse.model_validate(
            prediction_service.assess_payload(item.model_dump(), top_n=top_factors)
        )
        for item in payloads
    ]


@router.get(
    "/model/info",
    response_model=ModelInfo,
    summary="Deployed model metadata",
    description="Version, training provenance and headline evaluation metrics.",
)
def model_info() -> ModelInfo:
    return ModelInfo.model_validate(registry.metadata())


@router.get(
    "/model/metrics",
    summary="Full evaluation metrics",
    description=(
        "The complete metrics report written by the training script, including "
        "the confusion matrix and per-class precision/recall/F1."
    ),
)
def model_metrics() -> Dict[str, Any]:
    metrics = registry.metrics()
    # The safety-versus-circularity trade-off is a property of the decision
    # layer, not of the training run, so it is attached here rather than
    # written into models/metrics.json. Published so it can be challenged:
    # see app/ml/cost_matrix.py's CIRCULARITY_RATIONALE.
    metrics["safety_circularity_exchange_rate"] = cost_matrix.safety_circularity_exchange_rate()
    metrics["data_notice"] = SYNTHETIC_DATA_NOTICE
    return metrics


@router.get(
    "/model/r-ladder",
    summary="The value-retention hierarchy this platform can reach",
    description=(
        "The circular-economy R-ladder (R0-R9) and which rungs this platform "
        "reaches. The classifier predicts four dispositions; "
        "`app.ml.r_ladder` refines those into R4 repair, R6 remanufacture and "
        "R7 repurpose using explicit rules, reported **alongside** the model's "
        "own recommendation and never in place of it.\n\n"
        "R0-R2 are design-stage decisions taken before a component is "
        "installed, so this platform cannot reach them and does not claim to."
    ),
)
def model_r_ladder() -> Dict[str, Any]:
    return r_ladder.ladder_reference()


@router.get(
    "/model/feature-importance",
    summary="Global feature importance - three independent methods",
    description=(
        "Gini importance (biased toward high-cardinality features), permutation "
        "importance (the actual drop in held-out f1_macro when a feature is "
        "shuffled) and SHAP TreeExplainer, side by side so they can be compared "
        "rather than one standing in for the others."
    ),
)
def model_feature_importance() -> Dict[str, Any]:
    metrics = registry.metrics()
    return {
        "model_version": registry.model_version,
        "model_available": registry.is_available,
        "gini": global_importance_table(registry.feature_importance),
        "permutation": global_importance_table(metrics.get("permutation_importance", {})),
        "shap": global_importance_table(metrics.get("shap_importance", {})),
        "method": (
            "Three independent methods: Random Forest impurity-based (Gini) "
            "importance, permutation importance on the held-out test set, and "
            "mean |SHAP value| from one representative calibration fold."
        ),
        "data_notice": SYNTHETIC_DATA_NOTICE,
    }


@router.get(
    "/model/calibration",
    summary="Calibration reliability diagram + conformal/abstention summary",
    description=(
        "Per-class Brier score and expected-calibration-error reliability bins "
        "(mean predicted confidence vs. observed accuracy, in equal-width "
        "confidence bins) for the deployed CalibratedClassifierCV model, plus "
        "the split-conformal threshold and the resulting abstention (`DEFER_"
        "TO_INSPECTION`) statistics on the held-out test set."
    ),
)
def model_calibration() -> Dict[str, Any]:
    metrics = registry.metrics()
    return {
        "model_version": registry.model_version,
        "model_available": registry.is_available,
        "calibration_method": metrics.get("calibration_method"),
        "calibration_cv_folds": metrics.get("calibration_cv_folds"),
        "brier_score_per_class": metrics.get("brier_score_per_class", {}),
        "reliability": metrics.get("calibration", {}),
        "conformal": metrics.get("conformal", {}),
        "abstention": metrics.get("abstention", {}),
        "cost_analysis": metrics.get("cost_analysis", {}),
        "cohort_validation": metrics.get("cohort_validation", {}),
        "data_notice": SYNTHETIC_DATA_NOTICE,
    }


@router.post(
    "/model/reload",
    summary="Reload the model from disk",
    description="Picks up a freshly trained model without restarting the API.",
)
def reload_model() -> Dict[str, Any]:
    registry.reload()
    return registry.metadata()


@router.get(
    "/predictions/export",
    summary="Export predictions as CSV",
    response_class=Response,
)
def export_predictions(db: Session = Depends(get_db)) -> Response:
    rows = db.execute(
        select(Prediction)
        .options(selectinload(Prediction.component))
        .order_by(Prediction.predicted_at.desc())
    ).scalars().all()

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "prediction_id", "component_id", "component_type", "material", "material_grade",
            "health_score", "recommendation", "recommendation_label", "confidence",
            "safety_flag", "model_version", "predicted_at",
            "shadow", "technician_trust_rating", "top_factors",
        ]
    )
    for row in rows:
        factors = "; ".join(
            factor.get("factor", "") for factor in (row.key_factors or []) if isinstance(factor, dict)
        )
        writer.writerow(
            [
                row.id,
                row.component.component_id if row.component else "",
                row.component.component_type if row.component else "",
                row.component.material if row.component else "",
                life_model.grade_label(row.component) if row.component else "",
                row.health_score, row.recommendation, recommendation_label(row.recommendation),
                row.confidence, row.safety_flag,
                row.model_version, row.predicted_at.isoformat(),
                row.shadow, row.technician_trust_rating if row.technician_trust_rating else "",
                factors,
            ]
        )

    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=kone_elevate_predictions.csv"},
    )


@router.get(
    "/predictions/recent",
    summary="Most recent assessments across the fleet",
    description=(
        "Live assessments only - shadow-mode predictions (see "
        "`POST /components/{id}/predict/shadow`) are deliberately excluded, "
        "the same way they never update a component's displayed recommendation."
    ),
)
def recent_predictions(
    db: Session = Depends(get_db), limit: int = Query(10, ge=1, le=100)
) -> List[Dict[str, Any]]:
    rows = db.execute(
        select(Prediction)
        .options(selectinload(Prediction.component))
        .where(Prediction.shadow.is_(False))
        .order_by(Prediction.predicted_at.desc(), Prediction.id.desc())
        .limit(limit)
    ).scalars().all()
    return [
        {
            "id": row.id,
            "component_id": row.component.component_id if row.component else None,
            "component_type": row.component.component_type if row.component else None,
            "recommendation": row.recommendation,
            "confidence": row.confidence,
            "health_score": row.health_score,
            "safety_flag": row.safety_flag,
            "predicted_at": row.predicted_at,
        }
        for row in rows
    ]


@router.post(
    "/predictions/{prediction_id}/feedback",
    summary="Rate how much you trust one assessment (P6 pilot metric)",
    description=(
        "One-tap 1-5 rating, the 'technician trust score' pilot metric named "
        "in plan.md's P6 - the one pilot metric that cannot be derived from "
        "data already recorded elsewhere. Overwrites any previous rating on "
        "the same prediction rather than averaging - the latest rating is "
        "what a person currently thinks, not a running score."
    ),
    responses={404: {"description": "Prediction not found"}},
)
def rate_prediction(
    prediction_id: int,
    payload: PredictionFeedback,
    db: Session = Depends(get_db),
    actor: str = Depends(current_actor),
) -> Dict[str, Any]:
    prediction = db.get(Prediction, prediction_id)
    if prediction is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Prediction {prediction_id} was not found.",
        )
    prediction.technician_trust_rating = payload.trust_rating
    db.flush()
    audit_service.record(
        db,
        entity_type="prediction",
        entity_id=str(prediction.id),
        action=AuditAction.PREDICTION_FEEDBACK.value,
        data_snapshot={"trust_rating": payload.trust_rating, "notes": payload.notes},
        actor=actor,
    )
    db.commit()
    return {"prediction_id": prediction.id, "trust_rating": prediction.technician_trust_rating}


@router.post(
    "/components/{component_id}/predict/shadow",
    summary="Run a shadow assessment (P6 shadow mode)",
    description=(
        "Computes and stores an assessment WITHOUT surfacing it: the "
        "component's displayed recommendation/confidence "
        "(`latest_recommendation`/`latest_confidence`) are left untouched, "
        "and this row is excluded from `/predictions/recent`. Intended for "
        "comparing the model against a workshop outcome recorded after the "
        "fact - see `scripts/agreement_report.py` and docs/shadow-mode.md - "
        "not for technician-facing use."
    ),
)
def predict_shadow(
    component: Component = Depends(get_component_or_404),
    db: Session = Depends(get_db),
    actor: str = Depends(current_actor),
    top_factors: int = Query(4, ge=1, le=13),
) -> Dict[str, Any]:
    _, result = prediction_service.assess_component_shadow(
        db, component, actor=actor, top_n=top_factors
    )
    return {
        "component_id": component.component_id,
        "prediction_id": result["prediction_id"],
        "recommendation": result["recommendation"],
        "confidence": result["confidence"],
        "shadow": True,
        "note": "Not surfaced to technicians - see the endpoint description.",
    }
