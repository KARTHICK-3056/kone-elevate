"""Digital Component Passport: the QR-addressable lifecycle record."""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.components import component_to_read
from app.api.deps import get_component_public_or_404
from app.core.database import get_db
from app.api.simulation import scenario_view
from app.ml import life_model
from app.models.component import Component
from app.models.prediction import Prediction
from app.models.service_event import ServiceEvent
from app.schemas.component import ComponentPassport, QRInfo
from app.services import (
    audit_service,
    dpp_service,
    early_warning_service,
    impact_service,
    qr_service,
    quality_certificate_service,
)
from app.utils import standards
from app.utils.enums import (
    RECOMMENDATION_DISCLAIMER,
    SAFETY_GATE_MESSAGE,
    SYNTHETIC_DATA_NOTICE,
    is_safety_critical,
    recommendation_label,
)
from app.utils.helpers import utcnow

router = APIRouter(prefix="/passports", tags=["Passport"])


@router.get(
    "/{component_id}",
    response_model=ComponentPassport,
    summary="Get a component passport",
    description=(
        "The complete digital passport: identity, operating history, service "
        "history, AI assessment history, audit trail, prototype impact "
        "estimate and the QR code. Resolvable by component id, serial number "
        "or QR token so a scanned label always works."
    ),
    responses={404: {"description": "Component not found"}},
)
def get_passport(
    component: Component = Depends(get_component_public_or_404),
    db: Session = Depends(get_db),
    events_limit: int = Query(50, ge=1, le=200),
    audit_limit: int = Query(50, ge=1, le=200),
) -> ComponentPassport:
    events = db.execute(
        select(ServiceEvent)
        .where(ServiceEvent.component_id == component.id)
        .order_by(ServiceEvent.event_date.desc(), ServiceEvent.id.desc())
        .limit(events_limit)
    ).scalars().all()

    predictions = db.execute(
        select(Prediction)
        .where(Prediction.component_id == component.id)
        .order_by(Prediction.predicted_at.desc(), Prediction.id.desc())
        .limit(20)
    ).scalars().all()

    audit_entries = audit_service.list_for_entity(
        db, "component", component.component_id, limit=audit_limit
    )

    latest = predictions[0] if predictions else None
    safety_flag = is_safety_critical(component.component_type)
    life_assessment = _life_assessment(component, component.latest_prediction)

    return ComponentPassport(
        component=component_to_read(component),
        qr=QRInfo(**qr_service.qr_payload(component.component_id, component.qr_token)),
        qr_data_uri=qr_service.qr_data_uri(component.component_id),
        service_events=[
            {
                "id": event.id,
                "event_type": event.event_type,
                "event_date": event.event_date,
                "technician": event.technician,
                "description": event.description,
                "operating_hours": event.operating_hours,
                "vibration": event.vibration,
                "temperature": event.temperature,
                "inspection_score": event.inspection_score,
            }
            for event in events
        ],
        predictions=[
            {
                "id": prediction.id,
                "recommendation": prediction.recommendation,
                "recommendation_label": recommendation_label(prediction.recommendation),
                "confidence": prediction.confidence,
                "health_score": prediction.health_score,
                "safety_flag": prediction.safety_flag,
                "safety_message": prediction.safety_message,
                "model_version": prediction.model_version,
                "key_factors": prediction.key_factors,
                "predicted_at": prediction.predicted_at,
            }
            for prediction in predictions
        ],
        audit_trail=[
            {
                "id": entry.id,
                "action": entry.action,
                "actor": entry.actor,
                "timestamp": entry.timestamp,
                "current_hash": entry.current_hash,
                "previous_hash": entry.previous_hash,
                "data_snapshot": entry.data_snapshot,
            }
            for entry in audit_entries
        ],
        impact=impact_service.component_impact(
            component.component_type,
            component.material,
            latest.recommendation if latest else None,
        ),
        standards_basis=standards.standards_summary(component.component_type),
        dpp=dpp_service.identity_summary(component),
        material_profile=_material_profile(component, life_assessment),
        quality_certificate=quality_certificate_service.build(component),
        life_assessment=life_assessment,
        early_warning=early_warning_service.for_component(component),
        scenarios=_public_scenarios(component),
        safety_flag=safety_flag,
        safety_message=SAFETY_GATE_MESSAGE if safety_flag else None,
        disclaimer=RECOMMENDATION_DISCLAIMER,
        data_notice=SYNTHETIC_DATA_NOTICE,
        generated_at=utcnow(),
    )


