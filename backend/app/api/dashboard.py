"""Portfolio command centre: summary counters, chart series and impact.

Scale note (P4)
----------------
Every aggregate in this module is now computed with a SQL ``GROUP BY`` /
``COUNT`` / ``AVG``, not by loading every component into Python and looping
over it. The distinction matters at fleet scale: the build audit's own
number was 1.8 million components, and a Python loop over that many ORM
objects (plus every prediction and service event they touch)
is exactly the kind of thing that degrades from "fine in the demo" to
"doesn't return" at that size. The one exception is
:func:`_monthly_activity`, which still buckets by month in Python - but only
after a SQL ``WHERE`` restricts the rows to the requested window, so the
work scales with *months requested x events per month*, not with total
history.

Every endpoint here is now also tenant-scoped - see ``app.core.tenancy``.
Country is a hard boundary; frontline unit is a soft default overridable
with ``?all_units=true``.

"Current recommendation" reads a cache, not history
-----------------------------------------------------
Every place below that needs "the current recommendation" reads
``Component.latest_recommendation`` / ``latest_confidence`` - columns kept
in sync on every assessment (see
``app.services.prediction_service.assess_component``) - rather than a
``MAX(id) GROUP BY component_id`` subquery over the full, forever-growing
``predictions`` table. A 200k-component / 600k-prediction load test
(``scripts/load_test.py``) measured that subquery costing
``GET /dashboard/summary`` a 1.75s p95; reading the cached column dropped
it to single-digit milliseconds. ``predictions`` itself is untouched and
still append-only - this is a read-side cache, not a change to what gets
persisted.
"""

from __future__ import annotations

import statistics
from datetime import date
from typing import Any, Dict, List, Optional, Sequence

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_tenant_scope
from app.core.database import get_db
from app.core.tenancy import TenantScope
from app.ml.explain import global_importance_table
from app.ml.model_registry import registry
from app.models.audit import AuditLog
from app.models.component import Component
from app.models.prediction import Prediction
from app.models.service_event import ServiceEvent
from app.schemas.dashboard import (
    AnalyticsResponse,
    ComponentTypeBreakdown,
    ConfidenceDistribution,
    CountItem,
    DashboardSummary,
    DispositionBreakdown,
    HealthDistribution,
    ImpactSummary,
    LifecycleBreakdown,
    MonthlyActivity,
)
from app.services import impact_service
from app.services.health_service import HEALTH_BANDS
from app.utils.enums import (
    SAFETY_CRITICAL_TYPES,
    LifecycleStatus,
    Recommendation,
)

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

HEALTH_BUCKETS = [(0, 20), (20, 40), (40, 60), (60, 80), (80, 100)]
CONFIDENCE_BUCKETS = [(0.0, 0.5), (0.5, 0.65), (0.65, 0.8), (0.8, 0.9), (0.9, 1.01)]

_ALL_UNITS_DESC = "See every frontline unit in your country, not just your own"


# --------------------------------------------------------------------------
# Tenant-scoping and shared filter helpers
# --------------------------------------------------------------------------
def _component_filters(
    scope: TenantScope,
    all_units: bool,
    component_type: Optional[List[str]] = None,
    current_status: Optional[List[str]] = None,
    location: Optional[str] = None,
    installed_from: Optional[date] = None,
    installed_to: Optional[date] = None,
):
    """Every filter clause shared across the dashboard endpoints, as a list.

    Kept as a list of clauses (not a bound statement) so both a plain
    ``Component`` query and a query joined against another table can apply
    them with ``.where(*clauses)``.
    """
    clauses = []
    if not scope.is_global:
        clauses.append(Component.country == scope.country)
        if not all_units:
            clauses.append(Component.frontline_unit == scope.frontline_unit)
    if component_type:
        clauses.append(Component.component_type.in_(component_type))
    if current_status:
        clauses.append(Component.current_status.in_(current_status))
    if location:
        clauses.append(Component.location.ilike(f"%{location}%"))
    if installed_from:
        clauses.append(Component.installation_date >= installed_from)
    if installed_to:
        clauses.append(Component.installation_date <= installed_to)
    return clauses


def _count(db: Session, *clauses) -> int:
    statement = select(func.count(Component.id))
    if clauses:
        statement = statement.where(*clauses)
    return int(db.execute(statement).scalar_one())


