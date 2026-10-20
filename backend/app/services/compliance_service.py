"""Regulatory disclosures derived from the material-flow ledger.

Three reports, all built from the same rows:

* **ESRS E5-4 / E5-5** - the EU Corporate Sustainability Reporting Directive's
  resource inflow and outflow disclosures, in tonnes by material, with the
  secondary-material share and the simplified-ESRS critical-raw-materials
  metric.
* **BRSR** - the Indian equivalent for KONE's Indian entity: Principle 2
  reclaimed-input share and Principle 6 waste and circularity.
* **DPP** - a registry-shaped Digital Product Passport export for one
  component, mapped to CPR (EU) 2024/3110.

Every report embeds the audit hash range it was derived from, so an assurance
provider can pull the same rows, recompute the same totals and check them
against a tamper-evident chain rather than taking the number on trust.

What these reports are NOT
--------------------------
They are drafts computed from synthetic components whose masses are, in almost
every case, per-type estimates rather than weighed values. Each report states
its own estimated-mass share for exactly that reason. Nothing here is fit to
file until the ledger is fed by real removals and real weights.
"""

from __future__ import annotations

from calendar import monthrange
from datetime import date
from typing import Any, Dict, Iterable, List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.audit import AuditLog
from app.models.material_flow import MaterialFlow
from app.services import audit_service
from app.utils.enums import (
    DIRECTED_TO_DISPOSAL,
    DIVERTED_FROM_DISPOSAL,
    SYNTHETIC_DATA_NOTICE,
    MassSource,
    MaterialFlowDirection,
    OutflowRoute,
)
from app.utils.helpers import percentage, utcnow

KG_PER_TONNE = 1000.0

PROTOTYPE_NOTICE = (
    "DRAFT - PROTOTYPE. Computed from synthetic component records. Component "
    "masses are predominantly per-type configuration estimates, not weighed "
    "values; see estimated_mass_share_percent. Not fit for filing."
)


class InvalidPeriodError(ValueError):
    """Raised when a reporting period cannot be parsed."""


# --------------------------------------------------------------------------
# Period handling
# --------------------------------------------------------------------------
def parse_period(period: str) -> Tuple[date, date, str]:
    """Parse a reporting period into an inclusive ``(start, end, label)``.

    Accepts a calendar year (``2026``), a quarter (``2026-Q1``), a month
    (``2026-03``) or an explicit range (``2026-01-01:2026-06-30``).
    """
    raw = (period or "").strip().upper()
    if not raw:
        raise InvalidPeriodError("A reporting period is required.")

    try:
        if ":" in raw:
            start_text, end_text = raw.split(":", 1)
            start = date.fromisoformat(start_text.strip())
            end = date.fromisoformat(end_text.strip())
            if end < start:
                raise InvalidPeriodError(
                    f"Period end {end.isoformat()} precedes its start {start.isoformat()}."
                )
            return start, end, f"{start.isoformat()} to {end.isoformat()}"

        if "Q" in raw:
            year_text, quarter_text = raw.split("Q", 1)
            year = int(year_text.rstrip("-"))
            quarter = int(quarter_text)
            if not 1 <= quarter <= 4:
                raise InvalidPeriodError(f"Quarter must be 1-4, got {quarter}.")
            first_month = 3 * (quarter - 1) + 1
            start = date(year, first_month, 1)
            end = _month_end(year, first_month + 2)
            return start, end, f"{year}-Q{quarter}"

        if "-" in raw:
            year_text, month_text = raw.split("-", 1)
            year, month = int(year_text), int(month_text)
            if not 1 <= month <= 12:
                raise InvalidPeriodError(f"Month must be 1-12, got {month}.")
            return date(year, month, 1), _month_end(year, month), f"{year}-{month:02d}"

        year = int(raw)
        return date(year, 1, 1), date(year, 12, 31), str(year)
    except InvalidPeriodError:
        raise
    except (ValueError, TypeError) as exc:
        raise InvalidPeriodError(
            f"Could not parse period '{period}'. Use YYYY, YYYY-Qn, YYYY-MM "
            "or YYYY-MM-DD:YYYY-MM-DD."
        ) from exc


def _month_end(year: int, month: int) -> date:
    """Last day of a month, accepting a month number greater than 12."""
    year += (month - 1) // 12
    month = (month - 1) % 12 + 1
    return date(year, month, monthrange(year, month)[1])


