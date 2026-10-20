"""Gather what the pre-emptive issue forecast needs for one stored component.

The forecast itself (``app.ml.early_warning``) is a pure function so it can be
tested without a database. This module supplies its inputs: the component's
dated service readings, the survival model's 12-month probability, and the
current AI verdict.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from app.core.logging_config import get_logger
from app.ml import early_warning
from app.ml.features import FEATURE_COLUMNS, build_frame, component_to_features
from app.ml.forecast_registry import forecast_registry
from app.models.component import Component
from app.services.forecast_service import ALREADY_DUE_RECOMMENDATIONS

logger = get_logger(__name__)


def survival_probability_12m(component: Component) -> Optional[float]:
    """P(leaving the Continue Using band within a year) from the survival model.

    ``None`` when no forecast model is trained - the forecast then simply has
    one fewer corroborating signal, and says so by its absence.
    """
    if not forecast_registry.is_available:
        return None
    try:
        frame = build_frame([component_to_features(component)])[FEATURE_COLUMNS]
        design = forecast_registry.preprocessor.transform(frame)
        return float(forecast_registry.model.event_probability_within(design, 1.0)[0])
    except Exception:  # pragma: no cover - a corrupt bundle must not break an assessment
        logger.exception("Survival probability unavailable for %s", component.component_id)
        return None


def _readings(component: Component) -> list:
    """Service-event readings plus monthly telemetry means, oldest first."""
    from sqlalchemy.orm import object_session

    from app.services import telemetry_service

    events = list(component.service_events)
    session = object_session(component)
    if session is not None:
        events += telemetry_service.forecast_points(session, component)
    return sorted(events, key=lambda e: e["event_date"] if isinstance(e, dict) else e.event_date)


def for_component(
    component: Component, latest_recommendation: Optional[str] = None
) -> Dict[str, Any]:
    """The pre-emptive issue forecast for one component.

    Trends run over service-visit readings plus monthly averages of any
    sensor telemetry (``telemetry_service``): a component with a retrofit
    sensor gets a trend from continuous data, not only from visits.
    """
    if latest_recommendation is None:
        latest = component.latest_prediction
        latest_recommendation = latest.recommendation if latest else None
    # The survival model was fitted on components still suitable for their
    # current application (see forecast_service.split_fleet). For one the classifier
    # already puts past it, the model saturates towards 100% - an echo of the
    # classifier, not independent evidence - so it is left out rather than
    # counted as a second vote.
    survival = (
        None
        if latest_recommendation in ALREADY_DUE_RECOMMENDATIONS
        else survival_probability_12m(component)
    )
    return early_warning.forecast(
        component,
        events=_readings(component),
        latest_recommendation=latest_recommendation,
        survival_probability_12m=survival,
    )