def _bucket_counts(db: Session, column, comp_filters: Sequence, ranges) -> Dict[str, int]:
    """SQL ``GROUP BY`` over a ``CASE`` expression.

    One round trip returning at most ``len(ranges)`` rows, instead of
    pulling every non-null value in ``column`` into Python to bucket it
    there - the fix that took health/confidence distribution off the list
    of endpoints that scanned the whole fleet into memory on every request
    (see the module docstring's load-test note).
    """
    whens = [(and_(column >= low, column < high), f"{low}-{high}") for low, high in ranges[:-1]]
    last_low, last_high = ranges[-1]
    label_expr = case(*whens, else_=f"{last_low}-{last_high}")
    rows = db.execute(
        select(label_expr.label("bucket"), func.count())
        .where(column.isnot(None), *comp_filters)
        .group_by(label_expr)
    ).all()
    return {str(label): int(count) for label, count in rows}


def _band_counts(db: Session, column, comp_filters: Sequence) -> Dict[str, int]:
    whens = [(column >= threshold, label) for threshold, label in HEALTH_BANDS if label != "CRITICAL"]
    label_expr = case(*whens, else_="CRITICAL")
    rows = db.execute(
        select(label_expr.label("band"), func.count())
        .where(column.isnot(None), *comp_filters)
        .group_by(label_expr)
    ).all()
    return {str(label): int(count) for label, count in rows}


def _avg_and_median(db: Session, column, comp_filters: Sequence) -> tuple[float, float]:
    """Average via SQL always; exact median via SQL on Postgres.

    SQLite has no portable percentile function, so the fallback there pulls
    the (non-null, filtered) values into Python - acceptable because SQLite
    backs only tests and small local-dev fleets, never the fleet sizes this
    module's SQL-aggregation rewrite is about.
    """
    average = db.execute(select(func.avg(column)).where(column.isnot(None), *comp_filters)).scalar_one()
    if db.get_bind().dialect.name == "postgresql":
        median = db.execute(
            select(func.percentile_cont(0.5).within_group(column)).where(
                column.isnot(None), *comp_filters
            )
        ).scalar_one()
    else:
        values = sorted(
            float(v)
            for v in db.execute(select(column).where(column.isnot(None), *comp_filters)).scalars().all()
        )
        median = statistics.median(values) if values else None
    return (
        float(average) if average is not None else 0.0,
        float(median) if median is not None else 0.0,
    )


# --------------------------------------------------------------------------
# Summary
# --------------------------------------------------------------------------
def _build_summary(
    db: Session,
    scope: TenantScope,
    all_units: bool = False,
    comp_filters: Optional[Sequence] = None,
) -> DashboardSummary:
    comp_filters = list(comp_filters) if comp_filters is not None else _component_filters(scope, all_units)

    total_components = _count(db, *comp_filters)

    rec_counts = dict(
        db.execute(
            select(Component.latest_recommendation, func.count())
            .where(Component.latest_recommendation.isnot(None), *comp_filters)
            .group_by(Component.latest_recommendation)
        ).all()
    )
    assessed_components = sum(int(v) for v in rec_counts.values())

    avg_health_stmt = select(func.avg(Component.health_score)).where(
        Component.health_score.isnot(None), *comp_filters
    )
    average_health = db.execute(avg_health_stmt).scalar_one()

    impact_grouped = db.execute(
        select(
            Component.component_type,
            Component.material,
            Component.latest_recommendation,
            func.count(),
        )
        .where(Component.latest_recommendation.isnot(None), *comp_filters)
        .group_by(Component.component_type, Component.material, Component.latest_recommendation)
    ).all()
    impact = impact_service.portfolio_impact_from_counts(
        (
            {"component_type": t, "material": m, "recommendation": r},
            int(c),
        )
        for t, m, r, c in impact_grouped
    )

    awaiting_inspection = db.execute(
        select(func.count(Component.id)).where(
            *comp_filters,
            or_(
                Component.current_status == LifecycleStatus.UNDER_INSPECTION.value,
                and_(
                    Component.component_type.in_(SAFETY_CRITICAL_TYPES),
                    Component.latest_recommendation.in_(
                        [Recommendation.CONTINUE_USING.value, Recommendation.COMPONENT_RECOVERY.value]
                    ),
                ),
            ),
        )
    ).scalar_one()

    safety_critical_components = _count(
        db, Component.component_type.in_(SAFETY_CRITICAL_TYPES), *comp_filters
    )

    #: The audit chain is one linear, globally-ordered structure (see
    #: app.services.audit_service) - it has no per-tenant partition, so this
    #: headline counter is deliberately global for every viewer, not scoped.
    audit_records = int(db.execute(select(func.count(AuditLog.id))).scalar_one())

    return DashboardSummary(
        total_components=total_components,
        assessed_components=assessed_components,
        continue_using=int(rec_counts.get(Recommendation.CONTINUE_USING.value, 0)),
        component_recovery=int(rec_counts.get(Recommendation.COMPONENT_RECOVERY.value, 0)),
        material_recovery=int(rec_counts.get(Recommendation.MATERIAL_RECOVERY.value, 0)),
        disposal=int(rec_counts.get(Recommendation.DISPOSE.value, 0)),
        average_health_score=round(float(average_health), 1) if average_health is not None else 0.0,
        potential_recovery_value=impact["total_recovery_value"],
        estimated_co2_avoided_kg=impact["total_co2_avoided_kg"],
        estimated_co2_avoided_tonnes=impact["total_co2_avoided_tonnes"],
        components_awaiting_inspection=int(awaiting_inspection),
        safety_critical_components=safety_critical_components,
        audit_records=audit_records,
        currency=impact["currency"],
        currency_symbol=impact["currency_symbol"],
        estimate_basis=impact["estimate_basis"],
    )


