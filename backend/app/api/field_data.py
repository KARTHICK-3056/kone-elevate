"""Field data: measured inspections and sensor / controller telemetry.

The two real-world routes for condition and usage data that need no vendor
account. Both land in the component's own record, so every model downstream
(life model, early-warning forecast, AI classifier) works from them.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.components import create_service_event
from app.api.deps import current_actor, get_component_or_404
from app.core.database import get_db
from app.ml import inspection
from app.models.component import Component
from app.schemas.service_event import ServiceEventCreate
from app.services import telemetry_service
from app.simulation import reference as ref
from app.utils.enums import ServiceEventType

router = APIRouter(tags=["Field data"])

MeasurementValue = float | int | bool | str


# --------------------------------------------------------------------------
# Measured inspections
# --------------------------------------------------------------------------
class InspectionPreview(BaseModel):
    component_type: str
    measurements: Dict[str, MeasurementValue]


class InspectionCreate(BaseModel):
    measurements: Dict[str, MeasurementValue] = Field(
        ..., description="Checklist values keyed as in GET /inspections/checklists."
    )
    event_date: date = Field(default_factory=date.today)
    technician: Optional[str] = Field(None, max_length=96)
    notes: Optional[str] = Field(None, max_length=1500)


@router.get("/inspections/checklists", summary="Measurement checklists per component type")
def get_checklists() -> Dict[str, Any]:
    return {component_type: inspection.checklist(component_type) for component_type in inspection.CHECKLISTS}


@router.post("/inspections/preview", summary="Score measurements without saving")
def preview_inspection(payload: InspectionPreview) -> Dict[str, Any]:
    try:
        return inspection.score(payload.component_type, dict(payload.measurements))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post(
    "/components/{component_id}/inspections",
    status_code=status.HTTP_201_CREATED,
    summary="Record a measured inspection",
    description=(
        "Scores the technician's measurements against the checklist limits, then records "
        "an INSPECTION service event carrying the measurements, the computed inspection "
        "score and - for motors - the measured vibration and temperature."
    ),
)
def record_inspection(
    payload: InspectionCreate,
    component: Component = Depends(get_component_or_404),
    db: Session = Depends(get_db),
    actor: str = Depends(current_actor),
) -> Dict[str, Any]:
    try:
        result = inspection.score(component.component_type, dict(payload.measurements))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    metadata: Dict[str, Any] = {
        key: value for key, value in result["measured_values"].items()
    }
    metadata["inspection_method"] = result["method"]
    metadata["inspection_governing"] = result["governing"]["key"]
    summary = (
        f"Measured inspection: score {result['inspection_score']}/100, governed by "
        f"{result['governing']['label'].lower()}."
    )
    if result["discard_criteria_met"]:
        summary += " DISCARD CRITERIA MET: " + "; ".join(result["discard_criteria_met"]) + "."
    if payload.notes:
        summary += f" Notes: {payload.notes}"

    event = create_service_event(
        ServiceEventCreate(
            event_type=ServiceEventType.INSPECTION.value,
            event_date=payload.event_date,
            technician=payload.technician,
            description=summary,
            vibration=result["readings"].get("vibration"),
            temperature=result["readings"].get("temperature"),
            inspection_score=result["inspection_score"],
            sensor_metadata=metadata,
        ),
        component=component,
        db=db,
        actor=actor,
    )
    return {"inspection": result, "service_event": event}


# --------------------------------------------------------------------------
# Telemetry
# --------------------------------------------------------------------------
class TelemetryRow(BaseModel):
    recorded_at: datetime
    trips: Optional[int] = Field(None, ge=0)
    run_seconds: Optional[float] = Field(None, ge=0)
    load_kg: Optional[float] = Field(None, ge=0)
    load_percent: Optional[float] = Field(None, ge=0)
    vibration: Optional[float] = Field(None, ge=0)
    temperature: Optional[float] = None


class TelemetryBatch(BaseModel):
    source: str = Field(..., min_length=1, max_length=48, description="e.g. iot-retrofit, controller-export")
    rated_load_kg: float = Field(ref.RATED_LOAD_KG, gt=0, le=10_000, description="Used to convert load_percent to kg")
    readings: List[TelemetryRow] = Field(..., min_length=1, max_length=telemetry_service.MAX_BATCH)


@router.post(
    "/components/{component_id}/telemetry",
    summary="Push sensor / controller readings",
    description=(
        "Vendor-neutral intake for any sensor gateway or monitoring system. Counters "
        "(trips, run_seconds) are increments since the previous reading. Idempotent on "
        "(component, recorded_at, source), so retried batches are safe."
    ),
)
def push_telemetry(
    payload: TelemetryBatch,
    component: Component = Depends(get_component_or_404),
    db: Session = Depends(get_db),
    actor: str = Depends(current_actor),
) -> Dict[str, Any]:
    try:
        return telemetry_service.ingest(
            db, component, [row.model_dump() for row in payload.readings],
            payload.source, actor, payload.rated_load_kg,
        )
    except telemetry_service.TelemetryError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post(
    "/components/{component_id}/telemetry/csv",
    summary="Upload a controller / sensor CSV export",
    description=f"CSV with a header row. Columns understood: {', '.join(telemetry_service.CSV_COLUMNS)}.",
)
def upload_telemetry_csv(
    file: UploadFile = File(...),
    source: str = Form("controller-export"),
    rated_load_kg: float = Form(ref.RATED_LOAD_KG),
    component: Component = Depends(get_component_or_404),
    db: Session = Depends(get_db),
    actor: str = Depends(current_actor),
) -> Dict[str, Any]:
    # Sync on purpose: FastAPI runs it in a worker thread, so the blocking
    # database work never stalls the event loop.
    raw = file.file.read()
    if len(raw) > 5_000_000:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="CSV larger than 5 MB.")
    try:
        parsed = telemetry_service.parse_csv(raw.decode("utf-8-sig"))
        if not parsed["rows"]:
            raise telemetry_service.TelemetryError(
                "No readable rows. " + (parsed["errors"][0]["reason"] if parsed["errors"] else "")
            )
        result = telemetry_service.ingest(db, component, parsed["rows"], source, actor, rated_load_kg)
    except (telemetry_service.TelemetryError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {**result, "csv_errors": parsed["errors"], "csv_error_count": parsed["error_count"]}


@router.get("/components/{component_id}/telemetry", summary="Telemetry sources and monthly aggregates")
def get_telemetry(
    component: Component = Depends(get_component_or_404),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    return telemetry_service.summary(db, component)