# --------------------------------------------------------------------------
# Ledger access
# --------------------------------------------------------------------------
def _flows_in_period(
    db: Session, start: date, end: date, direction: Optional[str] = None
) -> List[MaterialFlow]:
    statement = (
        select(MaterialFlow)
        .where(MaterialFlow.flow_date >= start)
        .where(MaterialFlow.flow_date <= end)
        .order_by(MaterialFlow.flow_date.asc(), MaterialFlow.id.asc())
    )
    if direction:
        statement = statement.where(MaterialFlow.direction == direction)
    return list(db.execute(statement).scalars().all())


def _tonnes(kg: float) -> float:
    return round(kg / KG_PER_TONNE, 4)


def _estimated_share(flows: Iterable[MaterialFlow]) -> float:
    """Percentage of total mass that rests on a per-type estimate."""
    total = 0.0
    estimated = 0.0
    for flow in flows:
        total += flow.mass_kg
        if flow.mass_source == MassSource.CONFIG_ESTIMATE.value:
            estimated += flow.mass_kg
    return percentage(estimated, total)


def _by_material(flows: Iterable[MaterialFlow]) -> Dict[str, Dict[str, Any]]:
    buckets: Dict[str, Dict[str, Any]] = {}
    for flow in flows:
        bucket = buckets.setdefault(
            flow.material, {"mass_kg": 0.0, "units": 0, "secondary_kg": 0.0}
        )
        bucket["mass_kg"] += flow.mass_kg
        bucket["units"] += 1
        if flow.is_secondary:
            bucket["secondary_kg"] += flow.mass_kg
    return {
        material: {
            "material": material,
            "tonnes": _tonnes(values["mass_kg"]),
            "mass_kg": round(values["mass_kg"], 2),
            "units": values["units"],
            "secondary_tonnes": _tonnes(values["secondary_kg"]),
            "secondary_share_percent": percentage(values["secondary_kg"], values["mass_kg"]),
        }
        for material, values in sorted(
            buckets.items(), key=lambda item: item[1]["mass_kg"], reverse=True
        )
    }


# --------------------------------------------------------------------------
# Provenance: the hash range a report was derived from
# --------------------------------------------------------------------------
def derivation_evidence(db: Session, flows: List[MaterialFlow]) -> Dict[str, Any]:
    """The audit-chain range backing a report, so it can be re-derived.

    Returns the hashes of the first and last audit entries that recorded the
    contributing ledger rows, the count, and the chain head at generation
    time. An assurance provider re-runs the same query, recomputes the totals
    and verifies the chain over that range.
    """
    hashes = [flow.audit_hash for flow in flows if flow.audit_hash]
    entry_ids: List[int] = []
    if hashes:
        entry_ids = [
            int(row)
            for row in db.execute(
                select(AuditLog.id).where(AuditLog.current_hash.in_(hashes))
            ).scalars().all()
        ]

    return {
        "ledger_rows": len(flows),
        "audit_entries": len(entry_ids),
        "first_audit_id": min(entry_ids) if entry_ids else None,
        "last_audit_id": max(entry_ids) if entry_ids else None,
        "first_audit_hash": flows[0].audit_hash if flows else None,
        "last_audit_hash": flows[-1].audit_hash if flows else None,
        "chain_head_hash_at_generation": audit_service.latest_hash(db),
        "verification": (
            "Re-derive by selecting material_flow rows in this period, summing "
            "mass_kg by material, and verifying the audit entries referenced by "
            "each row's audit_hash via GET /api/v1/audit/verify."
        ),
    }


# --------------------------------------------------------------------------
# Critical raw materials
# --------------------------------------------------------------------------
def critical_raw_materials(flows: Iterable[MaterialFlow]) -> Dict[str, Any]:
    """CRM content of a set of flows, by substance.

    The simplified ESRS added a critical-raw-materials metric, and for a lift
    fleet it points at copper windings and any electronic assemblies, which
    carry more listed substance by share than a cast-iron sheave.
    """
    by_substance: Dict[str, float] = {}
    by_component_type: Dict[str, float] = {}
    total_mass = 0.0
    electronic_mass = 0.0

    for flow in flows:
        total_mass += flow.mass_kg
        fractions = settings.CRM_MASS_FRACTION.get(str(flow.material), {})
        if str(flow.material) == "Electronic":
            electronic_mass += flow.mass_kg
        for substance, fraction in fractions.items():
            contribution = flow.mass_kg * float(fraction)
            by_substance[substance] = by_substance.get(substance, 0.0) + contribution
            by_component_type[flow.component_type] = (
                by_component_type.get(flow.component_type, 0.0) + contribution
            )

    crm_total = sum(by_substance.values())
    return {
        "total_crm_tonnes": _tonnes(crm_total),
        "total_crm_kg": round(crm_total, 3),
        "crm_share_of_mass_percent": percentage(crm_total, total_mass, digits=2),
        "electronic_mass_tonnes": _tonnes(electronic_mass),
        "by_substance": {
            substance: {
                "tonnes": _tonnes(mass),
                "kg": round(mass, 3),
                "share_of_crm_percent": percentage(mass, crm_total, digits=2),
            }
            for substance, mass in sorted(
                by_substance.items(), key=lambda item: item[1], reverse=True
            )
        },
        "by_component_type": {
            component_type: {"kg": round(mass, 3), "tonnes": _tonnes(mass)}
            for component_type, mass in sorted(
                by_component_type.items(), key=lambda item: item[1], reverse=True
            )
        },
        "list_reference": settings.CRM_LIST_REFERENCE,
        "basis": (
            "Per-material average mass fractions from configuration "
            "(CRM_MASS_FRACTION). PROTOTYPE ESTIMATES - a filed CRM figure "
            "must come from supplier declarations per article."
        ),
    }