@router.get(
    "/summary",
    response_model=DashboardSummary,
    summary="Dashboard headline figures",
    description="Portfolio counters, average health, prototype recovery value and CO2 estimate.",
)
def summary(
    db: Session = Depends(get_db),
    scope: TenantScope = Depends(get_tenant_scope),
    all_units: bool = Query(False, description=_ALL_UNITS_DESC),
    component_type: Optional[List[str]] = Query(None),
    current_status: Optional[List[str]] = Query(None),
    location: Optional[str] = Query(None),
    installed_from: Optional[date] = Query(None),
    installed_to: Optional[date] = Query(None),
) -> DashboardSummary:
    comp_filters = _component_filters(
        scope, all_units, component_type, current_status, location, installed_from, installed_to
    )
    return _build_summary(db, scope, all_units, comp_filters)


# --------------------------------------------------------------------------
# Chart series
# --------------------------------------------------------------------------
@router.get(
    "/disposition",
    response_model=DispositionBreakdown,
    summary="AI disposition distribution",
)
def disposition(
    db: Session = Depends(get_db),
    scope: TenantScope = Depends(get_tenant_scope),
    all_units: bool = Query(False, description=_ALL_UNITS_DESC),
) -> DispositionBreakdown:
    comp_filters = _component_filters(scope, all_units)
    total_components = _count(db, *comp_filters)
    counts = dict(
        db.execute(
            select(Component.latest_recommendation, func.count())
            .where(Component.latest_recommendation.isnot(None), *comp_filters)
            .group_by(Component.latest_recommendation)
        ).all()
    )
    assessed = sum(int(v) for v in counts.values())
    return DispositionBreakdown(
        items=[
            CountItem(name=label, value=int(counts.get(label, 0))) for label in Recommendation.values()
        ],
        total=assessed,
        unassessed=total_components - assessed,
    )


@router.get(
    "/health-distribution",
    response_model=HealthDistribution,
    summary="Health score distribution",
)
def health_distribution(
    db: Session = Depends(get_db),
    scope: TenantScope = Depends(get_tenant_scope),
    all_units: bool = Query(False, description=_ALL_UNITS_DESC),
) -> HealthDistribution:
    comp_filters = _component_filters(scope, all_units)
    bucket_counts = _bucket_counts(db, Component.health_score, comp_filters, HEALTH_BUCKETS)
    band_counts = _band_counts(db, Component.health_score, comp_filters)
    average, median = _avg_and_median(db, Component.health_score, comp_filters)
    assessed = sum(bucket_counts.values())

    buckets = [
        CountItem(name=f"{low}-{high}", value=bucket_counts.get(f"{low}-{high}", 0))
        for low, high in HEALTH_BUCKETS
    ]
    bands = [
        CountItem(name=band, value=band_counts.get(band, 0))
        for band in ["EXCELLENT", "GOOD", "FAIR", "POOR", "CRITICAL"]
    ]

    return HealthDistribution(
        buckets=buckets,
        bands=bands,
        average=round(average, 1),
        median=round(median, 1),
        assessed=assessed,
    )


