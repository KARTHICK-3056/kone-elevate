"""Recording lifecycle transitions as mass, for ESRS E5 disclosure.

This module owns one decision: when a component moves from one lifecycle state
to another, did material cross the reporting boundary, and if so in which
direction and by which treatment route?

The boundary
------------
The reporting boundary is the **installed fleet under management**.

* A component entering service (``-> ACTIVE``) is an **inflow** (E5-4). The
  secondary flag is kept for rows with a prior state, but a removed component
  never re-enters service, so no recovery path books a secondary inflow.
* A component whose parts are being recovered, whose material is being recovered, or
  which is thrown away leaves the
  boundary: an **outflow** (E5-5), carrying the treatment route that decides
  whether it counts as diverted from disposal or directed to disposal.
* Everything else - removal, inspection - moves the component
  around inside the boundary and must not be counted. It is still recorded,
  so the ledger tells the whole story rather than a reportable subset.

"""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.component import Component
from app.models.material_flow import MaterialFlow
from app.services import audit_service
from app.utils.enums import (
    AuditAction,
    LifecycleStatus,
    MassSource,
    MaterialFlowDirection,
    OutflowRoute,
)
from app.utils.helpers import utcnow

#: How each destination state sits relative to the reporting boundary.
#: ``LifecycleStatus.ACTIVE`` is the only inflow; the part-recovery, material-recovery and
#: disposal states are the only outflows.
_DESTINATION: Dict[str, tuple[str, Optional[str]]] = {
    LifecycleStatus.ACTIVE.value: (MaterialFlowDirection.INFLOW.value, None),
    LifecycleStatus.UNDER_INSPECTION.value: (MaterialFlowDirection.INTERNAL.value, None),
    LifecycleStatus.REMOVED.value: (MaterialFlowDirection.INTERNAL.value, None),
    LifecycleStatus.RECOVERED.value: (MaterialFlowDirection.INTERNAL.value, None),
    LifecycleStatus.PART_RECOVERY.value: (
        MaterialFlowDirection.OUTFLOW.value,
        OutflowRoute.PREPARATION_FOR_REUSE.value,
    ),
    LifecycleStatus.MATERIAL_RECOVERED.value: (
        MaterialFlowDirection.OUTFLOW.value,
        OutflowRoute.RECYCLING.value,
    ),
    #: Conservative default. ESRS E5-5 wants incineration, landfill and other
    #: disposal split; the platform does not yet capture which one a disposal
    #: used, so it books the route that overstates rather than flatters the
    #: disclosure. Callers that know better pass ``route=`` explicitly.
    LifecycleStatus.DISPOSED.value: (
        MaterialFlowDirection.OUTFLOW.value,
        OutflowRoute.LANDFILL.value,
    ),
}


def classify(from_state: Optional[str], to_state: str) -> tuple[str, Optional[str]]:
    """Classify a transition as inflow, outflow or internal movement.

    A move between two outflow states (``PART_RECOVERY -> MATERIAL_RECOVERED``, say) is
    internal: the material left the boundary once already, and counting it
    again would inflate E5-5.
    """
    direction, route = _DESTINATION.get(
        str(to_state), (MaterialFlowDirection.INTERNAL.value, None)
    )
    if direction == MaterialFlowDirection.OUTFLOW.value and from_state is not None:
        previous_direction, _ = _DESTINATION.get(
            str(from_state), (MaterialFlowDirection.INTERNAL.value, None)
        )
        if previous_direction == MaterialFlowDirection.OUTFLOW.value:
            return MaterialFlowDirection.INTERNAL.value, None
    return direction, route


def resolve_mass(component: Component) -> tuple[float, str]:
    """Return the component's mass in kg and where that figure came from.

    Prefers the mass recorded on the component itself; falls back to the
    illustrative per-type table in configuration. The fallback is flagged so a
    report can disclose how much of its total rests on estimates.
    """
    recorded = getattr(component, "mass_kg", None)
    if recorded is not None and float(recorded) > 0:
        return float(recorded), MassSource.COMPONENT_RECORD.value
    fallback = settings.IMPACT_COMPONENT_MASS_KG.get(str(component.component_type))
    if fallback is None:
        return 0.0, MassSource.CONFIG_ESTIMATE.value
    return float(fallback), MassSource.CONFIG_ESTIMATE.value


def record_transition(
    db: Session,
    component: Component,
    from_state: Optional[str],
    to_state: str,
    actor: str,
    source: str,
    flow_date: Optional[date] = None,
    route: Optional[str] = None,
    notes: Optional[str] = None,
) -> Optional[MaterialFlow]:
    """Append one ledger row for a lifecycle transition, and audit it.

    Returns ``None`` when the state did not actually change, so callers can
    invoke this unconditionally after any write that *might* have moved a
    component. The row is flushed but not committed: it joins the caller's
    transaction so the mass fact and the business change cannot diverge.

    The audit entry is written first and its hash stored on the ledger row, so
    every kilogram in an E5 table traces back to a tamper-evident record.
    """
    if from_state == to_state:
        return None

    direction, default_route = classify(from_state, to_state)
    mass_kg, mass_source = resolve_mass(component)
    is_outflow = direction == MaterialFlowDirection.OUTFLOW.value
    effective_route = (route or default_route) if is_outflow else None
    is_secondary = (
        direction == MaterialFlowDirection.INFLOW.value and from_state is not None
    )
    when = flow_date or utcnow().date()

    snapshot = {
        "component_id": component.component_id,
        "component_type": component.component_type,
        "material": component.material,
        "mass_kg": mass_kg,
        "mass_source": mass_source,
        "from_state": from_state,
        "to_state": to_state,
        "direction": direction,
        "outflow_route": effective_route,
        "is_secondary": is_secondary,
        "flow_date": when.isoformat(),
        "source": source,
    }
    entry = audit_service.record(
        db,
        entity_type="material_flow",
        entity_id=component.component_id,
        action=AuditAction.MATERIAL_FLOW.value,
        data_snapshot=snapshot,
        actor=actor,
    )

    flow = MaterialFlow(
        component_pk=component.id,
        component_id=component.component_id,
        component_type=component.component_type,
        material=component.material,
        mass_kg=mass_kg,
        mass_source=mass_source,
        from_state=from_state,
        to_state=to_state,
        direction=direction,
        outflow_route=effective_route,
        is_secondary=is_secondary,
        flow_date=when,
        actor=actor,
        source=source,
        audit_hash=entry.current_hash,
        notes=notes,
    )
    db.add(flow)
    db.flush()
    return flow


def history_for_component(db: Session, component_id: str) -> List[MaterialFlow]:
    """Every recorded movement for one component, oldest first."""
    return list(
        db.execute(
            select(MaterialFlow)
            .where(MaterialFlow.component_id == component_id)
            .order_by(MaterialFlow.flow_date.asc(), MaterialFlow.id.asc())
        )
        .scalars()
        .all()
    )


def flow_to_dict(flow: MaterialFlow) -> Dict[str, Any]:
    """JSON-friendly view of one ledger row."""
    return {
        "id": flow.id,
        "component_id": flow.component_id,
        "component_type": flow.component_type,
        "material": flow.material,
        "mass_kg": round(flow.mass_kg, 3),
        "mass_source": flow.mass_source,
        "from_state": flow.from_state,
        "to_state": flow.to_state,
        "direction": flow.direction,
        "outflow_route": flow.outflow_route,
        "is_secondary": bool(flow.is_secondary),
        "flow_date": flow.flow_date.isoformat(),
        "actor": flow.actor,
        "source": flow.source,
        "audit_hash": flow.audit_hash,
    }
