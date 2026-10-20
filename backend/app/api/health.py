"""Service health, readiness and platform metadata endpoints."""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.ml import life_model
from app.ml.model_registry import registry
from app.models.audit import AuditLog
from app.models.component import Component
from app.utils.enums import (
    RECOMMENDATION_DISCLAIMER,
    SAFETY_CRITICAL_TYPES,
    SAFETY_GATE_MESSAGE,
    SYNTHETIC_DATA_NOTICE,
    ComponentType,
    LifecycleStatus,
    Material,
    Recommendation,
    ServiceEventType,
)
from app.utils.helpers import utcnow

router = APIRouter(tags=["Health"])


@router.get(
    "/health",
    summary="Service health check",
    description=(
        "Reports API, database and ML model availability. Used by Docker "
        "healthchecks and by the frontend to show an honest offline banner."
    ),
)
def health(db: Session = Depends(get_db)) -> Dict[str, Any]:
    database_ok = True
    database_error = None
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - only on a real outage
        database_ok = False
        database_error = str(exc)[:200]

    model_meta = registry.metadata()
    status_value = "ok" if database_ok and model_meta["model_available"] else "degraded"

    return {
        "status": status_value,
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "timestamp": utcnow().isoformat(),
        "database": {
            "connected": database_ok,
            "dialect": settings.DATABASE_URL.split(":")[0],
            "error": database_error,
        },
        "model": model_meta,
        "data_notice": SYNTHETIC_DATA_NOTICE,
    }


@router.get(
    "/health/ready",
    summary="Readiness probe",
    description="Returns 200 only when the database responds and tables exist.",
)
def ready(db: Session = Depends(get_db)) -> Dict[str, Any]:
    components = db.execute(select(Component.id).limit(1)).first()
    audit = db.execute(select(AuditLog.id).limit(1)).first()
    return {
        "ready": True,
        "has_components": components is not None,
        "has_audit_records": audit is not None,
        "model_available": registry.is_available,
    }


@router.get(
    "/meta/enums",
    tags=["Metadata"],
    summary="Domain enumerations",
    description="Every controlled vocabulary the UI needs, in one request.",
)
def enums() -> Dict[str, Any]:
    return {
        "component_types": ComponentType.values(),
        "materials": Material.values(),
        "recommendations": Recommendation.values(),
        "lifecycle_statuses": LifecycleStatus.values(),
        "service_event_types": ServiceEventType.values(),
        # The grade catalogue, per type, for recording a grade from the
        # nameplate or bill of materials. Never used to assume one.
        "material_grades": {
            component_type: [
                {
                    "grade": key,
                    "label": grade["label"],
                    "designation": grade["designation"],
                    "grading_system": grade["grading_system"],
                    "materials": grade["materials"],
                }
                for key, grade in grades.items()
            ]
            for component_type, grades in life_model.MATERIAL_GRADES.items()
        },
        "safety_critical_types": sorted(SAFETY_CRITICAL_TYPES),
        "safety_gate_message": SAFETY_GATE_MESSAGE,
        "recommendation_disclaimer": RECOMMENDATION_DISCLAIMER,
        "data_notice": SYNTHETIC_DATA_NOTICE,
    }