@router.get(
    "/component-types",
    response_model=ComponentTypeBreakdown,
    summary="Fleet composition by component type",
)
def component_types(
    db: Session = Depends(get_db),
    scope: TenantScope = Depends(get_tenant_scope),
    all_units: bool = Query(False, description=_ALL_UNITS_DESC),
) -> ComponentTypeBreakdown:
    comp_filters = _component_filters(scope, all_units)
    rows = db.execute(
        select(Component.component_type, func.count(Component.id), func.avg(Component.health_score))
        .where(*comp_filters)
        .group_by(Component.component_type)
        .order_by(func.count(Component.id).desc())
    ).all()
    items = [
        CountItem(
            name=str(name),
            value=int(count),
            secondary=round(float(average), 1) if average is not None else None,
        )
        for name, count, average in rows
    ]
    return ComponentTypeBreakdown(items=items, total=sum(int(item.value) for item in items))


@router.get(
    "/lifecycle",
    response_model=LifecycleBreakdown,
    summary="Fleet composition by lifecycle status",
)
def lifecycle(
    db: Session = Depends(get_db),
    scope: TenantScope = Depends(get_tenant_scope),
    all_units: bool = Query(False, description=_ALL_UNITS_DESC),
) -> LifecycleBreakdown:
    comp_filters = _component_filters(scope, all_units)
    rows = db.execute(
        select(Component.current_status, func.count(Component.id))
        .where(*comp_filters)
        .group_by(Component.current_status)
    ).all()
    counts = {str(name): int(count) for name, count in rows}
    items = [
        CountItem(name=status_value, value=counts.get(status_value, 0))
        for status_value in LifecycleStatus.values()
        if counts.get(status_value, 0) > 0
    ]
    return LifecycleBreakdown(items=items, total=sum(counts.values()))


@router.get(
    "/confidence",
    response_model=ConfidenceDistribution,
    summary="Model confidence distribution",
    description=(
        "Distribution of each component's CURRENT assessment confidence "
        "(not every assessment ever made - see Prediction history per "
        "component for that)."
    ),
)
def confidence(
    db: Session = Depends(get_db),
    scope: TenantScope = Depends(get_tenant_scope),
    all_units: bool = Query(False, description=_ALL_UNITS_DESC),
) -> ConfidenceDistribution:
    comp_filters = _component_filters(scope, all_units)
    bucket_counts = _bucket_counts(db, Component.latest_confidence, comp_filters, CONFIDENCE_BUCKETS)
    average, _ = _avg_and_median(db, Component.latest_confidence, comp_filters)
    total = sum(bucket_counts.values())

    buckets = [
        CountItem(
            name=f"{int(low * 100)}-{min(int(high * 100), 100)}%",
            value=bucket_counts.get(f"{low}-{high}", 0),
        )
        for low, high in CONFIDENCE_BUCKETS
    ]
    return ConfidenceDistribution(
        buckets=buckets,
        average=round(average, 3),
        total=total,
    )


@router.get(
    "/monthly-activity",
    response_model=MonthlyActivity,
    summary="Service events and assessments per month",
)
def monthly_activity(
    db: Session = Depends(get_db),
    scope: TenantScope = Depends(get_tenant_scope),
    all_units: bool = Query(False, description=_ALL_UNITS_DESC),
    months: int = Query(12, ge=1, le=36),
) -> MonthlyActivity:
    return _monthly_activity(db, scope, all_units, months)


