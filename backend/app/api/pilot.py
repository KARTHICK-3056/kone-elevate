"""Pilot metrics (P6). See app.services.pilot_service and docs/pilot-protocol.md."""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services import pilot_service

router = APIRouter(prefix="/pilot", tags=["Pilot"])


@router.get(
    "/metrics",
    summary="Pilot metrics: diversion rate, technician trust, mass diverted",
    description=(
        "The metrics docs/pilot-protocol.md pre-registers before any real "
        "pilot starts. Computed from whatever fleet is currently in this "
        "database - the synthetic demo fleet today, a real pilot's data once "
        "one exists. Nothing about the calculation changes when the data "
        "source does."
    ),
)
def pilot_metrics(db: Session = Depends(get_db)) -> Dict[str, Any]:
    return pilot_service.pilot_metrics(db)
