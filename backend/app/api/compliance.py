"""Regulatory disclosure endpoints: ESRS E5, BRSR, standards and anchoring."""

from __future__ import annotations

import csv
import io
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_actor, require_roles
from app.core.database import get_db
from app.models.component import Component
from app.models.material_flow import MaterialFlow
from app.models.user import User
from app.services import (
    anchor_service,
    circularity_service,
    compliance_service,
    material_flow_service,
)
from app.services.compliance_service import InvalidPeriodError
from app.utils import standards
from app.utils.enums import Role

router = APIRouter(prefix="/reports", tags=["Compliance"])

_PERIOD_DESCRIPTION = (
    "Reporting period: a year (2026), a quarter (2026-Q1), a month (2026-03) "
    "or an explicit range (2026-01-01:2026-06-30)."
)


def _parse_or_422(period: str):
    try:
        return compliance_service.parse_period(period)
    except InvalidPeriodError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc


@router.get(
    "/esrs-e5",
    summary="Draft ESRS E5-4 / E5-5 disclosure",
    description=(
        "Resource inflows (E5-4) and outflows (E5-5) in tonnes by material, "
        "with the secondary/reused share and the simplified-ESRS critical raw "
        "materials metric. Derived entirely from the material-flow ledger, and "
        "carrying the audit hash range needed to re-derive it independently.\n\n"
        "**DRAFT. Computed from synthetic components whose masses are mostly "
        "per-type estimates - see `estimated_mass_share_percent`.**"
    ),
)
def esrs_e5_report(
    period: str = Query(..., description=_PERIOD_DESCRIPTION),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    _parse_or_422(period)
    return compliance_service.esrs_e5(db, period)


@router.get(
    "/brsr",
    summary="Draft BRSR Principle 2 / Principle 6 disclosure",
    description=(
        "The Indian equivalent for KONE's Indian entity: Principle 2 reclaimed "
        "input share and Principle 6 waste and circularity, in tonnes.\n\n"
        "**DRAFT. Synthetic data.**"
    ),
)
def brsr_report(
    period: str = Query(..., description=_PERIOD_DESCRIPTION),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    _parse_or_422(period)
    return compliance_service.brsr(db, period)


@router.get(
    "/material-flow",
    summary="Material-flow ledger rows",
    description=(
        "The underlying kilogram ledger every disclosure is computed from. "
        "Each row names the audit-chain hash that recorded the same transition, "
        "so a reported tonne can be traced to tamper-evident history."
    ),
)
def material_flow_rows(
    period: Optional[str] = Query(None, description=_PERIOD_DESCRIPTION),
    direction: Optional[str] = Query(None, pattern="^(INFLOW|OUTFLOW|INTERNAL)$"),
    component_id: Optional[str] = Query(None),
    limit: int = Query(200, ge=1, le=2000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    statement = select(MaterialFlow)
    if period:
        start, end, _ = _parse_or_422(period)
        statement = statement.where(MaterialFlow.flow_date >= start).where(
            MaterialFlow.flow_date <= end
        )
    if direction:
        statement = statement.where(MaterialFlow.direction == direction)
    if component_id:
        statement = statement.where(MaterialFlow.component_id == component_id)

    rows = list(
        db.execute(
            statement.order_by(MaterialFlow.flow_date.desc(), MaterialFlow.id.desc())
            .offset(offset)
            .limit(limit)
        )
        .scalars()
        .all()
    )
    return {
        "items": [material_flow_service.flow_to_dict(flow) for flow in rows],
        "returned": len(rows),
        "offset": offset,
        "limit": limit,
    }


@router.get(
    "/esrs-e5.csv",
    summary="Draft ESRS E5 disclosure as CSV",
    description="The E5-4 and E5-5 tables flattened for a reporting controller.",
    response_class=Response,
    responses={200: {"content": {"text/csv": {}}}},
)
def esrs_e5_csv(
    period: str = Query(..., description=_PERIOD_DESCRIPTION),
    db: Session = Depends(get_db),
) -> Response:
    _parse_or_422(period)
    report = compliance_service.esrs_e5(db, period)

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["disclosure", "line", "material", "tonnes", "units", "note"])

    inflows = report["E5-4_resource_inflows"]
    writer.writerow(
        ["E5-4", "Total resource inflows", "", inflows["total_tonnes"], inflows["total_units"], ""]
    )
    writer.writerow(
        [
            "E5-4",
            "Secondary / reused inflows",
            "",
            inflows["secondary_reused_tonnes"],
            "",
            f"{inflows['secondary_reused_share_percent']}% of inflows",
        ]
    )
    for material, values in inflows["by_material"].items():
        writer.writerow(["E5-4", "Inflow by material", material, values["tonnes"], values["units"], ""])

    outflows = report["E5-5_resource_outflows"]
    writer.writerow(
        ["E5-5", "Total resource outflows", "", outflows["total_tonnes"], outflows["total_units"], ""]
    )
    writer.writerow(
        [
            "E5-5",
            "Diverted from disposal",
            "",
            outflows["diverted_from_disposal_tonnes"],
            "",
            f"{outflows['diverted_from_disposal_percent']}% of outflows",
        ]
    )
    writer.writerow(
        [
            "E5-5",
            "Directed to disposal",
            "",
            outflows["directed_to_disposal_tonnes"],
            "",
            f"{outflows['directed_to_disposal_percent']}% of outflows",
        ]
    )
    for route, values in outflows["by_route"].items():
        writer.writerow(
            [
                "E5-5",
                "Outflow by route",
                route,
                values["tonnes"],
                values["units"],
                values["treatment"],
            ]
        )
    for material, values in outflows["by_material"].items():
        writer.writerow(["E5-5", "Outflow by material", material, values["tonnes"], values["units"], ""])

    writer.writerow([])
    writer.writerow(["NOTICE", report["notice"], "", "", "", ""])
    writer.writerow(
        [
            "DERIVATION",
            f"ledger rows: {report['derivation']['ledger_rows']}",
            f"first hash: {report['derivation']['first_audit_hash']}",
            f"last hash: {report['derivation']['last_audit_hash']}",
            f"head: {report['derivation']['chain_head_hash_at_generation']}",
            "",
        ]
    )

    label = report["period"]["label"].replace(" ", "")
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=esrs-e5-{label}.csv"},
    )


@router.get(
    "/ledger-summary",
    summary="Material-flow ledger coverage",
    description=(
        "How much the ledger holds, how much of it rests on estimated rather "
        "than weighed mass, and the current chain head."
    ),
)
def ledger_summary(db: Session = Depends(get_db)) -> Dict[str, Any]:
    return compliance_service.ledger_summary(db)


@router.get(
    "/circularity",
    summary="Material Circularity Indicator and the narrow/slow/close breakdown",
    description=(
        "Every other impact figure this platform reports is money. It does not "
        "measure circularity - a fleet can improve it while sending "
        "more material to landfill. This is the Ellen MacArthur Foundation's "
        "Material Circularity Indicator (0 = fully linear, 1 = fully circular), "
        "computed over the same material-flow ledger the ESRS E5 report uses, "
        "plus the three circular-economy strategies reported separately.\n\n"
        "**Narrow is deliberately reported as not measured**: using less "
        "material per unit of service is a design-stage decision this platform "
        "never sees. Slow and close are measured from real ledger rows.\n\n"
        "**Prototype estimate** over estimated masses and placeholder design "
        "lifetimes - every assumption is returned with the figure."
    ),
)
def circularity(
    country: Optional[str] = Query(None, description="Restrict to one country"),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    return circularity_service.fleet_circularity(db, country=country)


@router.get(
    "/circularity/{component_id}",
    summary="Material Circularity Indicator for one component",
    description=(
        "The per-component MCI behind the fleet figure, with every input "
        "exposed so the number can be re-derived by hand."
    ),
)
def component_circularity(
    component_id: str,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    component = db.execute(
        select(Component).where(Component.component_id == component_id)
    ).scalars().first()
    if component is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Component '{component_id}' was not found.",
        )
    return circularity_service.component_mci(db, component)


@router.get(
    "/standards",
    summary="Standards basis catalogue",
    description=(
        "Which published standard governs each component type, and which part "
        "of it. Clause pointers marked CLAUSE_UNVERIFIED were assembled from "
        "public scopes rather than the purchased standard text and must be "
        "confirmed before external use."
    ),
)
def standards_catalogue(
    component_type: Optional[str] = Query(None, description="Filter to one component type"),
) -> Dict[str, Any]:
    if component_type:
        return standards.standards_summary(component_type)
    return standards.all_standards()


@router.get(
    "/anchors",
    summary="Audit-chain anchoring status",
    description=(
        "Daily head-hash commitments and, crucially, whether any of them has "
        "an external witness. Without one the chain is not protected against "
        "an administrator who rebuilds it."
    ),
)
def anchors(
    limit: int = Query(90, ge=1, le=365),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    status_payload = anchor_service.anchor_status(db)
    status_payload["anchors"] = [
        anchor_service.anchor_to_dict(anchor)
        for anchor in anchor_service.list_anchors(db, limit=limit)
    ]
    return status_payload


@router.post(
    "/anchors",
    status_code=status.HTTP_201_CREATED,
    summary="Anchor the current chain head",
    description=(
        "Records a commitment to today's chain head. Publishes it externally "
        "when CHAIN_ANCHOR_WEBHOOK_URL is configured; otherwise records it "
        "locally and says so.\n\n"
        "Restricted to supervisors and sustainability controllers: an anchor "
        "is the commitment a later tamper claim is judged against, so who may "
        "create one is itself part of the control."
    ),
    responses={403: {"description": "Caller's role may not anchor the chain"}},
)
def create_anchor(
    db: Session = Depends(get_db),
    actor: str = Depends(current_actor),
    _: User = Depends(require_roles(Role.SUPERVISOR, Role.SUSTAINABILITY_CONTROLLER)),
) -> Dict[str, Any]:
    anchor = anchor_service.create_anchor(db, actor=actor)
    if anchor is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The audit chain has no records to anchor.",
        )
    payload = anchor_service.anchor_to_dict(anchor)
    payload["status"] = anchor_service.anchor_status(db)["protection"]
    return payload