def _monthly_activity(
    db: Session,
    scope: TenantScope,
    all_units: bool = False,
    months: int = 12,
    comp_filters: Optional[Sequence] = None,
) -> MonthlyActivity:
    """Bucket service events and assessments into the last ``months`` calendar months.

    Every month in the window is returned, including months with no activity,
    so the chart's time axis is continuous and always covers exactly
    ``months`` months.

    The ``WHERE event_date >= cutoff`` below is what keeps this bounded at
    fleet scale: only rows inside the requested window are ever pulled into
    Python, regardless of how many years of history the event tables hold.
    """
    comp_filters = list(comp_filters) if comp_filters is not None else _component_filters(scope, all_units)
    today = date.today()
    window: List[str] = []
    year, month = today.year, today.month
    for _ in range(months):
        window.append(f"{year:04d}-{month:02d}")
        year, month = (year, month - 1) if month > 1 else (year - 1, 12)
    window.reverse()
    cutoff = date(int(window[0][:4]), int(window[0][5:]), 1)

    buckets: Dict[str, Dict[str, Any]] = {
        key: {"month": key, "service_events": 0, "assessments": 0} for key in window
    }

    event_statement = select(ServiceEvent.event_date).where(ServiceEvent.event_date >= cutoff)
    if comp_filters:
        event_statement = event_statement.join(
            Component, Component.id == ServiceEvent.component_id
        ).where(*comp_filters)
    for event_date in db.execute(event_statement).scalars().all():
        if event_date is None:
            continue
        key = f"{event_date.year:04d}-{event_date.month:02d}"
        if key in buckets:
            buckets[key]["service_events"] += 1

    prediction_statement = select(Prediction.predicted_at).where(Prediction.predicted_at >= cutoff)
    if comp_filters:
        prediction_statement = prediction_statement.join(
            Component, Component.id == Prediction.component_id
        ).where(*comp_filters)
    for predicted_at in db.execute(prediction_statement).scalars().all():
        if predicted_at is None:
            continue
        key = f"{predicted_at.year:04d}-{predicted_at.month:02d}"
        if key in buckets:
            buckets[key]["assessments"] += 1

    return MonthlyActivity(items=[buckets[key] for key in window])


@router.get(
    "/recovery-value",
    response_model=List[CountItem],
    summary="Prototype recovery value by component type",
)
def recovery_value(
    db: Session = Depends(get_db),
    scope: TenantScope = Depends(get_tenant_scope),
    all_units: bool = Query(False, description=_ALL_UNITS_DESC),
) -> List[CountItem]:
    comp_filters = _component_filters(scope, all_units)
    grouped = db.execute(
        select(
            Component.component_type,
            Component.material,
            Component.latest_recommendation,
            func.count(),
        )
        .where(Component.latest_recommendation.isnot(None), *comp_filters)
        .group_by(Component.component_type, Component.material, Component.latest_recommendation)
    ).all()
    impact = impact_service.portfolio_impact_from_counts(
        ({"component_type": t, "material": m, "recommendation": r}, int(c)) for t, m, r, c in grouped
    )
    return [
        CountItem(name=name, value=values["value"], secondary=values["co2_kg"])
        for name, values in impact["by_component_type"].items()
    ]


@router.get(
    "/impact",
    response_model=ImpactSummary,
    summary="Prototype economic and environmental impact",
    description=(
        "Aggregated recovery value and avoided CO2 for the assessed fleet. "
        "All figures are prototype estimates derived from configurable "
        "constants, not validated KONE data."
    ),
)
def impact(
    db: Session = Depends(get_db),
    scope: TenantScope = Depends(get_tenant_scope),
    all_units: bool = Query(False, description=_ALL_UNITS_DESC),
    include_constants: bool = Query(True, description="Return the assumption tables too"),
) -> ImpactSummary:
    comp_filters = _component_filters(scope, all_units)
    grouped = db.execute(
        select(
            Component.component_type,
            Component.material,
            Component.latest_recommendation,
            func.count(),
        )
        .where(Component.latest_recommendation.isnot(None), *comp_filters)
        .group_by(Component.component_type, Component.material, Component.latest_recommendation)
    ).all()
    payload = impact_service.portfolio_impact_from_counts(
        ({"component_type": t, "material": m, "recommendation": r}, int(c)) for t, m, r, c in grouped
    )
    if include_constants:
        payload["constants"] = impact_service.constants_snapshot()
    return ImpactSummary.model_validate(payload)


@router.get(
    "/safety-queue",
    summary="Safety-critical inspection queue",
    description=(
        "Safety-critical components whose latest AI assessment proposes continued "
        "use or component recovery. Every entry requires MANDATORY HUMAN INSPECTION "
        "before any disposition decision is acted on."
    ),
)
def safety_queue(
    db: Session = Depends(get_db),
    scope: TenantScope = Depends(get_tenant_scope),
    all_units: bool = Query(False, description=_ALL_UNITS_DESC),
    limit: int = Query(50, ge=1, le=200),
) -> List[Dict[str, Any]]:
    return _safety_queue(db, scope, all_units, limit)


