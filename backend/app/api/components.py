"""Component CRUD, service history and per-component AI assessment."""

from __future__ import annotations

import csv
import io
from datetime import date
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import asc, desc, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import current_actor, get_component_or_404, get_tenant_scope
from app.core.database import get_db
from app.core.tenancy import TenantScope, scope_by_country, scope_by_unit
from app.ml import life_model
from app.models.component import Component
from app.models.prediction import Prediction
from app.models.service_event import ServiceEvent
from app.schemas.component import (
    ComponentCreate,
    ComponentFilters,
    ComponentListItem,
    ComponentPage,
    ComponentRead,
    ComponentUpdate,
    PredictionSummary,
)
from app.schemas.prediction import ImpactEstimate, PredictionHistory, PredictionRead, PredictionResponse
from app.schemas.service_event import ServiceEventCreate, ServiceEventList, ServiceEventRead
from app.services import (
    audit_service,
    impact_service,
    material_flow_service,
    prediction_service,
)
from app.utils.enums import (
    SAFETY_CRITICAL_TYPES,
    AuditAction,
    LifecycleStatus,
    ServiceEventType,
    is_safety_critical,
    recommendation_label,
)
from app.utils import lifecycle
from app.utils.helpers import new_component_id, new_qr_token, new_serial_number, serialise

router = APIRouter(prefix="/components", tags=["Components"])

SORTABLE_FIELDS = {
    "component_id": Component.component_id,
    "component_type": Component.component_type,
    "material": Component.material,
    "health_score": Component.health_score,
    "installation_date": Component.installation_date,
    "operating_hours": Component.operating_hours,
    "current_status": Component.current_status,
    "created_at": Component.created_at,
    "updated_at": Component.updated_at,
}


# --------------------------------------------------------------------------
# Serialisation helpers
# --------------------------------------------------------------------------
def component_to_read(component: Component) -> ComponentRead:
    """Build the full read model, including derived and related fields."""
    latest = component.latest_prediction
    latest_summary = None
    if latest is not None:
        latest_summary = PredictionSummary.model_validate(latest).model_copy(
            update={
                "impact": ImpactEstimate.model_validate(
                    impact_service.component_impact(
                        component.component_type, component.material, latest.recommendation
                    )
                )
            }
        )
    payload = {
        column.name: getattr(component, column.name) for column in Component.__table__.columns
    }
    payload.update(
        {
            "material_grade_label": life_model.grade_label(component),
            "component_age": component.component_age,
            "days_since_last_service": component.days_since_last_service,
            "is_safety_critical": is_safety_critical(component.component_type),
            "latest_prediction": latest_summary,
        }
    )
    return ComponentRead.model_validate(payload)


def component_to_list_item(component: Component) -> ComponentListItem:
    """Build the lightweight table row."""
    latest = component.latest_prediction
    return ComponentListItem(
        id=component.id,
        component_id=component.component_id,
        serial_number=component.serial_number,
        component_type=component.component_type,
        material=component.material,
        material_grade=component.material_grade,
        material_grade_label=life_model.grade_label(component),
        location=component.location,
        installation_date=component.installation_date,
        component_age=component.component_age,
        health_score=component.health_score,
        current_status=component.current_status,
        country=component.country,
        frontline_unit=component.frontline_unit,
        is_safety_critical=is_safety_critical(component.component_type),
        last_service_date=component.last_service_date,
        recommendation=latest.recommendation if latest else None,
        recommendation_label=recommendation_label(latest.recommendation) if latest else None,
        confidence=latest.confidence if latest else None,
        safety_flag=bool(latest.safety_flag) if latest else is_safety_critical(component.component_type),
    )


def _generate_component_id(db: Session, component_type: str) -> str:
    """Allocate the next readable component id for a type."""
    prefix = "".join(ch for ch in component_type.upper() if ch.isalpha())[:3] or "CMP"
    count = int(
        db.execute(
            select(func.count(Component.id)).where(Component.component_type == component_type)
        ).scalar_one()
    )
    for offset in range(1, 500):
        candidate = f"KE-{prefix}-{count + offset:06d}"
        exists = db.execute(
            select(Component.id).where(Component.component_id == candidate)
        ).first()
        if not exists:
            return candidate
    return new_component_id(component_type)  # pragma: no cover - fallback


