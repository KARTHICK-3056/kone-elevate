"""Prototype economic and environmental impact estimation.

IMPORTANT DISCLOSURE
--------------------
Every figure produced by this module is a **prototype estimate** computed from
the illustrative constants in ``app.core.config``. They are not official KONE
cost, mass or emission factors, and they are not suitable for external
sustainability reporting. They exist so the demo can show the *shape* of the
circular-economy business case.

Model
-----
    recovered_value = new_part_cost[type] x value_recovery_factor[disposition]
    co2_avoided     = mass[type] x co2_intensity[material]
                                 x co2_avoidance_factor[disposition]

Both factor tables are configuration, so an engineering team can replace them
with validated values without touching application code.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from app.core.config import settings
from app.utils.enums import Recommendation

PROTOTYPE_LABEL = "Prototype estimate"

DISCLAIMER = (
    "Prototype estimate. Economic figures are derived from illustrative "
    "configuration constants, not from validated KONE cost data."
)


def new_part_cost(component_type: str) -> float:
    """Illustrative replacement cost of a new component of this type."""
    return float(settings.IMPACT_NEW_PART_COST.get(str(component_type), 60_000.0))


def component_mass(component_type: str) -> float:
    """Illustrative mass in kilograms."""
    return float(settings.IMPACT_COMPONENT_MASS_KG.get(str(component_type), 60.0))


def co2_intensity(material: str) -> float:
    """Illustrative embodied-carbon intensity in kg CO2e per kg of material."""
    return float(settings.IMPACT_CO2_PER_KG.get(str(material), 2.0))


def value_factor(recommendation: Optional[str]) -> float:
    return float(settings.IMPACT_VALUE_RECOVERY_FACTOR.get(str(recommendation), 0.0))


def co2_factor(recommendation: Optional[str]) -> float:
    return float(settings.IMPACT_CO2_AVOIDANCE_FACTOR.get(str(recommendation), 0.0))


def estimate_value(component_type: str, recommendation: Optional[str]) -> float:
    """Estimated recoverable economic value for a disposition."""
    return round(new_part_cost(component_type) * value_factor(recommendation), 2)


def estimate_co2_saving(component_type: str, material: str, recommendation: Optional[str]) -> float:
    """Estimated CO2e avoided (kg) by not manufacturing a replacement."""
    embodied = component_mass(component_type) * co2_intensity(material)
    return round(embodied * co2_factor(recommendation), 2)


def component_impact(
    component_type: str, material: str, recommendation: Optional[str]
) -> Dict[str, Any]:
    """Full impact breakdown for a single component."""
    embodied = round(component_mass(component_type) * co2_intensity(material), 2)
    return {
        "component_type": component_type,
        "material": material,
        "recommendation": recommendation,
        "new_part_cost": round(new_part_cost(component_type), 2),
        "estimated_recovery_value": estimate_value(component_type, recommendation),
        "value_recovery_factor": value_factor(recommendation),
        "component_mass_kg": component_mass(component_type),
        "embodied_co2_kg": embodied,
        "estimated_co2_avoided_kg": estimate_co2_saving(component_type, material, recommendation),
        "co2_avoidance_factor": co2_factor(recommendation),
        "currency": settings.IMPACT_CURRENCY,
        "currency_symbol": settings.IMPACT_CURRENCY_SYMBOL,
        "estimate_basis": PROTOTYPE_LABEL,
        "disclaimer": DISCLAIMER,
    }


def portfolio_impact(rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate impact across a portfolio of assessed components.

    ``rows`` is any iterable of dicts with ``component_type``, ``material`` and
    ``recommendation`` keys (typically produced by a database query).

    This iterates once per *component*. At fleet scale that is exactly the
    O(n) Python loop the build audit flagged in dashboard aggregation - use
    :func:`portfolio_impact_from_counts` with a SQL ``GROUP BY`` instead
    wherever the caller can produce pre-aggregated counts; this function
    stays for the few call sites (CSV export, ad-hoc scripts) that
    legitimately need one row per component.
    """
    return portfolio_impact_from_counts(
        (
            {
                "component_type": row.get("component_type"),
                "material": row.get("material"),
                "recommendation": row.get("recommendation"),
            },
            1,
        )
        for row in rows
    )