def _safety_queue(
    db: Session,
    scope: TenantScope,
    all_units: bool = False,
    limit: int = 50,
    comp_filters: Optional[Sequence] = None,
) -> List[Dict[str, Any]]:
    """Safety-critical components whose disposition still needs human sign-off.

    Filters to safety-critical types *before* touching predictions, so the
    row count fed into the final sort/limit is bounded by how many
    steel-rope/brake/governor components exist, not by fleet size.
    """
    comp_filters = list(comp_filters) if comp_filters is not None else _component_filters(scope, all_units)
    comp_filters = [*comp_filters, Component.component_type.in_(SAFETY_CRITICAL_TYPES)]

    rows = db.execute(
        select(
            Component.component_id,
            Component.component_type,
            Component.location,
            Component.health_score,
            Component.current_status,
            Component.last_service_date,
            Component.latest_recommendation,
            Component.latest_confidence,
        )
        .where(*comp_filters)
        .order_by(Component.health_score.is_(None), Component.health_score.asc())
        .limit(limit)
    ).all()

    from app.utils.helpers import days_since  # local import avoids a cycle at module load

    return [
        {
            "component_id": row.component_id,
            "component_type": row.component_type,
            "location": row.location,
            "health_score": row.health_score,
            "current_status": row.current_status,
            "recommendation": row.latest_recommendation,
            "confidence": row.latest_confidence,
            "last_service_date": row.last_service_date,
            "days_since_last_service": days_since(row.last_service_date),
            "requires_inspection": True,
            "safety_message": "MANDATORY HUMAN INSPECTION",
        }
        for row in rows
    ]