# --------------------------------------------------------------------------
# Listing
# --------------------------------------------------------------------------
@router.get(
    "",
    response_model=ComponentPage,
    summary="List components",
    description="Search, filter, sort and paginate the component portfolio.",
)
def list_components(
    db: Session = Depends(get_db),
    search: Optional[str] = Query(None, description="Matches component id, serial number or manufacturer"),
    component_type: Optional[List[str]] = Query(None),
    material: Optional[List[str]] = Query(None),
    current_status: Optional[List[str]] = Query(None),
    recommendation: Optional[List[str]] = Query(None),
    location: Optional[str] = Query(None),
    safety_critical: Optional[bool] = Query(None),
    min_health: Optional[float] = Query(None, ge=0, le=100),
    max_health: Optional[float] = Query(None, ge=0, le=100),
    installed_from: Optional[date] = Query(None),
    installed_to: Optional[date] = Query(None),
    sort_by: str = Query("component_id"),
    sort_dir: str = Query("asc", pattern="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    all_units: bool = Query(
        False, description="See every frontline unit in your country, not just your own"
    ),
    scope: TenantScope = Depends(get_tenant_scope),
) -> ComponentPage:
    statement = select(Component).options(selectinload(Component.predictions))
    statement = scope_by_country(statement, Component.country, scope)
    statement = scope_by_unit(statement, Component.frontline_unit, scope, all_units=all_units)
    filters = []

    if search:
        pattern = f"%{search.strip()}%"
        filters.append(
            or_(
                Component.component_id.ilike(pattern),
                Component.serial_number.ilike(pattern),
                Component.manufacturer.ilike(pattern),
                Component.origin.ilike(pattern),
            )
        )
    if component_type:
        filters.append(Component.component_type.in_(component_type))
    if material:
        filters.append(Component.material.in_(material))
    if current_status:
        filters.append(Component.current_status.in_(current_status))
    if location:
        filters.append(Component.location.ilike(f"%{location.strip()}%"))
    if min_health is not None:
        filters.append(Component.health_score >= min_health)
    if max_health is not None:
        filters.append(Component.health_score <= max_health)
    if installed_from:
        filters.append(Component.installation_date >= installed_from)
    if installed_to:
        filters.append(Component.installation_date <= installed_to)
    if safety_critical is True:
        filters.append(Component.component_type.in_(SAFETY_CRITICAL_TYPES))
    elif safety_critical is False:
        filters.append(Component.component_type.notin_(SAFETY_CRITICAL_TYPES))

    if recommendation:
        # Filter on the most recent prediction for each component.
        newest = (
            select(Prediction.component_id, func.max(Prediction.id).label("prediction_id"))
            .group_by(Prediction.component_id)
            .subquery()
        )
        latest_prediction = (
            select(newest.c.component_id)
            .join(Prediction, Prediction.id == newest.c.prediction_id)
            .where(Prediction.recommendation.in_(recommendation))
            .subquery()
        )
        filters.append(Component.id.in_(select(latest_prediction.c.component_id)))

    for condition in filters:
        statement = statement.where(condition)

    total = int(
        db.execute(select(func.count()).select_from(statement.subquery())).scalar_one()
    )

    column = SORTABLE_FIELDS.get(sort_by, Component.component_id)
    ordering = desc(column) if sort_dir == "desc" else asc(column)
    statement = statement.order_by(ordering).offset((page - 1) * page_size).limit(page_size)

    rows = db.execute(statement).scalars().unique().all()
    pages = (total + page_size - 1) // page_size if page_size else 0

    return ComponentPage(
        items=[component_to_list_item(component) for component in rows],
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


@router.get(
    "/filters",
    response_model=ComponentFilters,
    summary="Filter vocabulary",
    description="Distinct values available for the components filter controls.",
)
def component_filters(db: Session = Depends(get_db)) -> ComponentFilters:
    locations = [
        row for row in db.execute(select(Component.location).distinct()).scalars().all() if row
    ]
    manufacturers = [
        row for row in db.execute(select(Component.manufacturer).distinct()).scalars().all() if row
    ]
    return ComponentFilters(locations=sorted(locations), manufacturers=sorted(manufacturers))


@router.get(
    "/export",
    summary="Export components as CSV",
    description="Reporting-ready export of the component portfolio.",
    response_class=Response,
)
def export_components(db: Session = Depends(get_db)) -> Response:
    components = db.execute(
        select(Component).options(selectinload(Component.predictions)).order_by(Component.component_id)
    ).scalars().unique().all()

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "component_id", "serial_number", "component_type", "material", "material_grade",
            "manufacturer",
            "origin", "location", "installation_date", "component_age_years", "operating_hours",
            "load_cycles", "average_load_kg", "vibration_mm_s", "temperature_c", "service_count",
            "repair_count", "failure_history", "inspection_score", "health_score",
            "current_status", "safety_critical", "latest_recommendation",
            "latest_recommendation_label", "latest_confidence", "latest_assessment_at",
        ]
    )
    for component in components:
        latest = component.latest_prediction
        writer.writerow(
            [
                component.component_id, component.serial_number, component.component_type,
                component.material, life_model.grade_label(component),
                component.manufacturer or "", component.origin or "",
                component.location or "",
                component.installation_date.isoformat() if component.installation_date else "",
                component.component_age, component.operating_hours, component.load_cycles,
                component.average_load, component.vibration, component.temperature,
                component.service_count, component.repair_count, component.failure_history,
                component.inspection_score, component.health_score or "",
                component.current_status, is_safety_critical(component.component_type),
                latest.recommendation if latest else "",
                recommendation_label(latest.recommendation) if latest else "",
                latest.confidence if latest else "",
                latest.predicted_at.isoformat() if latest else "",
            ]
        )

    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=kone_elevate_components.csv"},
    )