def _public_scenarios(component: Component, limit: int = 5) -> List[Dict[str, Any]]:
    """Saved simulated scenarios, without who saved them (this path is public)."""
    return [scenario_view(s, include_author=False) for s in component.scenarios[:limit]]


def _material_profile(component: Component, life_assessment: Dict[str, Any] | None) -> Dict[str, Any] | None:
    """The material profile, with its grade cost comparison at this component's own duty."""
    assessment = life_assessment or {}
    rate = assessment.get("ageing_rate") if assessment.get("available") else None
    return life_model.material_profile(component, ageing_rate=rate)


def _life_assessment(component: Component, latest: Prediction | None) -> Dict[str, Any] | None:
    """Usage-adjusted life projection, with its agreement against the AI.

    The two are independent - one a physics-style damage model, one a
    classifier trained on synthetic labels - so whether they agree is worth
    showing: agreement is corroboration, disagreement is a reason to look.
    """
    assessment = life_model.assess(component)
    if assessment.get("supported") and assessment.get("available") and latest is not None:
        assessment["implication"]["ai_recommendation"] = latest.recommendation
        assessment["implication"]["agrees_with_ai"] = (
            latest.recommendation == assessment["implication"]["recommendation"]
        )
    return assessment


@router.get(
    "/{component_id}/life",
    summary="Material composition and usage-adjusted life",
    description=(
        "The material grade profile and the usage-adjusted life projection "
        "(design baseline vs. actual usage, with continue-using / recovery / "
        "replace bands) for one component, without the rest of the passport. Types "
        "the life model does not cover yet return `supported: false`."
    ),
    responses={404: {"description": "Component not found"}},
)
def get_life(component: Component = Depends(get_component_public_or_404)) -> Dict[str, Any]:
    life_assessment = _life_assessment(component, component.latest_prediction)
    return {
        "component_id": component.component_id,
        "material_profile": _material_profile(component, life_assessment),
        "life_assessment": life_assessment,
        "early_warning": early_warning_service.for_component(component),
        "scenarios": _public_scenarios(component),
    }


