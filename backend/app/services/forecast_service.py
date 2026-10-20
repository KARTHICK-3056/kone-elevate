"""Fleet end-of-life forecasting and component-recovery capacity planning.

Turns per-component survival probabilities into the two answers a service
organisation actually needs:

1. **What is coming off the fleet, and when** - expected removals per quarter,
   grouped by component type, site or region, with intervals.
2. **Can we absorb it** - forecast component-recovery labour hours against declared
   workshop capacity, with the bottleneck component type named.

Method note: expected removals in a quarter is the sum over components of
``P(event by end of quarter) - P(event by start of quarter)``. Summing
probabilities rather than counting thresholded predictions is deliberate - it
is an unbiased estimator of the count, and it does not throw away the
information in a component that is 45% likely to need attention.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional, Sequence

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.ml.features import FEATURE_COLUMNS, build_frame, component_to_features
from app.ml.forecast_registry import forecast_registry
from app.models.component import Component
from app.utils.enums import LifecycleStatus, Recommendation

MONTHS_PER_QUARTER = 3
MONTHS_PER_YEAR = 12.0

#: Lifecycle states that are still "in service" and therefore forecastable.
#: A component already removed or sent to material recovery has no remaining life to forecast.
ACTIVE_STATUSES = (
    LifecycleStatus.ACTIVE.value,
    LifecycleStatus.UNDER_INSPECTION.value,
)

#: A component whose latest assessment is already no-longer-suitable has
#: *already* crossed the threshold this model forecasts the crossing of. It is
#: current backlog, not a forecast, and feeding it to the survival model would
#: produce a meaningless "it should have crossed already" probability of ~1
#: piled into the first quarter. Survival analysis applies to the at-risk
#: population only; these are reported separately and counted once.
ALREADY_DUE_RECOMMENDATIONS = frozenset(
    {
        Recommendation.COMPONENT_RECOVERY.value,
        Recommendation.MATERIAL_RECOVERY.value,
        Recommendation.DISPOSE.value,
    }
)

FORECAST_DISCLAIMER = (
    "Forecast produced by a Weibull AFT model fitted to synthetic degradation "
    "data. It describes the simulator's wear physics, not observed KONE "
    "removals, and is not a maintenance schedule."
)


class ForecastUnavailableError(RuntimeError):
    """Raised when the forecast model has not been trained."""


# --------------------------------------------------------------------------
# Grouping
# --------------------------------------------------------------------------
def _region_of(location: Optional[str]) -> str:
    """Region = the country portion of a 'City, Country' location string."""
    if not location:
        return "Unknown"
    parts = [part.strip() for part in location.split(",")]
    return parts[-1] if len(parts) > 1 else parts[0]


def _group_key(component: Component, group_by: str) -> str:
    if group_by == "type":
        return component.component_type
    if group_by == "site":
        return component.location or "Unknown"
    if group_by == "region":
        return _region_of(component.location)
    raise ValueError(f"Unsupported group_by: {group_by}")


# --------------------------------------------------------------------------
# Core probability machinery
# --------------------------------------------------------------------------
def _load_active_components(db: Session) -> List[Component]:
    return list(
        db.execute(
            select(Component).where(Component.current_status.in_(ACTIVE_STATUSES))
        ).scalars().all()
    )


def split_fleet(db: Session) -> Dict[str, List[Component]]:
    """Split the in-service fleet into current backlog and the at-risk set.

    ``already_due``  - latest assessment is no-longer-suitable: the threshold
                       has already been crossed, so there is nothing left to
                       forecast. This is this quarter's workload.
    ``at_risk``      - still assessed CONTINUE_USING, or never assessed: the population
                       the survival model was fitted on and is valid for.
    """
    components = _load_active_components(db)
    already_due, at_risk = [], []
    for component in components:
        latest = component.latest_prediction
        recommendation = latest.recommendation if latest else None
        if recommendation in ALREADY_DUE_RECOMMENDATIONS:
            already_due.append(component)
        else:
            at_risk.append(component)
    return {"already_due": already_due, "at_risk": at_risk, "all": components}


def _backlog_summary(already_due: List[Component]) -> Dict[str, Any]:
    """Counts and labour hours for components that are already past threshold."""
    labour_hours = settings.COMPONENT_RECOVERY_LABOUR_HOURS
    by_type: Dict[str, int] = {}
    for component in already_due:
        by_type[component.component_type] = by_type.get(component.component_type, 0) + 1
    hours = sum(
        float(labour_hours.get(component.component_type, 8.0)) for component in already_due
    ) * float(settings.COMPONENT_RECOVERY_ROUTING_RATE)
    return {
        "components": len(already_due),
        "by_component_type": dict(sorted(by_type.items(), key=lambda kv: kv[1], reverse=True)),
        "recovery_hours_required": round(hours, 1),
        "note": (
            "Already assessed no-longer-suitable: these have crossed the threshold "
            "the forecast predicts, so they are counted as current backlog rather "
            "than forecast demand. Excluding them is why the first forecast quarter "
            "is not dominated by components that are already overdue."
        ),
    }


def _cumulative_event_probabilities(
    components: Sequence[Component], horizon_months: int
) -> Dict[str, np.ndarray]:
    """P(event within t) at each quarter boundary, per component.

    Returns arrays of shape (n_components, n_quarters) for the point estimate
    and both interval bounds.
    """
    if not forecast_registry.is_available:
        raise ForecastUnavailableError(
            "No trained forecast model. Run: python scripts/train_forecast.py"
        )
    model = forecast_registry.model
    preprocessor = forecast_registry.preprocessor

    payloads = [component_to_features(component) for component in components]
    frame = build_frame(payloads)[FEATURE_COLUMNS]
    design = preprocessor.transform(frame)

    quarters = max(1, horizon_months // MONTHS_PER_QUARTER)
    point, lower, upper = [], [], []
    for quarter in range(1, quarters + 1):
        horizon_years = (quarter * MONTHS_PER_QUARTER) / MONTHS_PER_YEAR
        interval = model.event_probability_interval(design, horizon_years)
        point.append(interval["probability"])
        lower.append(interval["lower"])
        upper.append(interval["upper"])

    return {
        "point": np.column_stack(point),
        "lower": np.column_stack(lower),
        "upper": np.column_stack(upper),
        "quarters": quarters,
    }


def _quarter_labels(quarters: int, start: Optional[date] = None) -> List[str]:
    """Calendar labels (e.g. '2026-Q4') for each forecast quarter."""
    start = start or date.today()
    labels = []
    year, quarter_index = start.year, (start.month - 1) // 3
    for _ in range(quarters):
        quarter_index += 1
        if quarter_index > 3:
            quarter_index, year = 0, year + 1
        labels.append(f"{year}-Q{quarter_index + 1}")
    return labels


def _incremental(cumulative: np.ndarray) -> np.ndarray:
    """Per-quarter event probability from the cumulative curve."""
    incremental = np.diff(cumulative, axis=1, prepend=0.0)
    return np.clip(incremental, 0.0, None)


def _bracket_increments(
    point: np.ndarray, low: np.ndarray, high: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Build a valid per-quarter interval from the two perturbed curves.

    The confidence bounds are computed on the CUMULATIVE probability, where
    they are correctly ordered: a longer predicted life always means a lower
    chance of having failed by time t. Differencing consecutive quarters to
    get a per-quarter figure does not preserve that ordering - the upper
    cumulative curve saturates toward 1 sooner, so its later increments fall
    *below* the point estimate's and the bounds cross over.

    So the per-quarter interval is taken as the elementwise min/max of both
    perturbed evaluations and the point estimate. Including the point is what
    guarantees ``lower <= point <= upper`` even where the increment is
    non-monotonic in the scale parameter (it peaks and then decays). This is
    a conservative bracket rather than an exact quantile - the honest choice,
    since the alternative was an interval that silently inverted.
    """
    lower = np.minimum(np.minimum(low, high), point)
    upper = np.maximum(np.maximum(low, high), point)
    return lower, upper


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------
def forecast_eol(
    db: Session, horizon_months: int = 24, group_by: str = "type"
) -> Dict[str, Any]:
    """Expected removals per quarter, grouped, with prediction intervals."""
    fleet = split_fleet(db)
    components = fleet["at_risk"]
    backlog = _backlog_summary(fleet["already_due"])
    if not components:
        return {
            "horizon_months": horizon_months,
            "group_by": group_by,
            "components_in_scope": 0,
            "quarters": [],
            "groups": [],
            "total_expected_removals": 0.0,
            "current_backlog": backlog,
            "model_version": forecast_registry.model_version,
            "data_notice": FORECAST_DISCLAIMER,
        }

    probabilities = _cumulative_event_probabilities(components, horizon_months)
    labels = _quarter_labels(probabilities["quarters"])
    point_increments = _incremental(probabilities["point"])
    low_increments, high_increments = _bracket_increments(
        point_increments,
        _incremental(probabilities["lower"]),
        _incremental(probabilities["upper"]),
    )
    incremental = {"point": point_increments, "lower": low_increments, "upper": high_increments}

    keys = [_group_key(component, group_by) for component in components]
    groups: List[Dict[str, Any]] = []
    for key in sorted(set(keys)):
        mask = np.array([k == key for k in keys])
        per_quarter = incremental["point"][mask].sum(axis=0)
        per_quarter_low = incremental["lower"][mask].sum(axis=0)
        per_quarter_high = incremental["upper"][mask].sum(axis=0)
        groups.append(
            {
                "group": key,
                "components_in_scope": int(mask.sum()),
                "expected_removals_total": round(float(per_quarter.sum()), 2),
                "quarters": [
                    {
                        "quarter": label,
                        "expected_removals": round(float(value), 2),
                        "lower": round(float(low), 2),
                        "upper": round(float(high), 2),
                    }
                    for label, value, low, high in zip(
                        labels, per_quarter, per_quarter_low, per_quarter_high, strict=True
                    )
                ],
            }
        )

    groups.sort(key=lambda row: row["expected_removals_total"], reverse=True)
    total = float(incremental["point"].sum())

    return {
        "horizon_months": horizon_months,
        "group_by": group_by,
        "components_in_scope": len(components),
        "quarters": labels,
        "groups": groups,
        "total_expected_removals": round(total, 2),
        "current_backlog": backlog,
        "model_version": forecast_registry.model_version,
        "method": (
            "Expected count = sum of per-component P(reaches no-longer-suitable) "
            "in each quarter, over the AT-RISK fleet only (components not already "
            "assessed no-longer-suitable). Intervals come from the AFT's "
            "coefficient covariance."
        ),
        "data_notice": FORECAST_DISCLAIMER,
    }


