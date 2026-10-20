"""End-of-life forecasting and component-recovery capacity endpoints."""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.ml.forecast_registry import forecast_registry
from app.services import forecast_service, site_impact_service
from app.services.forecast_service import ForecastUnavailableError

router = APIRouter(tags=["Forecast"])

_UNAVAILABLE = (
    "No trained forecast model is available. Run "
    "`python scripts/train_forecast.py` to build one."
)


def _guard() -> None:
    if not forecast_registry.is_available:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_UNAVAILABLE,
        )


@router.get(
    "/forecast/eol",
    summary="Forecast end-of-life removals per quarter",
    description=(
        "Expected removals per quarter over the requested horizon, grouped by "
        "component type, site or region, with prediction intervals.\n\n"
        "Expected counts are the sum of per-component probabilities rather than "
        "a count of thresholded predictions - an unbiased estimator that does "
        "not discard the information in a component sitting at 45%.\n\n"
        "**Forecasts are derived from synthetic degradation data.**"
    ),
)
def forecast_eol(
    horizon: int = Query(24, ge=3, le=60, description="Forecast horizon in months"),
    group_by: str = Query("type", pattern="^(type|site|region)$"),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    _guard()
    try:
        return forecast_service.forecast_eol(db, horizon_months=horizon, group_by=group_by)
    except ForecastUnavailableError as exc:  # pragma: no cover - guarded above
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@router.get(
    "/forecast/capacity",
    summary="Component-recovery capacity plan",
    description=(
        "Forecast component-recovery labour hours against declared workshop capacity: "
        "utilisation by quarter, the bottleneck component type, and a levelled "
        "intake schedule that carries un-absorbable work forward so the "
        "consequence of a breach is visible.\n\n"
        "**Labour hours and workshop capacity are prototype configuration "
        "estimates, not KONE workshop standards.**"
    ),
)
def forecast_capacity(
    horizon: int = Query(24, ge=3, le=60, description="Planning horizon in months"),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    _guard()
    return forecast_service.capacity_plan(db, horizon_months=horizon)


@router.get(
    "/forecast/site-impact",
    summary="Projected quarterly recovery value per site",
    description=(
        "The site model the original pitch's 'Rs.4.9L saved per site per "
        "quarter' claim needed and did not have. Projects each "
        "site's queue (current backlog + forecast arrivals over the "
        "horizon) against that site's own historical average recovery "
        "value per assessed component, falling back to the fleet-wide "
        "average for a site with no assessment history yet - and says so.\n\n"
        "**Prototype estimate over a synthetic fleet, not a validated KONE "
        "site figure.**"
    ),
)
def forecast_site_impact(
    site: Optional[str] = Query(None, description="Restrict to one site (location string)"),
    horizon: int = Query(3, ge=3, le=24, description="Projection horizon in months"),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    _guard()
    try:
        return site_impact_service.estimate_site_quarterly_impact(
            db, site=site, horizon_months=horizon
        )
    except ForecastUnavailableError as exc:  # pragma: no cover - guarded above
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@router.get(
    "/forecast/model",
    summary="Forecast model metadata and backtest",
    description=(
        "Weibull AFT fit summary and the published backtest: predicted versus "
        "actual event counts per horizon, and MAPE per component type."
    ),
)
def forecast_model_info(
    full: bool = Query(False, description="Include the full metrics report"),
) -> Dict[str, Any]:
    metadata = forecast_registry.metadata()
    if full and forecast_registry.is_available:
        metadata["metrics"] = forecast_registry.metrics()
    return metadata


@router.post(
    "/forecast/reload",
    summary="Reload the forecast model from disk",
    description="Picks up a freshly trained forecaster without restarting the API.",
)
def reload_forecast_model() -> Dict[str, Any]:
    forecast_registry.reload()
    return forecast_registry.metadata()