@router.get(
    "/{component_id}/dpp",
    summary="Digital Product Passport export",
    description=(
        "A registry-shaped Digital Product Passport for one component, mapped "
        "to CPR (EU) 2024/3110: persistent identifier and data carrier, "
        "economic operator, material composition including critical raw "
        "materials, standards basis, lifecycle record and tamper evidence.\n\n"
        "**Registry-shaped, not registry-accepted** - this build has no EU DPP "
        "Registry credentials, and `identification.registry_status` says so."
    ),
    responses={404: {"description": "Component not found"}},
)
def get_dpp(
    component: Component = Depends(get_component_public_or_404),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    return dpp_service.registry_export(db, component)


@router.get(
    "/{component_id}/qr",
    summary="Component QR code (PNG)",
    description=(
        "Returns the passport QR code as a PNG image. The encoded payload is "
        "the public passport URL built from QR_BASE_URL."
    ),
    response_class=Response,
    responses={
        200: {"content": {"image/png": {}}, "description": "QR code image"},
        404: {"description": "Component not found"},
    },
)
def get_qr(
    component: Component = Depends(get_component_public_or_404),
    box_size: int = Query(10, ge=2, le=24, description="Pixel size of one QR module"),
    download: bool = Query(False, description="Send as a file attachment"),
) -> Response:
    png = qr_service.qr_png_bytes(component.component_id, box_size=box_size)
    headers = {"Cache-Control": "public, max-age=86400"}
    if download:
        headers["Content-Disposition"] = (
            f"attachment; filename={component.component_id}-passport-qr.png"
        )
    return Response(content=png, media_type="image/png", headers=headers)


@router.get(
    "/{component_id}/qr/info",
    response_model=QRInfo,
    summary="QR metadata",
    description="The passport URL and image endpoint encoded for this component.",
)
def get_qr_info(component: Component = Depends(get_component_public_or_404)) -> QRInfo:
    return QRInfo(**qr_service.qr_payload(component.component_id, component.qr_token))


@router.get(
    "/lookup/resolve",
    summary="Resolve a scanned QR payload",
    description=(
        "Accepts a full passport URL, a bare component id or a serial number "
        "and returns the canonical component id, so the scanner UI can "
        "navigate reliably."
    ),
)
def resolve_scan(
    value: str = Query(..., description="Raw value read from the QR code"),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    candidate = qr_service.parse_scanned_value(value)
    if not candidate:
        return {"found": False, "input": value, "message": "Empty or unreadable QR payload."}

    component = db.execute(
        select(Component).where(
            (Component.component_id == candidate)
            | (Component.serial_number == candidate)
            | (Component.qr_token == candidate)
        )
    ).scalars().first()

    if component is None:
        return {
            "found": False,
            "input": value,
            "parsed": candidate,
            "message": f"No component matches '{candidate}'.",
        }

    return {
        "found": True,
        "input": value,
        "parsed": candidate,
        "component_id": component.component_id,
        "component_type": component.component_type,
        "passport_url": qr_service.passport_url(component.component_id),
    }


@router.get(
    "/{component_id}/report",
    summary="Auditable passport report",
    description=(
        "A reporting-ready, flattened view of one component: lifecycle, "
        "decision history, audit hash and prototype impact "
        "estimates."
    ),
)
def passport_report(
    component: Component = Depends(get_component_public_or_404), db: Session = Depends(get_db)
) -> Dict[str, Any]:
    audit_entries = audit_service.list_for_entity(db, "component", component.component_id, limit=500)
    predictions: List[Prediction] = list(
        db.execute(
            select(Prediction)
            .where(Prediction.component_id == component.id)
            .order_by(Prediction.predicted_at.desc())
        ).scalars().all()
    )
    latest = predictions[0] if predictions else None

    return {
        "component_id": component.component_id,
        "serial_number": component.serial_number,
        "component_type": component.component_type,
        "material": component.material,
        "material_grade": life_model.grade_label(component),
        "manufacturer": component.manufacturer,
        "origin": component.origin,
        "installation_date": component.installation_date,
        "component_age_years": component.component_age,
        "lifecycle_status": component.current_status,
        "health_score": component.health_score,
        "safety_critical": is_safety_critical(component.component_type),
        "decision_history": [
            {
                "recommendation": prediction.recommendation,
                "recommendation_label": recommendation_label(prediction.recommendation),
                "confidence": prediction.confidence,
                "health_score": prediction.health_score,
                "model_version": prediction.model_version,
                "predicted_at": prediction.predicted_at,
            }
            for prediction in predictions
        ],
        "impact": impact_service.component_impact(
            component.component_type,
            component.material,
            latest.recommendation if latest else None,
        ),
        "audit": {
            "records": len(audit_entries),
            "head_hash": audit_entries[0].current_hash if audit_entries else None,
            "first_record_at": audit_entries[-1].timestamp if audit_entries else None,
            "last_record_at": audit_entries[0].timestamp if audit_entries else None,
        },
        "disclaimer": RECOMMENDATION_DISCLAIMER,
        "data_notice": SYNTHETIC_DATA_NOTICE,
        "generated_at": utcnow(),
    }
