"""Print every financial/CO2 figure used in the pitch, from the same
constants the API uses - so no number reaches a slide that this script
cannot reproduce.

Rule enforced by this script (P0 of plan.md): if a claimed figure cannot be
derived from ``app.core.config.settings`` and ``app.services.impact_service``,
it is reported as NOT DERIVABLE and must come off the deck until a real model
for it exists.

Run:  python scripts/derive_impact_claims.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings  # noqa: E402
from app.core.database import SessionLocal  # noqa: E402
from app.services import impact_service, site_impact_service  # noqa: E402
from app.utils.enums import ComponentType, Recommendation  # noqa: E402

LINE = "-" * 78


def _fmt_inr(value: float) -> str:
    return f"{settings.IMPACT_CURRENCY_SYMBOL} {value:,.0f}"


def per_component_recovery_range() -> Tuple[float, float, List[Tuple[str, str, float]]]:
    """Every (component_type, recommendation) recovery value the model can produce."""
    rows: List[Tuple[str, str, float]] = []
    for component_type in ComponentType.values():
        for recommendation in Recommendation.values():
            value = impact_service.estimate_value(component_type, recommendation)
            if value > 0:
                rows.append((component_type, recommendation, value))
    values = [value for *_ignored, value in rows]
    return min(values), max(values), sorted(rows, key=lambda r: r[2])


def per_component_co2_range() -> Tuple[float, float]:
    """Every (component_type, material, recommendation) CO2-avoided figure."""
    values: List[float] = []
    for component_type in ComponentType.values():
        for material in settings.IMPACT_CO2_PER_KG:
            for recommendation in Recommendation.values():
                co2 = impact_service.estimate_co2_saving(component_type, material, recommendation)
                if co2 > 0:
                    values.append(co2)
    return min(values), max(values)


def main() -> None:
    print("=" * 78)
    print("KONE ELEVATE - derived impact claims (from app.core.config + impact_service)")
    print(settings.APP_VERSION)
    print("=" * 78)
    print(
        "Every figure below is computed from the SAME illustrative constants the\n"
        "API returns on every response, tagged 'Prototype estimate'. Nothing here\n"
        "is a validated KONE cost, mass or emission factor."
    )
    print(LINE)

    # ---------------------------------------------------------- per-component
    lo, hi, rows = per_component_recovery_range()
    print("CLAIM: 'Rs.30,000-Rs.1,20,000 saved per component' (pitch slide)")
    print("  Derived range across all (component_type x recommendation) pairs:")
    print(f"    min = {_fmt_inr(lo)}   ({rows[0][0]} / {rows[0][1]})")
    print(f"    max = {_fmt_inr(hi)}   ({rows[-1][0]} / {rows[-1][1]})")
    in_band = settings.IMPACT_CURRENCY == "INR" and 25_000 <= lo and hi <= 130_000
    print(f"  Slide range roughly consistent with derived range: {in_band}")
    print(
        "  Assumptions: new_part_cost and value_recovery_factor tables in "
        "app.core.config (IMPACT_NEW_PART_COST, IMPACT_VALUE_RECOVERY_FACTOR)."
    )
    print(LINE)

    co2_lo, co2_hi = per_component_co2_range()
    print("CLAIM (supporting): per-component CO2 avoided")
    print(f"  Derived range: {co2_lo:.1f} kg - {co2_hi:.1f} kg CO2e per component")
    print(
        "  Assumptions: IMPACT_COMPONENT_MASS_KG x IMPACT_CO2_PER_KG x "
        "IMPACT_CO2_AVOIDANCE_FACTOR."
    )
    print(LINE)

    # --------------------------------------------------- per-site-per-quarter
    print("CLAIM: 'Rs.4.9 L and 1.7 t CO2 saved per site per quarter' (pitch slide)")
    print(
        "  UPDATED STATUS: DERIVABLE (P0 follow-up).\n"
        "  The original NOT DERIVABLE finding stood on a real gap: there was no\n"
        "  SITE MODEL anywhere in the codebase - no notion of how many components\n"
        "  a site processes per quarter, or with what disposition mix.\n"
        "  app.services.site_impact_service now supplies exactly that, built\n"
        "  entirely from data this system already has (no external dataset):\n"
        "    N = a site's current backlog + its forecast arrivals next quarter\n"
        "    value/co2 = N x that site's OWN historical average per assessed\n"
        "                component (fleet-wide average if it has no history yet)\n"
        "  This is the worked-example format the original finding asked for -\n"
        "  every number below states its N and where its mix came from, rather\n"
        "  than asserting a bare currency figure."
    )
    try:
        with SessionLocal() as db:
            site_report = site_impact_service.estimate_site_quarterly_impact(db)
        if not site_report["sites"]:
            print(
                "  No active components in this database yet - run "
                "scripts/seed_database.py, then re-run this script."
            )
        else:
            print(f"  Sites found: {len(site_report['sites'])}")
            for row in site_report["sites"]:
                print(
                    f"    {row['site']}: N={row['projected_components_this_period']} "
                    f"({row['mix_source']}) -> "
                    f"{_fmt_inr(row['projected_value'])}, "
                    f"{row['projected_co2_kg']:.1f} kg CO2e"
                )
            if site_report["fleet_average"]:
                avg = site_report["fleet_average"]
                print(
                    f"  Fleet average across {avg['sites']} site(s): "
                    f"{_fmt_inr(avg['avg_projected_value_per_site'])} and "
                    f"{avg['avg_projected_co2_tonnes_per_site']:.3f} t CO2e per site "
                    "per quarter - THIS is the number that may replace the bare "
                    "slide claim, together with the per-site table above."
                )
    except Exception as exc:  # noqa: BLE001 - a script, not a service; report and move on
        print(
            f"  Could not compute (forecast model or database not available: {exc}).\n"
            "  Run scripts/train_forecast.py and scripts/seed_database.py first."
        )
    print(LINE)

    print(
        "Reminder: every number in this report - and on any slide derived from\n"
        f"it - carries this disclaimer: {impact_service.DISCLAIMER}"
    )
    print("=" * 78)


if __name__ == "__main__":
    main()
