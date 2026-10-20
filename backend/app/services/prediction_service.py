"""Orchestration around the ML inference path.

Responsibilities kept here (and out of the API layer):

* turn a Component ORM row into the model feature contract,
* run inference and the safety gate,
* persist an immutable Prediction row,
* refresh the cached health score on the component,
* append the corresponding audit-chain entry.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ml import early_warning
from app.ml.features import component_to_features
from app.ml.predict import predict_disposition
from app.models.component import Component
from app.models.prediction import Prediction
from app.services import audit_service, early_warning_service, impact_service
from app.utils.enums import AuditAction


def assess_payload(payload: Dict[str, Any], top_n: int = 4) -> Dict[str, Any]:
    """Score a raw feature payload without touching the database."""
    result = predict_disposition(payload, top_n=top_n, grade=payload.get("material_grade"))
    result["impact"] = impact_service.component_impact(
        payload.get("component_type"), payload.get("material"), result["recommendation"]
    )
    return result


def assess_component(
    db: Session,
    component: Component,
    actor: str = "system",
    overrides: Optional[Dict[str, Any]] = None,
    top_n: int = 4,
    persist: bool = True,
    commit: bool = True,
    shadow: bool = False,
) -> Tuple[Optional[Prediction], Dict[str, Any]]:
    """Run an AI assessment for a stored component.

    Returns the persisted :class:`Prediction` (or ``None`` when
    ``persist=False``) together with the full explainable result dictionary.

    ``shadow=True`` (P6) computes and stores the assessment exactly as
    normal, EXCEPT it never touches ``component.health_score`` /
    ``latest_recommendation`` / ``latest_confidence`` - the cached columns
    the dashboard, passport and component list actually display (see
    ``app.models.component.Component``). That omission is the entire
    mechanism by which a shadow assessment stays invisible to a technician:
    there is no separate "is this component in shadow mode" flag to check
    everywhere else in the codebase, because nothing else ever reads a
    shadow prediction's values by default (``predictions/recent`` and the
    component's own prediction-history endpoint both still show it, tagged
    ``shadow: true``, for anyone deliberately looking).
    """
    features = component_to_features(component, overrides=overrides)
    result = predict_disposition(features, top_n=top_n, grade=component.material_grade)
    result["impact"] = impact_service.component_impact(
        component.component_type, component.material, result["recommendation"]
    )
    result["component_id"] = component.component_id
    # Pre-analysis alongside the snapshot verdict: which issue is coming, when,
    # and why we think so. Only for stored components - it needs history.
    result["early_warning"] = early_warning_service.for_component(
        component, latest_recommendation=result["recommendation"]
    )

    if not persist:
        return None, result

    prediction = Prediction(
        component_id=component.id,
        health_score=result["health_score"],
        recommendation=result["recommendation"],
        underlying_recommendation=result.get("underlying_recommendation"),
        abstained=bool(result.get("abstained", False)),
        confidence=result["confidence"],
        model_version=result["model_version"],
        key_factors=result["key_factors"],
        input_snapshot=result["input_snapshot"],
        probabilities=result["probabilities"],
        safety_flag=result["safety_flag"],
        safety_message=result["safety_message"],
        shadow=shadow,
        life_cycle_number=component.life_cycle_number,
    )
    db.add(prediction)

    if not shadow:
        # Cache the latest health score and recommendation on the component
        # for fast list/dashboard queries - see Component.latest_recommendation.
        component.health_score = result["health_score"]
        component.latest_recommendation = result["recommendation"]
        component.latest_confidence = result["confidence"]
    db.flush()

    audit_service.record(
        db,
        entity_type="component",
        entity_id=component.component_id,
        action=AuditAction.PREDICT.value,
        data_snapshot={
            "prediction_id": prediction.id,
            "recommendation": result["recommendation"],
            "underlying_recommendation": result.get("underlying_recommendation"),
            "abstained": result.get("abstained", False),
            "confidence": result["confidence"],
            "health_score": result["health_score"],
            "safety_flag": result["safety_flag"],
            "model_version": result["model_version"],
            "model_available": result["model_available"],
            "key_factors": [factor["factor"] for factor in result["key_factors"]],
            # Tamper-evident proof of what was predicted *before* it happened.
            "predicted_issues": early_warning.audit_summary(result["early_warning"]),
            "shadow": shadow,
        },
        actor=actor,
    )

    if commit:
        db.commit()
        db.refresh(prediction)

    result["prediction_id"] = prediction.id
    result["predicted_at"] = prediction.predicted_at
    return prediction, result


def assess_component_shadow(
    db: Session,
    component: Component,
    actor: str = "system",
    top_n: int = 4,
) -> Tuple[Optional[Prediction], Dict[str, Any]]:
    """Convenience wrapper: :func:`assess_component` with ``shadow=True``."""
    return assess_component(db, component, actor=actor, top_n=top_n, shadow=True)


def history(db: Session, component: Component, limit: int = 50) -> List[Prediction]:
    """Return the assessment history for a component, newest first."""
    statement = (
        select(Prediction)
        .where(Prediction.component_id == component.id)
        .order_by(Prediction.predicted_at.desc(), Prediction.id.desc())
        .limit(limit)
    )
    return list(db.execute(statement).scalars().all())


def latest(db: Session, component: Component) -> Optional[Prediction]:
    """Most recent assessment for a component, if one exists."""
    statement = (
        select(Prediction)
        .where(Prediction.component_id == component.id)
        .order_by(Prediction.predicted_at.desc(), Prediction.id.desc())
        .limit(1)
    )
    return db.execute(statement).scalars().first()
