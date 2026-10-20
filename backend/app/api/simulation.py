"""Interactive lift simulation: the user sets the load, everything else is derived.

Stateless on the server - the client holds the simulation state and sends it
back with each step. A simulation can start from a new lift or from a real
component's record; either way nothing here changes a component, a
prediction or any fleet figure. The one thing that is stored is a *saved
scenario*, in its own table, labelled as simulated.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_actor, get_component_or_404, get_tenant_scope
from app.core.database import get_db
from app.core.tenancy import TenantScope
from app.models.component import Component
from app.models.simulation import SimulationScenario
from app.services import audit_service
from app.simulation import engine
from app.simulation import reference as ref
from app.utils.enums import AuditAction

router = APIRouter(prefix="/simulation", tags=["Simulation"])


class AdvanceRequest(BaseModel):
    """One step of the simulation."""

    state: Optional[Dict[str, Any]] = Field(
        None, description="The state returned by the previous step; null starts a new lift."
    )
    load_kg: float = Field(
        ..., ge=0, le=ref.MAX_LOAD_KG,
        description="Average load per trip in kg - the one input the user controls.",
    )
    months: int = Field(3, ge=1, le=engine.MAX_MONTHS_PER_CALL, description="Months to simulate.")


class ScenarioCreate(BaseModel):
    """Save the current simulation to the focus component's passport."""

    state: Dict[str, Any]
    name: Optional[str] = Field(None, max_length=96)


def _unprocessable(exc: ValueError) -> HTTPException:
    return HTTPException(status_code=422, detail=str(exc))


def scenario_view(scenario: SimulationScenario, include_author: bool = True) -> Dict[str, Any]:
    """A saved scenario as the API returns it."""
    view = {
        "id": scenario.id,
        "name": scenario.name,
        "load_kg": scenario.load_kg,
        "historical_load_kg": scenario.historical_load_kg,
        "months_simulated": scenario.months_simulated,
        "created_at": scenario.created_at,
        "summary": scenario.summary,
    }
    if include_author:
        view["created_by"] = scenario.created_by
    return view


@router.get(
    "/reference",
    summary="Simulation calibration reference",
    description=(
        "The lift geometry, traffic and environment the simulation is calibrated on, "
        "each value tagged kone_api / standard / physics / assumption, plus how each "
        "of the 13 model parameters is derived from the user's load."
    ),
)
def get_reference() -> Dict[str, Any]:
    return {
        "reference": ref.reference_profile(),
        "parameter_basis": engine.parameter_basis(),
        "components": list(engine.COMPONENTS),
        "max_months_per_step": engine.MAX_MONTHS_PER_CALL,
        "max_years": engine.MAX_SIMULATED_MONTHS // 12,
    }


@router.post(
    "/advance",
    summary="Advance the simulation",
    description=(
        "Runs the lift for `months` months at `load_kg`. Returns the new state (send it "
        "back next time), a monthly series of true and estimated wear, the 13 derived "
        "parameters per component with the life model, early-warning forecast and AI "
        "assessment computed from them, and any new events."
    ),
)
def advance(payload: AdvanceRequest) -> Dict[str, Any]:
    try:
        return engine.advance(payload.state, payload.load_kg, payload.months)
    except ValueError as exc:
        raise _unprocessable(exc) from exc


@router.post(
    "/start/{component_id}",
    summary="Start a simulation from a real component",
    description=(
        "Seeds the simulation with a real component's record - age, counters, service "
        "history, readings and material - and calibrates the simulated physics to the "
        "unit's own readings. Returns the same shape as /advance. Nothing is written."
    ),
)
def start_from_component(component: Component = Depends(get_component_or_404)) -> Dict[str, Any]:
    try:
        return engine.start_from_component(component, list(component.service_events))
    except ValueError as exc:
        raise _unprocessable(exc) from exc


@router.post(
    "/scenarios/{component_id}",
    status_code=status.HTTP_201_CREATED,
    summary="Save a simulated scenario to the component's passport",
    description=(
        "Stores the simulated future of the focus component, clearly labelled as a "
        "SIMULATION. It never changes the component and is never counted in any "
        "dashboard, forecast or report."
    ),
)
def save_scenario(
    payload: ScenarioCreate,
    component: Component = Depends(get_component_or_404),
    db: Session = Depends(get_db),
    actor: str = Depends(current_actor),
) -> Dict[str, Any]:
    focus = (payload.state or {}).get("focus") or {}
    if focus.get("component_id") != component.component_id:
        raise HTTPException(
            status_code=422,
            detail="This simulation was not started from this component.",
        )
    try:
        summary = engine.scenario_summary(payload.state)
    except ValueError as exc:
        raise _unprocessable(exc) from exc

    name = payload.name or (
        f"{summary['final_load_kg']:.0f} kg for {summary['months_simulated'] / 12:.1f} years"
    )
    scenario = SimulationScenario(
        component_id=component.id,
        name=name,
        load_kg=summary["final_load_kg"],
        historical_load_kg=summary["historical_load_kg"],
        months_simulated=summary["months_simulated"],
        summary=summary,
        created_by=actor,
    )
    db.add(scenario)
    db.flush()
    audit_service.record(
        db,
        entity_type="component",
        entity_id=component.component_id,
        action=AuditAction.SCENARIO_SAVED.value,
        data_snapshot={
            "scenario_id": scenario.id,
            "name": name,
            "simulated": True,
            "loads_simulated_kg": summary["loads_simulated_kg"],
            "months_simulated": summary["months_simulated"],
            "replacements": summary["replacements"],
        },
        actor=actor,
    )
    db.commit()
    db.refresh(scenario)
    return scenario_view(scenario)


@router.get(
    "/scenarios/{component_id}",
    summary="Saved scenarios for a component",
)
def list_scenarios(
    component: Component = Depends(get_component_or_404),
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    rows = db.execute(
        select(SimulationScenario)
        .where(SimulationScenario.component_id == component.id)
        .order_by(SimulationScenario.created_at.desc())
    ).scalars().all()
    return [scenario_view(row) for row in rows]


@router.delete(
    "/scenarios/item/{scenario_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a saved scenario",
)
def delete_scenario(
    scenario_id: int,
    db: Session = Depends(get_db),
    scope: TenantScope = Depends(get_tenant_scope),
    actor: str = Depends(current_actor),
) -> Response:
    scenario = db.get(SimulationScenario, scenario_id)
    if scenario is None or not scope.owns_country(scenario.component.country):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scenario not found.")
    component_id = scenario.component.component_id
    db.delete(scenario)
    audit_service.record(
        db,
        entity_type="component",
        entity_id=component_id,
        action=AuditAction.SCENARIO_DELETED.value,
        data_snapshot={"scenario_id": scenario_id},
        actor=actor,
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