# --------------------------------------------------------------------------
# ESRS E5
# --------------------------------------------------------------------------
def esrs_e5(db: Session, period: str) -> Dict[str, Any]:
    """Draft ESRS E5-4 resource inflows and E5-5 resource outflows."""
    start, end, label = parse_period(period)
    all_flows = _flows_in_period(db, start, end)
    inflows = [f for f in all_flows if f.direction == MaterialFlowDirection.INFLOW.value]
    outflows = [f for f in all_flows if f.direction == MaterialFlowDirection.OUTFLOW.value]

    inflow_mass = sum(f.mass_kg for f in inflows)
    secondary_mass = sum(f.mass_kg for f in inflows if f.is_secondary)
    outflow_mass = sum(f.mass_kg for f in outflows)

    diverted = [f for f in outflows if f.outflow_route in DIVERTED_FROM_DISPOSAL]
    directed = [f for f in outflows if f.outflow_route in DIRECTED_TO_DISPOSAL]
    diverted_mass = sum(f.mass_kg for f in diverted)
    directed_mass = sum(f.mass_kg for f in directed)

    by_route: Dict[str, Dict[str, Any]] = {}
    for route in OutflowRoute.values():
        route_flows = [f for f in outflows if f.outflow_route == route]
        if not route_flows:
            continue
        route_mass = sum(f.mass_kg for f in route_flows)
        by_route[route] = {
            "route": route,
            "tonnes": _tonnes(route_mass),
            "units": len(route_flows),
            "treatment": (
                "diverted_from_disposal"
                if route in DIVERTED_FROM_DISPOSAL
                else "directed_to_disposal"
            ),
        }

    return {
        "standard": "ESRS E5 Resource use and circular economy",
        "regulation": "Directive (EU) 2022/2464 (CSRD), as amended by the 2026 Omnibus",
        "period": {"label": label, "start": start.isoformat(), "end": end.isoformat()},
        "unit": "tonnes",
        "E5-4_resource_inflows": {
            "disclosure": "E5-4 Resource inflows",
            "total_tonnes": _tonnes(inflow_mass),
            "total_units": len(inflows),
            "secondary_reused_tonnes": _tonnes(secondary_mass),
            "secondary_reused_share_percent": percentage(secondary_mass, inflow_mass),
            "virgin_tonnes": _tonnes(inflow_mass - secondary_mass),
            "by_material": _by_material(inflows),
            "critical_raw_materials": critical_raw_materials(inflows),
            "estimated_mass_share_percent": _estimated_share(inflows),
        },
        "E5-5_resource_outflows": {
            "disclosure": "E5-5 Resource outflows",
            "total_tonnes": _tonnes(outflow_mass),
            "total_units": len(outflows),
            "diverted_from_disposal_tonnes": _tonnes(diverted_mass),
            "diverted_from_disposal_percent": percentage(diverted_mass, outflow_mass),
            "directed_to_disposal_tonnes": _tonnes(directed_mass),
            "directed_to_disposal_percent": percentage(directed_mass, outflow_mass),
            "by_route": by_route,
            "by_material": _by_material(outflows),
            "critical_raw_materials": critical_raw_materials(outflows),
            "estimated_mass_share_percent": _estimated_share(outflows),
        },
        "derivation": derivation_evidence(db, all_flows),
        "boundary": (
            "The installed fleet under management. Inflow = a component "
            "entering service; outflow = a component leaving the fleet for "
            "reuse preparation, recycling or disposal. Movements inside the "
            "boundary are recorded in the ledger but excluded here."
        ),
        "notice": PROTOTYPE_NOTICE,
        "data_notice": SYNTHETIC_DATA_NOTICE,
        "generated_at": utcnow().isoformat(),
    }