def capacity_plan(db: Session, horizon_months: int = 24) -> Dict[str, Any]:
    """Forecast component-recovery workshop load against declared capacity."""
    fleet = split_fleet(db)
    components = fleet["at_risk"]
    backlog = _backlog_summary(fleet["already_due"])
    capacity = float(settings.WORKSHOP_CAPACITY_HOURS_PER_QUARTER)
    routing_rate = float(settings.COMPONENT_RECOVERY_ROUTING_RATE)
    labour_hours = settings.COMPONENT_RECOVERY_LABOUR_HOURS

    if not components:
        return {
            "horizon_months": horizon_months,
            "quarters": [],
            "bottleneck_component_type": None,
            "capacity_hours_per_quarter": capacity,
            "components_in_scope": 0,
            "current_backlog": backlog,
            "data_notice": FORECAST_DISCLAIMER,
        }

    probabilities = _cumulative_event_probabilities(components, horizon_months)
    labels = _quarter_labels(probabilities["quarters"])
    incremental = _incremental(probabilities["point"])

    types = np.array([component.component_type for component in components])
    hours_per_component = np.array(
        [float(labour_hours.get(component.component_type, 8.0)) for component in components]
    )

    # Only the share actually routed to component recovery consumes workshop hours.
    quarter_hours = (incremental * hours_per_component[:, None]).sum(axis=0) * routing_rate

    # Existing backlog is real load on the workshop in the first quarter.
    # Excluding it would report an idle workshop while work is already queued -
    # the utilisation figure has to answer "will I breach capacity", and the
    # honest answer includes what is already overdue.
    opening_backlog = float(backlog["recovery_hours_required"])

    quarters_out: List[Dict[str, Any]] = []
    for index, label in enumerate(labels):
        forecast_hours = float(quarter_hours[index])
        backlog_hours = opening_backlog if index == 0 else 0.0
        required = forecast_hours + backlog_hours
        utilisation = required / capacity if capacity > 0 else 0.0
        quarters_out.append(
            {
                "quarter": label,
                "forecast_removals": round(float(incremental[:, index].sum()), 2),
                "forecast_hours": round(forecast_hours, 1),
                "backlog_hours": round(backlog_hours, 1),
                "recovery_hours_required": round(required, 1),
                "capacity_hours": capacity,
                "utilisation_percent": round(utilisation * 100.0, 1),
                "over_capacity": bool(required > capacity),
                "surplus_or_deficit_hours": round(capacity - required, 1),
            }
        )

    # Bottleneck: the type consuming the most workshop hours across the horizon.
    hours_by_type: Dict[str, float] = {}
    for component_type in sorted(set(types)):
        mask = types == component_type
        hours_by_type[component_type] = round(
            float((incremental[mask] * hours_per_component[mask, None]).sum() * routing_rate), 1
        )
    bottleneck = max(hours_by_type, key=hours_by_type.get) if hours_by_type else None

    breached = [q["quarter"] for q in quarters_out if q["over_capacity"]]
    peak = max(quarters_out, key=lambda q: q["utilisation_percent"]) if quarters_out else None

    return {
        "horizon_months": horizon_months,
        "components_in_scope": len(components),
        "capacity_hours_per_quarter": capacity,
        "recovery_routing_rate": routing_rate,
        "quarters": quarters_out,
        "hours_by_component_type": hours_by_type,
        "bottleneck_component_type": bottleneck,
        "quarters_over_capacity": breached,
        "peak_utilisation_percent": peak["utilisation_percent"] if peak else 0.0,
        "current_backlog": backlog,
        # The workshop does not start empty: existing backlog is queued ahead of
        # the first forecast quarter's arrivals.
        "recommended_intake_schedule": _intake_schedule(
            quarters_out, capacity, opening_backlog_hours=backlog["recovery_hours_required"]
        ),
        "assumptions": {
            "labour_hours_per_component": labour_hours,
            "note": (
                "PROTOTYPE ESTIMATES. Labour hours, workshop capacity and the "
                "component-recovery routing rate are illustrative configuration values, "
                "not KONE workshop standards."
            ),
        },
        "model_version": forecast_registry.model_version,
        "data_notice": FORECAST_DISCLAIMER,
    }