# --------------------------------------------------------------------------
# Single component
# --------------------------------------------------------------------------
@router.get(
    "/{component_id}",
    response_model=ComponentRead,
    summary="Get one component",
    responses={404: {"description": "Component not found"}},
)
def get_component(component: Component = Depends(get_component_or_404)) -> ComponentRead:
    return component_to_read(component)


@router.post(
    "",
    response_model=ComponentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Register a component",
    description=(
        "Validates the payload, allocates a component id and QR token, writes "
        "the audit record and (by default) runs an initial AI assessment."
    ),
)
def create_component(
    payload: ComponentCreate,
    db: Session = Depends(get_db),
    actor: str = Depends(current_actor),
    scope: TenantScope = Depends(get_tenant_scope),
) -> ComponentRead:
    serial_number = payload.serial_number or new_serial_number(payload.component_type)
    duplicate = db.execute(
        select(Component.id).where(Component.serial_number == serial_number)
    ).first()
    if duplicate:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Serial number '{serial_number}' is already registered.",
        )

    country = payload.country or scope.country
    if not country:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "No country was supplied and this account has no default country "
                "(true for the two global roles). Set 'country' explicitly."
            ),
        )

    component = Component(
        component_id=_generate_component_id(db, payload.component_type),
        serial_number=serial_number,
        component_type=payload.component_type,
        material=payload.material,
        manufacturer=payload.manufacturer,
        origin=payload.origin,
        installation_date=payload.installation_date,
        mass_kg=payload.mass_kg,
        material_grade=payload.material_grade,
        location=payload.location,
        country=country,
        frontline_unit=payload.frontline_unit or scope.frontline_unit,
        operating_hours=payload.operating_hours,
        load_cycles=payload.load_cycles,
        average_load=payload.average_load,
        vibration=payload.vibration,
        temperature=payload.temperature,
        service_count=payload.service_count,
        repair_count=payload.repair_count,
        failure_history=payload.failure_history,
        inspection_score=payload.inspection_score,
        last_service_date=payload.last_service_date,
        current_status=payload.current_status,
        notes=payload.notes,
        qr_token=new_qr_token(),
    )
    db.add(component)
    db.flush()

    audit_service.record(
        db,
        entity_type="component",
        entity_id=component.component_id,
        action=AuditAction.CREATE.value,
        data_snapshot=serialise(component),
        actor=actor,
    )

    material_flow_service.record_transition(
        db,
        component,
        from_state=None,
        to_state=component.current_status,
        actor=actor,
        source="component.create",
        flow_date=payload.installation_date,
    )

    if payload.installation_date:
        installation = ServiceEvent(
            component_id=component.id,
            event_type=ServiceEventType.INSTALLATION.value,
            event_date=payload.installation_date,
            technician=actor,
            description="Component registered in KONE ELEVATE and placed in service.",
            operating_hours=0.0,
            inspection_score=payload.inspection_score,
        )
        db.add(installation)
        db.flush()

    if payload.run_initial_prediction:
        prediction_service.assess_component(db, component, actor=actor, commit=False)

    db.commit()
    db.refresh(component)
    return component_to_read(component)


