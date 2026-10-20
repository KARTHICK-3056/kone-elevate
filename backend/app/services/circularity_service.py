"""Material Circularity Indicator, and the narrow/slow/close breakdown.

Why this exists
---------------
Every impact figure this platform produced before now was rupees or
kilograms of CO2e. Neither is a circularity measure. A fleet can improve
both while becoming *less* circular - swap steel parts for lighter virgin
composites and carbon falls while material keeps going to landfill. For a
product whose entire pitch is a circular economy, that was a real gap: the
system measured the co-benefits of circularity and never circularity
itself.

The field's standard metric is the Ellen MacArthur Foundation's **Material
Circularity Indicator**, and its inputs are already in the P3 material-flow
ledger. This module is arithmetic over data we keep, not new
instrumentation.

The formula
-----------
For a component of mass ``M``::

    V   = M(1 - F_R - F_U)              virgin feedstock
    W_0 = M(1 - C_R - C_U)              unrecoverable waste at end of life
    W_F = M(1 - E_F) F_R / E_F          waste making the recycled feedstock
    W_C = M(1 - E_C) C_R                waste in the end-of-life recycling
    W   = W_0 + (W_F + W_C) / 2         total unrecoverable waste
    LFI = (V + W) / (2M + (W_F - W_C) / 2)      linear flow index
    X   = (L / L_av) * (U / U_av)               utility
    MCI = max(0, 1 - LFI * 0.9 / X)

MCI runs 0 (fully linear: virgin in, landfill out, short life) to 1 (fully
circular).

What this build can and cannot supply
-------------------------------------
* ``F_U`` - **real.** The ledger records whether an inflow was secondary,
  which is exactly "this component's material was already in use before" (the MCI's term).
* ``F_R`` - **always 0.** Nothing in this platform knows the recycled
  content of a *new* part; that is supplier data we have never had. This
  understates MCI for any part made from recycled stock, and every response
  says so rather than quietly assuming zero is the truth.
* ``C_U`` / ``C_R`` - **real once the part has left**, from the outflow
  route. For a component still in service there is no outflow yet, so the
  latest AI recommendation is used as the *projected* route and the result
  is labelled ``projected``, never mixed silently with measured ones.
* ``L`` - real (age since first installation; recording recovered parts as
  fitted never resets ``installation_date``).
* ``L_av`` - the per-type ``design_life_years`` already in
  ``app.ml.features``, which are documented placeholders, not KONE figures.
* ``U / U_av`` - **assumed 1.0.** Utility intensity would need duty data per
  functional unit against an industry baseline; neither exists here.

So an MCI from this module is a prototype estimate built on the same
estimated masses the E5 report already discloses. It is reported with its
own assumptions attached, in the same spirit as ``mass_source``.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.ml import r_ladder
from app.ml.features import reference_for
from app.models.component import Component
from app.models.material_flow import MaterialFlow
from app.services import material_flow_service
from app.utils.enums import (
    DIRECTED_TO_DISPOSAL,
    LifecycleStatus,
    MaterialFlowDirection,
    OutflowRoute,
    Recommendation,
)

#: EMF's constant in F(X) = 0.9 / X.
_UTILITY_CONSTANT = 0.9

#: How a recorded outflow route maps onto the MCI's two recovery fractions.
_ROUTE_TO_FRACTION: Dict[str, str] = {
    OutflowRoute.PREPARATION_FOR_REUSE.value: "C_U",
    OutflowRoute.RECYCLING.value: "C_R",
    OutflowRoute.OTHER_RECOVERY.value: "C_R",
}

#: How a *projected* category maps onto the same fractions, for a part still
#: in service. CONTINUE_USING keeps the component in use where it is (C_U);
#: MATERIAL_RECOVERY recovers the material (C_R); DISPOSE recovers nothing.
#: COMPONENT_RECOVERY is split - see :func:`_component_recovery_split`.
_RECOMMENDATION_TO_FRACTION: Dict[str, str] = {
    Recommendation.CONTINUE_USING.value: "C_U",
    Recommendation.MATERIAL_RECOVERY.value: "C_R",
}


def _component_recovery_split(component: Component) -> tuple[float, float]:
    """(C_U, C_R) for a component whose sub-components are to be recovered.

    Only the separable sub-components stay in use; the rest of the component
    goes to material recovery. The parts' mass share is taken from the
    recorded material grade's bill of materials. Without a recorded grade the
    parts are unknown, so none of the mass is credited as kept in use - the
    conservative reading - and it is all counted as material recovery if the
    material allows it.
    """
    from app.ml import decision_flow, life_model

    key, provenance = life_model.resolve_grade(
        component.component_type, component.material, component.material_grade
    )
    parts_share = 0.0
    if key is not None and provenance == "recorded":
        parts_share = sum(
            item["mass_fraction"]
            for item in life_model.MATERIAL_GRADES[component.component_type][key]["constituents"]
            if item.get("separable")
        )
    material = decision_flow.material_recoverability(
        component.component_type, component.material, component.material_grade
    )
    rest = 1.0 - parts_share
    return parts_share, rest if material["possible"] else 0.0

ASSUMPTIONS = {
    "recycled_feedstock_fraction_F_R": (
        "Always 0. Recycled content of a new part is supplier data this "
        "platform has never held, so MCI is understated for any component "
        "manufactured from recycled stock."
    ),
    "utility_intensity_U_over_U_av": (
        "Assumed 1.0. Duty per functional unit against an industry baseline "
        "is not captured, so utility is carried by lifetime alone."
    ),
    "average_lifetime_L_av": (
        "Per-type design_life_years from app.ml.features - documented "
        "placeholder design envelopes, not validated KONE service lives."
    ),
    "mass": (
        "Component mass is the same figure the E5 ledger uses, and carries "
        "the same mass_source caveat: almost all of it is a per-type "
        "estimate because no part has been weighed."
    ),
}

DISCLAIMER = (
    "Prototype estimate. Material Circularity Indicator computed per Ellen "
    "MacArthur Foundation methodology over estimated masses and placeholder "
    "design lifetimes, on a synthetic fleet. Not a validated circularity "
    "disclosure."
)


def _recovery_fractions(
    component: Component, outflow: Optional[MaterialFlow]
) -> tuple[float, float, str, Optional[str]]:
    """Return ``(C_U, C_R, basis, route)`` for a component.

    ``basis`` is ``"actual"`` when the component has genuinely left the
    boundary and the ledger recorded by which route, and ``"projected"``
    when the figure rests on the latest AI recommendation instead.
    """
    if outflow is not None and outflow.outflow_route:
        fraction = _ROUTE_TO_FRACTION.get(outflow.outflow_route)
        return (
            1.0 if fraction == "C_U" else 0.0,
            1.0 if fraction == "C_R" else 0.0,
            "actual",
            outflow.outflow_route,
        )

    recommendation = component.latest_recommendation
    if str(recommendation) == Recommendation.COMPONENT_RECOVERY.value:
        c_u, c_r = _component_recovery_split(component)
        return c_u, c_r, "projected", None
    fraction = _RECOMMENDATION_TO_FRACTION.get(str(recommendation))
    return (
        1.0 if fraction == "C_U" else 0.0,
        1.0 if fraction == "C_R" else 0.0,
        "projected",
        None,
    )


def _terminal_outflow(db: Session, component: Component) -> Optional[MaterialFlow]:
    """The ledger row for this component leaving the boundary for good.

    Only a component now sitting in a terminal or part-recovery state has
    actually left; an outflow row alone does not prove that.
    """
    if component.current_status not in {
        LifecycleStatus.MATERIAL_RECOVERED.value,
        LifecycleStatus.DISPOSED.value,
        LifecycleStatus.PART_RECOVERY.value,
    }:
        return None
    return (
        db.execute(
            select(MaterialFlow)
            .where(
                MaterialFlow.component_pk == component.id,
                MaterialFlow.direction == MaterialFlowDirection.OUTFLOW.value,
            )
            .order_by(MaterialFlow.flow_date.desc(), MaterialFlow.id.desc())
        )
        .scalars()
        .first()
    )


def component_mci(db: Session, component: Component) -> Dict[str, Any]:
    """Material Circularity Indicator for one component."""
    mass, mass_source = material_flow_service.resolve_mass(component)
    e_c = float(settings.MCI_RECYCLING_EFFICIENCY)
    e_f = float(settings.MCI_RECYCLED_FEEDSTOCK_EFFICIENCY)

    # Feedstock. F_R is structurally 0 here - see this module's docstring.
    f_r = 0.0
    f_u = 1.0 if component.life_cycle_number > 1 else 0.0

    outflow = _terminal_outflow(db, component)
    c_u, c_r, basis, route = _recovery_fractions(component, outflow)

    virgin = mass * (1.0 - f_r - f_u)
    w_0 = mass * (1.0 - c_r - c_u)
    w_f = mass * (1.0 - e_f) * f_r / e_f if e_f > 0 else 0.0
    w_c = mass * (1.0 - e_c) * c_r
    waste = w_0 + (w_f + w_c) / 2.0

    denominator = 2.0 * mass + (w_f - w_c) / 2.0
    linear_flow_index = (virgin + waste) / denominator if denominator > 0 else 1.0

    reference = reference_for(component.component_type)
    average_life = float(reference.get("design_life_years", 20) or 20)
    actual_life = float(component.component_age or 0.0)
    ratio = (actual_life / average_life) if average_life > 0 and actual_life > 0 else 1.0

    # The utility term penalises a component whose service was cut short -
    # scrapping a motor at year 8 of a 25-year design life wastes 17 years
    # of embodied material. That penalty is only correct once the service
    # has actually ended. A part whose sub-components were recovered has not
    # lost all those years; the recovered parts carry on. Applying the
    # penalty there too drove every component in the fleet to a clamped
    # zero and destroyed the ordering the indicator exists to express, so
    # the ratio is floored at 1.0 unless the material genuinely left for
    # material recovery or disposal.
    service_ended = component.current_status in {
        LifecycleStatus.MATERIAL_RECOVERED.value,
        LifecycleStatus.DISPOSED.value,
    }
    utility = ratio if service_ended else max(ratio, 1.0)

    mci = max(0.0, 1.0 - linear_flow_index * _UTILITY_CONSTANT / utility)

    return {
        "component_id": component.component_id,
        "component_type": component.component_type,
        "material": component.material,
        "mci": round(mci, 4),
        "basis": basis,
        "life_cycle_number": component.life_cycle_number,
        "mass_kg": round(mass, 3),
        "mass_source": mass_source,
        "inputs": {
            "F_R_recycled_feedstock": f_r,
            "F_U_reused_feedstock": f_u,
            "C_R_to_recycling": c_r,
            "C_U_to_reuse": c_u,
            "E_C_recycling_efficiency": e_c,
            "E_F_feedstock_efficiency": e_f,
            "L_actual_years": round(actual_life, 2),
            "L_av_years": average_life,
            "utility_X": round(utility, 4),
            "utility_penalty_applied": service_ended,
            "outflow_route": route,
        },
        "linear_flow_index": round(linear_flow_index, 4),
    }


def fleet_circularity(db: Session, country: Optional[str] = None) -> Dict[str, Any]:
    """Fleet-wide MCI plus the narrow / slow / close strategy breakdown.

    The three strategies are reported separately rather than rolled into one
    score because they are different levers with different owners, and
    because only two of them are measurable here - saying which is which is
    the point.
    """
    filters = [Component.country == country] if country is not None else []
    components = list(
        db.execute(select(Component).where(*filters)).scalars().all()
    )

    rows: List[Dict[str, Any]] = [component_mci(db, component) for component in components]
    total_mass = sum(row["mass_kg"] for row in rows)

    if rows and total_mass > 0:
        # Mass-weighted: a 260 kg motor's circularity matters more to the
        # fleet's material footprint than a 9 kg control board's.
        weighted = sum(row["mci"] * row["mass_kg"] for row in rows) / total_mass
    else:
        weighted = 0.0
    simple = sum(row["mci"] for row in rows) / len(rows) if rows else 0.0

    actual = [row for row in rows if row["basis"] == "actual"]
    projected = [row for row in rows if row["basis"] == "projected"]

    by_type: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        bucket = by_type.setdefault(
            row["component_type"], {"count": 0, "mass_kg": 0.0, "mci_sum": 0.0}
        )
        bucket["count"] += 1
        bucket["mass_kg"] += row["mass_kg"]
        bucket["mci_sum"] += row["mci"]

    return {
        "mci_mass_weighted": round(weighted, 4),
        "mci_unweighted_mean": round(simple, 4),
        "components_scored": len(rows),
        "total_mass_kg": round(total_mass, 2),
        "basis_split": {
            "actual": len(actual),
            "projected": len(projected),
            "note": (
                "'actual' components have genuinely left the boundary and the "
                "ledger recorded the route. 'projected' components are still in "
                "service, so the latest AI recommendation stands in for a route "
                "nobody has taken yet."
            ),
        },
        "by_component_type": {
            name: {
                "components": bucket["count"],
                "mass_kg": round(bucket["mass_kg"], 2),
                "mean_mci": round(bucket["mci_sum"] / bucket["count"], 4),
            }
            for name, bucket in sorted(
                by_type.items(), key=lambda item: item[1]["mass_kg"], reverse=True
            )
        },
        "strategies": _strategies(db, components, rows, filters),
        "r_ladder_distribution": _r_ladder_distribution(components),
        # Same evidence block the ESRS E5 and BRSR reports carry. An MCI is
        # computed from the material-flow ledger, so it is re-derivable from
        # the same audit range - and a circularity figure that cannot name
        # its evidence is a claim, not a disclosure.
        "derivation": _derivation(db),
        "assumptions": ASSUMPTIONS,
        "disclaimer": DISCLAIMER,
    }


def _derivation(db: Session) -> Dict[str, Any]:
    """The audit-chain range this figure was computed over."""
    from app.services.compliance_service import derivation_evidence  # noqa: PLC0415

    flows = list(db.execute(select(MaterialFlow)).scalars().all())
    evidence = derivation_evidence(db, flows)
    evidence["re_derivation_note"] = (
        "MCI is a function of the same ledger rows the E5 report totals, "
        "plus the per-type design lifetimes in app.ml.features and the "
        "efficiency constants in settings. Re-run fleet_circularity over "
        "the same audit range to reproduce it."
    )
    return evidence


def _r_ladder_distribution(components: List[Component]) -> Dict[str, Any]:
    """Where the fleet sits on the value-retention hierarchy.

    Uses each component's cached recommendation and health score rather than
    re-running inference over the whole fleet: this is a dashboard figure,
    and re-scoring every component to draw one chart is the kind of O(n)
    model call the P4 scale work removed everywhere else.
    """
    rungs: List[Optional[str]] = []
    for component in components:
        recommendation = component.latest_recommendation
        if not recommendation:
            rungs.append(None)
            continue
        placement = r_ladder.refine(
            recommendation,
            {
                "component_type": component.component_type,
                "component_age": component.component_age,
                "operating_hours": component.operating_hours,
                "load_cycles": component.load_cycles,
                "inspection_score": component.inspection_score,
                "repair_count": component.repair_count,
                "failure_history": component.failure_history,
            },
            float(component.health_score or 0.0),
        )
        rungs.append(placement["rung"])
    return r_ladder.distribution(rungs)


def _strategies(
    db: Session,
    components: List[Component],
    rows: List[Dict[str, Any]],
    filters: list,
) -> Dict[str, Any]:
    """Narrow, slow and close - the three circular-economy levers.

    Reported separately because a single score hides which one a fleet is
    actually pulling, and because 'narrow' is not measurable from anything
    this platform holds. Saying that plainly is better than inventing a
    number for it.
    """
    total = len(components)

    # --- slow: are components lasting, and coming back for another life? ---
    # life_cycle_number > 1 exists only in legacy records: a complete
    # component is no longer refitted, so new data never increments it.
    second_life = [c for c in components if c.life_cycle_number > 1]
    part_recovery = [
        c for c in components if c.current_status == LifecycleStatus.PART_RECOVERY.value
    ]
    life_ratios = [
        row["inputs"]["L_actual_years"] / row["inputs"]["L_av_years"]
        for row in rows
        if row["inputs"]["L_av_years"] > 0
    ]

    # --- close: where does the material actually go? -----------------------
    outflows = list(
        db.execute(
            select(MaterialFlow).where(
                MaterialFlow.direction == MaterialFlowDirection.OUTFLOW.value
            )
        )
        .scalars()
        .all()
    )
    out_mass = sum(flow.mass_kg for flow in outflows)
    disposed_mass = sum(
        flow.mass_kg for flow in outflows if flow.outflow_route in DIRECTED_TO_DISPOSAL
    )
    inflows = list(
        db.execute(
            select(MaterialFlow).where(
                MaterialFlow.direction == MaterialFlowDirection.INFLOW.value
            )
        )
        .scalars()
        .all()
    )
    in_mass = sum(flow.mass_kg for flow in inflows)
    secondary_mass = sum(flow.mass_kg for flow in inflows if flow.is_secondary)

    return {
        "narrow": {
            "measured": False,
            "note": (
                "Narrowing the loop - using less material per unit of service - "
                "is a design-stage decision. This platform sees components only "
                "once they are installed, so it holds no data on it and reports "
                "no figure rather than a misleading one."
            ),
        },
        "slow": {
            "measured": True,
            "components_on_second_or_later_life": len(second_life),
            "components_in_part_recovery": len(part_recovery),
            "second_life_share_percent": (
                round(100.0 * len(second_life) / total, 1) if total else 0.0
            ),
            "mean_life_achieved_vs_design_percent": (
                round(100.0 * sum(life_ratios) / len(life_ratios), 1) if life_ratios else 0.0
            ),
            "note": (
                "Slowing the loop is extending service life (Continue Using) and "
                "recovering usable sub-components for lower-demand applications "
                "(Component Recovery). The part-recovery count is components now "
                "being dismantled for their usable sub-components; the second-life count reflects "
                "legacy records only, as complete components are no longer refitted."
            ),
        },
        "close": {
            "measured": True,
            "outflow_mass_kg": round(out_mass, 2),
            "diverted_from_disposal_percent": (
                round(100.0 * (out_mass - disposed_mass) / out_mass, 1) if out_mass else 0.0
            ),
            "inflow_mass_kg": round(in_mass, 2),
            "secondary_inflow_share_percent": (
                round(100.0 * secondary_mass / in_mass, 1) if in_mass else 0.0
            ),
            "note": (
                "Closing the loop is material re-entering the fleet instead of "
                "being replaced by virgin stock. These are the same figures "
                "ESRS E5-4 and E5-5 disclose, expressed as circularity rather "
                "than as tonnage."
            ),
        },
    }