def _intake_schedule(
    quarters: List[Dict[str, Any]], capacity: float, opening_backlog_hours: float = 0.0
) -> List[Dict[str, Any]]:
    """Level the forecast load against capacity, deferring the overflow.

    A deliberately simple carry-forward: work that cannot be absorbed in the
    quarter it arrives is pushed to the next one, where it competes with that
    quarter's own arrivals. It makes the consequence of a breach visible
    (deferred hours accumulating) rather than silently dropping it.

    ``opening_backlog_hours`` seeds the queue with work that is already
    overdue, so the plan does not pretend the workshop starts empty.
    """
    schedule: List[Dict[str, Any]] = []
    carried = float(opening_backlog_hours)
    for quarter in quarters:
        # forecast_hours, not recovery_hours_required: the latter already
        # folds opening backlog into quarter one, and `carried` seeds it here.
        arriving = quarter["forecast_hours"]
        available = arriving + carried
        scheduled = min(available, capacity)
        carried = max(available - capacity, 0.0)
        schedule.append(
            {
                "quarter": quarter["quarter"],
                "arriving_hours": round(arriving, 1),
                "deferred_in_hours": round(available - arriving, 1),
                "scheduled_hours": round(scheduled, 1),
                "deferred_out_hours": round(carried, 1),
            }
        )
    return schedule