def portfolio_impact_from_counts(
    grouped_rows: Iterable[tuple[Dict[str, Any], int]],
) -> Dict[str, Any]:
    """Aggregate impact from pre-grouped ``(dimensions, count)`` pairs.

    ``dimensions`` needs ``component_type``, ``material`` and
    ``recommendation``. Because a fleet has only a handful of distinct
    (type, material, recommendation) combinations - a few hundred at most,
    regardless of whether the fleet is 1,000 components or 1.8 million - a
    caller that does the counting in one SQL ``GROUP BY`` query and passes
    the result here does a fixed amount of Python work independent of fleet
    size, instead of one iteration per component.
    """
    total_value = 0.0
    total_co2 = 0.0
    total_new_cost = 0.0
    diverted = 0
    counted = 0
    by_disposition: Dict[str, Dict[str, float]] = {
        label: {"count": 0, "value": 0.0, "co2": 0.0} for label in Recommendation.values()
    }
    by_type: Dict[str, Dict[str, float]] = {}

    for row, count in grouped_rows:
        component_type = row.get("component_type")
        material = row.get("material")
        recommendation = row.get("recommendation")
        if not component_type or not material or not count:
            continue

        counted += count
        value = estimate_value(component_type, recommendation) * count
        co2 = estimate_co2_saving(component_type, material, recommendation) * count
        total_value += value
        total_co2 += co2
        total_new_cost += new_part_cost(component_type) * count

        if recommendation in (
            Recommendation.CONTINUE_USING.value,
            Recommendation.COMPONENT_RECOVERY.value,
            Recommendation.MATERIAL_RECOVERY.value,
        ):
            diverted += count

        bucket = by_disposition.setdefault(
            str(recommendation), {"count": 0, "value": 0.0, "co2": 0.0}
        )
        bucket["count"] += count
        bucket["value"] += value
        bucket["co2"] += co2

        type_bucket = by_type.setdefault(
            str(component_type), {"count": 0, "value": 0.0, "co2": 0.0}
        )
        type_bucket["count"] += count
        type_bucket["value"] += value
        type_bucket["co2"] += co2

    return {
        "components_assessed": counted,
        "components_diverted_from_disposal": diverted,
        "diversion_rate_percent": round(100.0 * diverted / counted, 1) if counted else 0.0,
        "total_recovery_value": round(total_value, 2),
        "total_new_part_cost": round(total_new_cost, 2),
        "avoided_procurement_share_percent": (
            round(100.0 * total_value / total_new_cost, 1) if total_new_cost else 0.0
        ),
        "total_co2_avoided_kg": round(total_co2, 2),
        "total_co2_avoided_tonnes": round(total_co2 / 1000.0, 3),
        "by_disposition": {
            label: {
                "count": int(values["count"]),
                "value": round(values["value"], 2),
                "co2_kg": round(values["co2"], 2),
            }
            for label, values in by_disposition.items()
        },
        "by_component_type": {
            label: {
                "count": int(values["count"]),
                "value": round(values["value"], 2),
                "co2_kg": round(values["co2"], 2),
            }
            for label, values in sorted(
                by_type.items(), key=lambda item: item[1]["value"], reverse=True
            )
        },
        "currency": settings.IMPACT_CURRENCY,
        "currency_symbol": settings.IMPACT_CURRENCY_SYMBOL,
        "estimate_basis": PROTOTYPE_LABEL,
        "disclaimer": DISCLAIMER,
    }


def constants_snapshot() -> Dict[str, Any]:
    """Expose the configured constants so the UI can show its own assumptions."""
    return {
        "new_part_cost": settings.IMPACT_NEW_PART_COST,
        "component_mass_kg": settings.IMPACT_COMPONENT_MASS_KG,
        "co2_intensity_kg_per_kg": settings.IMPACT_CO2_PER_KG,
        "value_recovery_factor": settings.IMPACT_VALUE_RECOVERY_FACTOR,
        "co2_avoidance_factor": settings.IMPACT_CO2_AVOIDANCE_FACTOR,
        "currency": settings.IMPACT_CURRENCY,
        "estimate_basis": PROTOTYPE_LABEL,
        "disclaimer": DISCLAIMER,
    }


def supported_types() -> List[str]:
    return sorted(settings.IMPACT_NEW_PART_COST.keys())