# --------------------------------------------------------------------------
# BRSR
# --------------------------------------------------------------------------
def brsr(db: Session, period: str) -> Dict[str, Any]:
    """Draft BRSR Principle 2 and Principle 6 circularity disclosures."""
    start, end, label = parse_period(period)
    all_flows = _flows_in_period(db, start, end)
    inflows = [f for f in all_flows if f.direction == MaterialFlowDirection.INFLOW.value]
    outflows = [f for f in all_flows if f.direction == MaterialFlowDirection.OUTFLOW.value]

    inflow_mass = sum(f.mass_kg for f in inflows)
    reclaimed_mass = sum(f.mass_kg for f in inflows if f.is_secondary)
    outflow_mass = sum(f.mass_kg for f in outflows)

    reused_mass = sum(
        f.mass_kg
        for f in outflows
        if f.outflow_route == OutflowRoute.PREPARATION_FOR_REUSE.value
    )
    recycled_mass = sum(
        f.mass_kg for f in outflows if f.outflow_route == OutflowRoute.RECYCLING.value
    )
    recovered_mass = sum(
        f.mass_kg for f in outflows if f.outflow_route == OutflowRoute.OTHER_RECOVERY.value
    )
    disposed_mass = sum(f.mass_kg for f in outflows if f.outflow_route in DIRECTED_TO_DISPOSAL)

    return {
        "framework": "SEBI Business Responsibility and Sustainability Report (BRSR) Core",
        "entity_scope": "Indian operations",
        "period": {"label": label, "start": start.isoformat(), "end": end.isoformat()},
        "unit": "tonnes",
        "principle_2_sustainable_safe_goods": {
            "disclosure": (
                "Principle 2, Essential Indicator: inputs sourced from "
                "recycled or reused material as a share of total inputs"
            ),
            "total_input_tonnes": _tonnes(inflow_mass),
            "reclaimed_input_tonnes": _tonnes(reclaimed_mass),
            "reclaimed_input_share_percent": percentage(reclaimed_mass, inflow_mass),
            "reclaimed_by_material": {
                material: values["secondary_tonnes"]
                for material, values in _by_material(inflows).items()
            },
        },
        "principle_6_environment": {
            "disclosure": (
                "Principle 6, Essential Indicator: waste generated, and waste "
                "recovered through recycling, re-use or other recovery"
            ),
            "total_waste_tonnes": _tonnes(outflow_mass),
            "reused_tonnes": _tonnes(reused_mass),
            "recycled_tonnes": _tonnes(recycled_mass),
            "other_recovery_tonnes": _tonnes(recovered_mass),
            "total_recovered_tonnes": _tonnes(reused_mass + recycled_mass + recovered_mass),
            "recovered_share_percent": percentage(
                reused_mass + recycled_mass + recovered_mass, outflow_mass
            ),
            "disposed_tonnes": _tonnes(disposed_mass),
            "disposed_share_percent": percentage(disposed_mass, outflow_mass),
            "by_material": _by_material(outflows),
        },
        "derivation": derivation_evidence(db, all_flows),
        "notice": PROTOTYPE_NOTICE,
        "data_notice": SYNTHETIC_DATA_NOTICE,
        "generated_at": utcnow().isoformat(),
    }


# --------------------------------------------------------------------------
# Ledger summary (what the compliance page shows before a period is picked)
# --------------------------------------------------------------------------
def ledger_summary(db: Session) -> Dict[str, Any]:
    """Coverage statistics for the ledger itself."""
    total_rows = int(db.execute(select(func.count(MaterialFlow.id))).scalar_one())
    by_direction = {
        str(direction): {"rows": int(rows), "tonnes": _tonnes(float(mass or 0.0))}
        for direction, rows, mass in db.execute(
            select(
                MaterialFlow.direction,
                func.count(MaterialFlow.id),
                func.sum(MaterialFlow.mass_kg),
            ).group_by(MaterialFlow.direction)
        ).all()
    }
    bounds = db.execute(
        select(func.min(MaterialFlow.flow_date), func.max(MaterialFlow.flow_date))
    ).one()
    estimated_rows = int(
        db.execute(
            select(func.count(MaterialFlow.id)).where(
                MaterialFlow.mass_source == MassSource.CONFIG_ESTIMATE.value
            )
        ).scalar_one()
    )

    return {
        "total_rows": total_rows,
        "by_direction": by_direction,
        "first_flow_date": bounds[0].isoformat() if bounds[0] else None,
        "last_flow_date": bounds[1].isoformat() if bounds[1] else None,
        "rows_on_estimated_mass": estimated_rows,
        "estimated_mass_row_share_percent": percentage(estimated_rows, total_rows),
        "chain_head_hash": audit_service.latest_hash(db),
        "notice": PROTOTYPE_NOTICE,
    }