@router.put(
    "/{component_id}",
    response_model=ComponentRead,
    summary="Update a component",
    description="Partial update. Every change appends an audit-chain record.",
)
def update_component(
    payload: ComponentUpdate,
    component: Component = Depends(get_component_or_404),
    db: Session = Depends(get_db),
    actor: str = Depends(current_actor),
) -> ComponentRead:
    changes: Dict[str, Any] = {}
    updates = payload.model_dump(exclude_unset=True)

    # A removed component can never be set back to ACTIVE by hand - a complete
    # component is never refitted, resold or transferred. Only the moves into
    # ACTIVE the lifecycle state machine allows (back from UNDER_INSPECTION)
    # are accepted; other status edits stay as permissive as before.
    if updates.get("current_status") == LifecycleStatus.ACTIVE.value:
        try:
            lifecycle.assert_transition(component.current_status, LifecycleStatus.ACTIVE.value)
        except lifecycle.InvalidTransitionError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    def _json_safe(value: Any) -> Any:
        return value.isoformat() if isinstance(value, date) else value

    for field, value in updates.items():
        previous = getattr(component, field)
        if previous != value:
            changes[field] = {"from": _json_safe(previous), "to": _json_safe(value)}
            setattr(component, field, value)

    if not changes:
        return component_to_read(component)

    db.flush()
    action = (
        AuditAction.STATUS_CHANGE.value
        if set(changes) == {"current_status"}
        else AuditAction.UPDATE.value
    )
    audit_service.record(
        db,
        entity_type="component",
        entity_id=component.component_id,
        action=action,
        data_snapshot={"changes": changes, "state": serialise(component)},
        actor=actor,
    )
    if "current_status" in changes:
        material_flow_service.record_transition(
            db,
            component,
            from_state=changes["current_status"]["from"],
            to_state=changes["current_status"]["to"],
            actor=actor,
            source="component.update",
        )
    db.commit()
    db.refresh(component)
    return component_to_read(component)


@router.delete(
    "/{component_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete a component",
    description=(
        "Removes the component and its dependent rows. The audit chain is "
        "append-only, so the deletion itself is recorded and prior history "
        "remains verifiable."
    ),
)
def delete_component(
    component: Component = Depends(get_component_or_404),
    db: Session = Depends(get_db),
    actor: str = Depends(current_actor),
) -> Dict[str, Any]:
    snapshot = serialise(component)
    reference = component.component_id
    db.delete(component)
    db.flush()
    audit_service.record(
        db,
        entity_type="component",
        entity_id=reference,
        action=AuditAction.DELETE.value,
        data_snapshot=snapshot,
        actor=actor,
    )
    db.commit()
    return {"deleted": True, "component_id": reference}


# --------------------------------------------------------------------------
# Service history
# --------------------------------------------------------------------------
@router.get(
    "/{component_id}/service-events",
    response_model=ServiceEventList,
    summary="Component service history",
)
def list_service_events(
    component: Component = Depends(get_component_or_404),
    db: Session = Depends(get_db),
    limit: int = Query(100, ge=1, le=500),
) -> ServiceEventList:
    statement = (
        select(ServiceEvent)
        .where(ServiceEvent.component_id == component.id)
        .order_by(ServiceEvent.event_date.desc(), ServiceEvent.id.desc())
        .limit(limit)
    )
    events = list(db.execute(statement).scalars().all())
    return ServiceEventList(
        component_id=component.component_id,
        total=len(events),
        items=[ServiceEventRead.model_validate(event) for event in events],
    )


