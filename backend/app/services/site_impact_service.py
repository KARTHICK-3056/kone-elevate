"""Site-level quarterly economic and CO2 impact - the missing "site model".

The original pitch claimed "Rs.4.9 L and 1.7 t CO2 saved per site per
quarter." ``scripts/derive_impact_claims.py`` (P0) correctly flagged that
figure as NOT DERIVABLE: nothing in the codebase modelled how many
components a site processes in a quarter, or with what disposition mix, so
there was no way to reproduce the number from the same constants the API
returns.

This module is that site model, built entirely from data and forecasts this
system already has - no external dataset required:

    N = components already overdue at this site (current backlog)
      + this site's forecast arrivals in the requested horizon
    projected_value = N x this site's own historical average recovery value
    projected_co2   = N x this site's own historical average CO2 avoided

"This site's own historical average" comes from the (component_type,
material, recommendation) mix of components already assessed at that site -
the same real numbers the Portfolio Command Center's impact tile is built
from, not an invented multiplier. A site with no assessed components yet
falls back to the fleet-wide average and says so explicitly, rather than
silently reporting a zero or a borrowed number as if it were the site's own.

Every figure here is still a **prototype estimate** over a synthetic fleet -
see ``app.services.impact_service`` and ``app.services.forecast_service``,
whose disclaimers this module inherits rather than repeats with different
wording.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.component import Component
from app.services import forecast_service, impact_service
from app.utils.enums import LifecycleStatus

METHOD_NOTE = (
    "N = current backlog at this site (already assessed as no longer suitable to continue using) "
    "+ forecast arrivals at this site over the requested horizon. "
    "projected_value = N x this site's own historical average per "
    "assessed component (fleet-wide average if the site has none yet)."
)

DISCLAIMER = (
    "Prototype estimate over a synthetic fleet - see forecast_service and "
    "impact_service disclaimers. This is a worked example computed from "
    "this system's own data, not a validated KONE site figure."
)

_ACTIVE_STATUSES = (LifecycleStatus.ACTIVE.value, LifecycleStatus.UNDER_INSPECTION.value)


def _site_snapshot(db: Session, site: Optional[str]) -> Dict[str, Any]:
    """This site's own (type, material, recommendation) mix, aggregated in
    SQL, and the average recovery value/CO2 per assessed component it
    implies. ``site=None`` aggregates the whole fleet."""
    filters = [Component.latest_recommendation.isnot(None)]
    if site is not None:
        filters.append(Component.location == site)

    grouped = db.execute(
        select(
            Component.component_type,
            Component.material,
            Component.latest_recommendation,
            func.count(),
        )
        .where(*filters)
        .group_by(Component.component_type, Component.material, Component.latest_recommendation)
    ).all()

    payload = impact_service.portfolio_impact_from_counts(
        ({"component_type": t, "material": m, "recommendation": r}, int(c))
        for t, m, r, c in grouped
    )
    assessed = payload["components_assessed"]
    return {
        "components_assessed": assessed,
        "avg_value_per_component": (
            round(payload["total_recovery_value"] / assessed, 2) if assessed else 0.0
        ),
        "avg_co2_kg_per_component": (
            round(payload["total_co2_avoided_kg"] / assessed, 2) if assessed else 0.0
        ),
    }


def _known_sites(db: Session) -> List[str]:
    rows = (
        db.execute(
            select(Component.location)
            .where(
                Component.location.isnot(None),
                Component.current_status.in_(_ACTIVE_STATUSES),
            )
            .distinct()
        )
        .scalars()
        .all()
    )
    return sorted(rows)


def estimate_site_quarterly_impact(
    db: Session, site: Optional[str] = None, horizon_months: int = 3
) -> Dict[str, Any]:
    """Project the next ``horizon_months`` of recovery value/CO2 for one
    named site, or every site with an active component, plus the fleet-wide
    average across sites - the figure that could replace a bare
    "Rs.X per site per quarter" slide claim.
    """
    fleet = forecast_service.split_fleet(db)
    quarters = max(1, horizon_months // forecast_service.MONTHS_PER_QUARTER)

    backlog_by_site: Dict[str, int] = {}
    for component in fleet["already_due"]:
        key = component.location or "Unknown"
        backlog_by_site[key] = backlog_by_site.get(key, 0) + 1

    forecast_by_site: Dict[str, float] = {}
    if fleet["at_risk"]:
        forecast = forecast_service.forecast_eol(
            db, horizon_months=horizon_months, group_by="site"
        )
        for group in forecast["groups"]:
            forecast_by_site[group["group"]] = sum(
                quarter["expected_removals"] for quarter in group["quarters"][:quarters]
            )

    fleet_wide = _site_snapshot(db, site=None)
    sites = [site] if site else _known_sites(db)

    results: List[Dict[str, Any]] = []
    for one_site in sites:
        backlog_count = backlog_by_site.get(one_site, 0)
        forecast_count = forecast_by_site.get(one_site, 0.0)
        projected_components = backlog_count + forecast_count

        own = _site_snapshot(db, site=one_site)
        used_fallback = own["components_assessed"] == 0
        basis = fleet_wide if used_fallback else own

        results.append(
            {
                "site": one_site,
                "current_backlog_components": backlog_count,
                "forecast_arrivals_components": round(forecast_count, 2),
                "projected_components_this_period": round(projected_components, 2),
                "avg_value_per_component": basis["avg_value_per_component"],
                "avg_co2_kg_per_component": basis["avg_co2_kg_per_component"],
                "projected_value": round(
                    projected_components * basis["avg_value_per_component"], 2
                ),
                "projected_co2_kg": round(
                    projected_components * basis["avg_co2_kg_per_component"], 2
                ),
                "projected_co2_tonnes": round(
                    projected_components * basis["avg_co2_kg_per_component"] / 1000.0, 3
                ),
                "mix_source": (
                    "fleet-wide average (this site has no assessed components yet)"
                    if used_fallback
                    else "this site's own historical assessments"
                ),
                "site_components_assessed": own["components_assessed"],
            }
        )

    results.sort(key=lambda row: row["projected_value"], reverse=True)

    fleet_average = None
    if results:
        count = len(results)
        fleet_average = {
            "sites": count,
            "avg_projected_value_per_site": round(
                sum(row["projected_value"] for row in results) / count, 2
            ),
            "avg_projected_co2_tonnes_per_site": round(
                sum(row["projected_co2_tonnes"] for row in results) / count, 3
            ),
        }

    return {
        "horizon_months": horizon_months,
        "sites": results,
        "fleet_average": fleet_average,
        "currency": settings.IMPACT_CURRENCY,
        "currency_symbol": settings.IMPACT_CURRENCY_SYMBOL,
        "method": METHOD_NOTE,
        "disclaimer": DISCLAIMER,
    }