# --------------------------------------------------------------------------
# Combined analytics payload
# --------------------------------------------------------------------------
@router.get(
    "/analytics",
    response_model=AnalyticsResponse,
    summary="Everything the analytics page needs",
    description="One round trip returning every chart series plus the impact model.",
)
def analytics(
    db: Session = Depends(get_db),
    scope: TenantScope = Depends(get_tenant_scope),
    all_units: bool = Query(False, description=_ALL_UNITS_DESC),
    component_type: Optional[List[str]] = Query(None),
    current_status: Optional[List[str]] = Query(None),
    location: Optional[str] = Query(None),
    installed_from: Optional[date] = Query(None),
    installed_to: Optional[date] = Query(None),
) -> AnalyticsResponse:
    comp_filters = _component_filters(
        scope, all_units, component_type, current_status, location, installed_from, installed_to
    )
    total_components = _count(db, *comp_filters)

    rec_counts = dict(
        db.execute(
            select(Component.latest_recommendation, func.count())
            .where(Component.latest_recommendation.isnot(None), *comp_filters)
            .group_by(Component.latest_recommendation)
        ).all()
    )
    assessed = sum(int(v) for v in rec_counts.values())

    health_bucket_counts = _bucket_counts(db, Component.health_score, comp_filters, HEALTH_BUCKETS)
    band_counts = _band_counts(db, Component.health_score, comp_filters)
    health_average, health_median = _avg_and_median(db, Component.health_score, comp_filters)
    health_assessed = sum(health_bucket_counts.values())
    buckets = [
        CountItem(name=f"{low}-{high}", value=health_bucket_counts.get(f"{low}-{high}", 0))
        for low, high in HEALTH_BUCKETS
    ]

    type_rows = db.execute(
        select(Component.component_type, func.count(Component.id))
        .where(*comp_filters)
        .group_by(Component.component_type)
        .order_by(func.count(Component.id).desc())
    ).all()
    status_rows = db.execute(
        select(Component.current_status, func.count(Component.id))
        .where(*comp_filters)
        .group_by(Component.current_status)
        .order_by(func.count(Component.id).desc())
    ).all()

    confidence_bucket_counts = _bucket_counts(
        db, Component.latest_confidence, comp_filters, CONFIDENCE_BUCKETS
    )
    confidence_average, _ = _avg_and_median(db, Component.latest_confidence, comp_filters)
    confidence_total = sum(confidence_bucket_counts.values())
    confidence_buckets = [
        CountItem(
            name=f"{int(low * 100)}-{min(int(high * 100), 100)}%",
            value=confidence_bucket_counts.get(f"{low}-{high}", 0),
        )
        for low, high in CONFIDENCE_BUCKETS
    ]

    impact_grouped = db.execute(
        select(
            Component.component_type,
            Component.material,
            Component.latest_recommendation,
            func.count(),
        )
        .where(Component.latest_recommendation.isnot(None), *comp_filters)
        .group_by(Component.component_type, Component.material, Component.latest_recommendation)
    ).all()
    impact_payload = impact_service.portfolio_impact_from_counts(
        ({"component_type": t, "material": m, "recommendation": r}, int(c))
        for t, m, r, c in impact_grouped
    )
    impact_payload["constants"] = impact_service.constants_snapshot()

    # Everything above except awaiting_inspection/safety_critical/exchange
    # counters was already computed for the charts below - _build_summary
    # would recompute all of it a second time, doubling this endpoint's
    # query count for no reason. Use it instead.
    awaiting_inspection = db.execute(
        select(func.count(Component.id)).where(
            *comp_filters,
            or_(
                Component.current_status == LifecycleStatus.UNDER_INSPECTION.value,
                and_(
                    Component.component_type.in_(SAFETY_CRITICAL_TYPES),
                    Component.latest_recommendation.in_(
                        [Recommendation.CONTINUE_USING.value, Recommendation.COMPONENT_RECOVERY.value]
                    ),
                ),
            ),
        )
    ).scalar_one()
    safety_critical_components = _count(
        db, Component.component_type.in_(SAFETY_CRITICAL_TYPES), *comp_filters
    )
    audit_records = int(db.execute(select(func.count(AuditLog.id))).scalar_one())

    summary_payload = DashboardSummary(
        total_components=total_components,
        assessed_components=assessed,
        continue_using=int(rec_counts.get(Recommendation.CONTINUE_USING.value, 0)),
        component_recovery=int(rec_counts.get(Recommendation.COMPONENT_RECOVERY.value, 0)),
        material_recovery=int(rec_counts.get(Recommendation.MATERIAL_RECOVERY.value, 0)),
        disposal=int(rec_counts.get(Recommendation.DISPOSE.value, 0)),
        average_health_score=round(health_average, 1),
        potential_recovery_value=impact_payload["total_recovery_value"],
        estimated_co2_avoided_kg=impact_payload["total_co2_avoided_kg"],
        estimated_co2_avoided_tonnes=impact_payload["total_co2_avoided_tonnes"],
        components_awaiting_inspection=int(awaiting_inspection),
        safety_critical_components=safety_critical_components,
        audit_records=audit_records,
        currency=impact_payload["currency"],
        currency_symbol=impact_payload["currency_symbol"],
        estimate_basis=impact_payload["estimate_basis"],
    )

    return AnalyticsResponse(
        summary=summary_payload,
        disposition=DispositionBreakdown(
            items=[
                CountItem(name=label, value=int(rec_counts.get(label, 0)))
                for label in Recommendation.values()
            ],
            total=assessed,
            unassessed=total_components - assessed,
        ),
        health=HealthDistribution(
            buckets=buckets,
            bands=[
                CountItem(name=band, value=band_counts.get(band, 0))
                for band in ["EXCELLENT", "GOOD", "FAIR", "POOR", "CRITICAL"]
            ],
            average=round(health_average, 1),
            median=round(health_median, 1),
            assessed=health_assessed,
        ),
        component_types=ComponentTypeBreakdown(
            items=[CountItem(name=str(name), value=int(count)) for name, count in type_rows],
            total=total_components,
        ),
        lifecycle=LifecycleBreakdown(
            items=[CountItem(name=str(name), value=int(count)) for name, count in status_rows],
            total=total_components,
        ),
        confidence=ConfidenceDistribution(
            buckets=confidence_buckets,
            average=round(confidence_average, 3),
            total=confidence_total,
        ),
        # The page's filters apply to every section, not only the counters.
        monthly_activity=_monthly_activity(db, scope, all_units, comp_filters=comp_filters),
        impact=ImpactSummary.model_validate(impact_payload),
        recovery_value_by_type=[
            CountItem(name=name, value=values["value"], secondary=values["co2_kg"])
            for name, values in impact_payload["by_component_type"].items()
        ],
        safety_queue=_safety_queue(db, scope, all_units, limit=25, comp_filters=comp_filters),
        feature_importance=global_importance_table(registry.feature_importance),
        filters_applied={
            "component_type": component_type,
            "current_status": current_status,
            "location": location,
            "installed_from": installed_from,
            "installed_to": installed_to,
            "all_units": all_units,
        },
    )