@router.post(
    "/{component_id}/service-events",
    response_model=ServiceEventRead,
    status_code=status.HTTP_201_CREATED,
    summary="Record a service event",
    description=(
        "Appends an inspection, maintenance, repair, modernisation or removal "
        "event. Readings can be absorbed into the component record, and the "
        "lifecycle status is advanced for REMOVAL events."
    ),
)
def create_service_event(
    payload: ServiceEventCreate,
    component: Component = Depends(get_component_or_404),
    db: Session = Depends(get_db),
    actor: str = Depends(current_actor),
) -> ServiceEventRead:
    status_before = component.current_status

    event = ServiceEvent(
        component_id=component.id,
        event_type=payload.event_type,
        event_date=payload.event_date,
        technician=payload.technician or actor,
        description=payload.description,
        operating_hours=payload.operating_hours,
        vibration=payload.vibration,
        temperature=payload.temperature,
        inspection_score=payload.inspection_score,
        sensor_metadata=payload.sensor_metadata,
    )
    db.add(event)

    if payload.update_component:
        if payload.operating_hours is not None:
            component.operating_hours = payload.operating_hours
        if payload.vibration is not None:
            component.vibration = payload.vibration
        if payload.temperature is not None:
            component.temperature = payload.temperature
        if payload.inspection_score is not None:
            component.inspection_score = payload.inspection_score

        component.last_service_date = payload.event_date
        if payload.event_type in (
            ServiceEventType.MAINTENANCE.value,
            ServiceEventType.INSPECTION.value,
        ):
            component.service_count += 1
        if payload.event_type == ServiceEventType.REPAIR.value:
            component.repair_count += 1
            component.service_count += 1
        if payload.event_type == ServiceEventType.REMOVAL.value:
            component.current_status = LifecycleStatus.REMOVED.value
        if payload.event_type == ServiceEventType.INSPECTION.value and is_safety_critical(
            component.component_type
        ):
            component.current_status = LifecycleStatus.UNDER_INSPECTION.value

    db.flush()
    audit_service.record(
        db,
        entity_type="component",
        entity_id=component.component_id,
        action=AuditAction.SERVICE_EVENT.value,
        data_snapshot={
            "service_event_id": event.id,
            "event_type": event.event_type,
            "event_date": event.event_date.isoformat(),
            "technician": event.technician,
            "readings": {
                "operating_hours": event.operating_hours,
                "vibration": event.vibration,
                "temperature": event.temperature,
                "inspection_score": event.inspection_score,
                "sensor_metadata": event.sensor_metadata,
            },
            "component_status": component.current_status,
            "life_cycle_number": component.life_cycle_number,
        },
        actor=actor,
    )
    material_flow_service.record_transition(
        db,
        component,
        from_state=status_before,
        to_state=component.current_status,
        actor=actor,
        source=f"service_event.{event.event_type}",
        flow_date=event.event_date,
    )
    db.commit()
    db.refresh(event)
    return ServiceEventRead.model_validate(event)


# --------------------------------------------------------------------------
# AI assessment
# --------------------------------------------------------------------------
@router.post(
    "/{component_id}/predict",
    response_model=PredictionResponse,
    summary="Run an AI assessment",
    description=(
        "Scores the stored component, persists an immutable prediction row and "
        "appends an audit record. For safety-critical component types the "
        "response carries a MANDATORY HUMAN INSPECTION flag."
    ),
)
def predict_for_component(
    component: Component = Depends(get_component_or_404),
    db: Session = Depends(get_db),
    actor: str = Depends(current_actor),
    top_factors: int = Query(4, ge=1, le=13),
) -> PredictionResponse:
    _, result = prediction_service.assess_component(
        db, component, actor=actor, top_n=top_factors
    )
    return PredictionResponse.model_validate(result)


@router.get(
    "/{component_id}/predictions",
    response_model=PredictionHistory,
    summary="Assessment history",
)
def list_predictions(
    component: Component = Depends(get_component_or_404),
    db: Session = Depends(get_db),
    limit: int = Query(50, ge=1, le=200),
) -> PredictionHistory:
    rows = prediction_service.history(db, component, limit=limit)
    return PredictionHistory(
        component_id=component.component_id,
        total=len(rows),
        items=[PredictionRead.model_validate(row) for row in rows],
    )
