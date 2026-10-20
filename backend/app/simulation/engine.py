"""Month-by-month simulation of one traction lift: drivetrain and overspeed governor.

The user sets one thing - the average load the car carries per trip. Everything
else the models need (all 13 model parameters, for each of motor, steel rope,
sheave and overspeed governor) comes from, in priority order:

1. **The KONE API** (``reference.kone_record``). Month 0 starts from the
   reference lift's KONE record - service count, repairs, failures, days
   since the last visit and the condition code on departure - and every rate
   KONE publishes (trip duration, the default load, the service interval, the
   callout rate) drives the forward months. Where the KONE record is too
   thin to establish a rate it says so and the simulation's own figure is
   used.
2. **Simulation**, only for what KONE does not publish: vibration,
   temperature and a component's age, plus the forward evolution of every
   count after month 0.

Two layers, deliberately kept apart
-----------------------------------
**Physical truth.** Each component carries a hidden true wear state. It grows
each month by the same damage laws the life model documents - load stress
with each mechanism's exponent, heat, vibration, duty - plus a hidden
unit-to-unit variation and month-to-month scatter that no model is told
about. Real parts differ from their datasheet; so do these.

**What a technician observes.** Vibration, temperature and the inspection
score are only *read* at service visits, with measurement noise, exactly as
the published KONE API makes them available (i.e. not continuously). The life
model, the early-warning forecast and the AI classifier all work from these
observations, never from the true wear.

Closing the loop
----------------
At each service visit the estimate drives the maintenance decision: a part in
the replace band is replaced before it fails, and the removed part is given its
end-of-use category by the decision flow (component recovery, material recovery
or disposal). A part that reaches true end of life between visits breaks down
and is replaced reactively. A complete part is never restored and put back. The KPIs therefore
measure the pre-analysis itself: how many replacements were made *before* a
breakdown, and how many months of warning the forecast gave.

Load physics
------------
Per-trip load varies around the user's average (gamma-distributed, CV from the
reference). Each component feels the load differently:

* rope     - tension on the car side: car + load
* sheave   - both rope sides press on the grooves: car + load + counterweight
* governor - its rope is tensioned by its own pit weight, not by the car, so
             load reaches it only weakly through the moving mass it follows
             (the life model's governor exponent of 0.5 carries that weakness)
* motor    - torque follows the *imbalance* |load - balance| plus friction and
             acceleration of the whole moving mass. A half-full car is the
             motor's easiest trip; an empty car is nearly as hard as a full one.

Damage follows Miner's rule, so the equivalent load is (E[s^p])^(1/p) with the
mechanism's exponent p - a few heavy trips cost more than their average.

The state is plain JSON and the server keeps none of it: the client sends the
state back with each request. Nothing here touches the database or the real
fleet.
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from scipy.stats import gamma

from app.integrations.kone_features import APPORTIONMENT
from app.ml import early_warning, life_model
from app.ml.features import FEATURE_COLUMNS, build_frame, reference_for
from app.simulation import reference as ref
from app.utils.enums import ComponentType, Recommendation, is_safety_critical
from app.utils.helpers import utcnow

STATE_VERSION = 2
DAYS_PER_MONTH = 30.4375
MAX_MONTHS_PER_CALL = 24
MAX_EVENTS = 150
MAX_SIMULATED_MONTHS = 12 * 60

#: The four focus components and their primary material. A simulated part has
#: no recorded material grade, so none is given: the life model then assumes
#: the industry-standard grade for the material (the shortest-lived where there
#: is a choice) and labels it as assumed. A part started from a real component
#: keeps its own recorded grade.
COMPONENTS: Dict[str, Tuple[str, Optional[str]]] = {
    ComponentType.MOTOR.value: ("Steel", None),
    ComponentType.STEEL_ROPE.value: ("Steel", None),
    ComponentType.SHEAVE.value: ("Cast Iron", None),
    ComponentType.GOVERNOR.value: ("Cast Iron", None),
}

#: Hidden unit-to-unit variation in true life (lognormal sigma) and monthly
#: scatter. Neither is visible to any model - which is why estimates differ
#: from the truth, as they would on a real lift.
UNIT_VARIATION_SIGMA = 0.12
MONTHLY_SCATTER_SIGMA = 0.15

#: Readings are observed with this measurement noise.
VIBRATION_NOISE = 0.05  # relative
TEMPERATURE_NOISE_C = 1.5
INSPECTION_NOISE = 3.0

#: New-condition vibration as a share of the type limit, and how it grows
#: with wear: at end of life it sits close to the limit.
VIBRATION_NEW_FRACTION = 0.28
VIBRATION_WEAR_GAIN = 2.2

#: Random fault hazard per month: a small base rate, rising steeply once a
#: part is past 60% of its life.
FAULT_BASE_RATE = 0.003
FAULT_WEAR_RATE = 0.05

#: Share of motor losses that do not depend on load (iron losses, fan).
MOTOR_FIXED_LOSS_SHARE = 0.7

#: Wear restored by a minor callout repair (an adjustment, not a restoration).
CALLOUT_RESTORES = 0.02

_QUANTILES = (np.arange(64) + 0.5) / 64.0


# --------------------------------------------------------------------------
# Load physics
# --------------------------------------------------------------------------
def trip_loads(mean_kg: float, cv: float) -> np.ndarray:
    """64 representative per-trip loads with the given mean (deterministic quantiles)."""
    if mean_kg <= 0:
        return np.zeros_like(_QUANTILES)
    shape = 1.0 / (cv * cv)
    loads = gamma.ppf(_QUANTILES, a=shape, scale=mean_kg / shape)
    return np.clip(loads, 0.0, ref.MAX_LOAD_KG)


def _moving_mass(loads: np.ndarray) -> np.ndarray:
    return ref.CAR_MASS_KG + loads + ref.COUNTERWEIGHT_KG


def stress(component_type: str, loads: np.ndarray) -> np.ndarray:
    """Relative mechanical stress on a component for each trip load."""
    if component_type == ComponentType.STEEL_ROPE.value:
        return ref.CAR_MASS_KG + loads
    if component_type == ComponentType.MOTOR.value:
        imbalance = np.abs(loads - ref.COUNTERWEIGHT_BALANCE * ref.RATED_LOAD_KG)
        return imbalance + 0.075 * _moving_mass(loads)
    return _moving_mass(loads)  # sheave, governor


def equivalent_ratio(component_type: str, mean_kg: float, reference_kg: float, cv: float) -> float:
    """Miner-equivalent stress at this load relative to the reference load."""
    p = life_model.MECHANISMS[component_type]["load_exponent"]
    here = np.mean(stress(component_type, trip_loads(mean_kg, cv)) ** p) ** (1.0 / p)
    base = np.mean(stress(component_type, trip_loads(reference_kg, cv)) ** p) ** (1.0 / p)
    return float(here / base)


def _thermal_ratio(component_type: str, mean_kg: float, reference_kg: float, cv: float) -> float:
    """Heat input relative to the reference load.

    Motor copper losses scale with torque squared (I^2 R); other parts with the
    moving mass. Only the motor's temperature follows it (``true_temperature``).
    """
    here, base = trip_loads(mean_kg, cv), trip_loads(reference_kg, cv)
    if component_type == ComponentType.MOTOR.value:
        return float(np.mean(stress(component_type, here) ** 2) / np.mean(stress(component_type, base) ** 2))
    return float(np.mean(_moving_mass(here)) / np.mean(_moving_mass(base)))


def _ambient(month: int) -> float:
    return ref.AMBIENT_C + ref.AMBIENT_SWING_C * math.sin(2 * math.pi * month / 12.0)


def true_temperature(component_type: str, thermal_ratio: float, wear: float, month: int) -> float:
    """Housing temperature: at the reference load a heat-sensitive part runs
    10 K under its limit (the life model's nominal point)."""
    ambient = _ambient(month)
    limit = reference_for(component_type)["temp_limit"]
    if component_type == ComponentType.MOTOR.value:
        # Only copper losses follow load; iron losses and the cooling fan
        # (MOTOR_FIXED_LOSS_SHARE) do not. Sized so full rated load runs the
        # housing near, not far past, its limit - as a correctly sized
        # traction motor does.
        heat = MOTOR_FIXED_LOSS_SHARE + (1.0 - MOTOR_FIXED_LOSS_SHARE) * thermal_ratio
        return ambient + (limit - 10 - ref.AMBIENT_C) * heat + 8.0 * wear
    return ambient + 3.0


def true_vibration(component_type: str, ratio: float, wear: float) -> float:
    limit = reference_for(component_type)["vibration_limit"]
    return (
        VIBRATION_NEW_FRACTION * limit
        * (1.0 + VIBRATION_WEAR_GAIN * max(wear, 0.0) ** 1.4)
        * (0.9 + 0.1 * ratio)
    )


# --------------------------------------------------------------------------
# State
# --------------------------------------------------------------------------
def _rng(state: Dict[str, Any], *keys: int) -> np.random.Generator:
    return np.random.default_rng([int(state["seed"]), *[int(k) for k in keys]])


def _date(state: Dict[str, Any], month: float) -> date:
    return date.fromisoformat(state["start_date"]) + timedelta(days=round(month * DAYS_PER_MONTH))


def _new_component(
    state: Dict[str, Any],
    index: int,
    component_type: str,
    life_number: int,
    month: int,
    material: Optional[str] = None,
    grade: Optional[str] = None,
) -> Dict[str, Any]:
    default_material, default_grade = COMPONENTS[component_type]
    material = material or default_material
    grade = grade or (default_grade if material == default_material else None)
    variation = float(np.exp(_rng(state, index, life_number, 991).normal(0.0, UNIT_VARIATION_SIGMA)))
    return {
        "component_type": component_type,
        "material": material,
        "material_grade": grade,
        "life_number": life_number,
        "installed_month": month,
        "wear": 0.0,
        "unit_variation": variation,
        "load_cycles": 0.0,
        "operating_hours": 0.0,
        "stress_moment": 0.0,  # sum over trips of the Miner-equivalent stress ratio^p
        "trips": 0.0,
        "service_count": 0,
        "repair_count": 0,
        "failure_history": 0,
        "last_service_month": month,
        "readings": [],
        "warned_month": None,
        "warned_issue": None,
        "ai": None,
    }


def new_state(seed: int = 7, start: Optional[date] = None, from_kone: bool = True) -> Dict[str, Any]:
    """The reference lift with all four components, starting from its KONE record.

    With ``from_kone`` the service count, repairs, failures, days since the
    last visit and the condition score start from the reference lift's KONE
    record (lift-level, as ``kone_features`` maps them). KONE publishes no
    installation date, so the parts' age starts at zero and is simulated.
    """
    state: Dict[str, Any] = {
        "version": STATE_VERSION,
        "seed": int(seed),
        "start_date": (start or utcnow().date()).isoformat(),
        "month": 0,
        "load_kg": None,
        #: Set when the simulation was started from a real component - see
        #: :func:`state_from_component`.
        "focus": None,
        "focus_series": [],
        "components": {},
        "events": [],
        "kpis": {
            "proactive_replacements": 0,
            "breakdowns": 0,
            "to_component_recovery": 0,
            "to_material_recovery": 0,
            "to_dispose": 0,
            "callouts": 0,
            "warnings_raised": 0,
            "warning_lead_months": [],
        },
    }
    for index, component_type in enumerate(COMPONENTS):
        state["components"][component_type] = _new_component(state, index, component_type, 1, 0)
    state["kone_start"] = None
    if from_kone:
        _apply_kone_start(state, ref.reference_values()["kone_start"])
    return state


def _apply_kone_start(state: Dict[str, Any], start: Dict[str, Any]) -> None:
    """Begin month 0 from the KONE record wherever KONE provides the value."""
    applied = {name: value for name, value in (start or {}).items() if value is not None}
    for component in state["components"].values():
        for name in ("service_count", "repair_count", "failure_history"):
            if name in applied:
                component[name] = int(applied[name])
        if "days_since_last_service" in applied:
            component["last_service_month"] = -round(float(applied["days_since_last_service"]) / DAYS_PER_MONTH, 3)
        if "inspection_score" in applied:
            component["start_inspection_score"] = float(applied["inspection_score"])
    state["kone_start"] = applied


def validate_state(state: Dict[str, Any]) -> Dict[str, Any]:
    """Reject anything that is not a state this engine produced."""
    try:
        if state.get("version") != STATE_VERSION:
            raise ValueError("Unsupported simulation state version.")
        if set(state["components"]) != set(COMPONENTS):
            raise ValueError("Simulation state must contain exactly the four focus components.")
        month = int(state["month"])
        if not 0 <= month <= MAX_SIMULATED_MONTHS:
            raise ValueError(f"Simulation is limited to {MAX_SIMULATED_MONTHS // 12} years.")
        date.fromisoformat(state["start_date"])
        for component in state["components"].values():
            float(component["wear"])
            component["readings"] = list(component["readings"])[-early_warning.MAX_TREND_POINTS:]
        state["events"] = list(state["events"])[-MAX_EVENTS:]
        state["focus_series"] = list(state.get("focus_series") or [])[-MAX_SIMULATED_MONTHS:]
        focus = state.get("focus")
        if focus is not None and focus.get("component_type") not in COMPONENTS:
            raise ValueError("Simulation focus must be one of the four focus components.")
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError(f"Malformed simulation state: {exc}") from exc
    return state


# --------------------------------------------------------------------------
# The 13 model parameters, as a technician's records would show them
# --------------------------------------------------------------------------
def parameters(state: Dict[str, Any], component: Dict[str, Any]) -> Dict[str, Any]:
    """The component's model inputs, from *observed* data only."""
    component_type = component["component_type"]
    month = state["month"]
    age_months = month - component["installed_month"]
    latest = component["readings"][-1] if component["readings"] else None
    p = life_model.MECHANISMS[component_type]["load_exponent"]
    if component["trips"] > 0:
        equivalent = (component["stress_moment"] / component["trips"]) ** (1.0 / p)
    else:
        equivalent = 1.0
    rated = reference_for(component_type)["rated_load"]
    installed = _date(state, component["installed_month"])
    last_service = _date(state, component["last_service_month"])
    today = _date(state, month)
    limit = reference_for(component_type)

    return {
        "component_type": component_type,
        "material": component["material"],
        "material_grade": component["material_grade"],
        "installation_date": installed,
        "component_age": round(age_months / 12.0, 3),
        "operating_hours": round(component["operating_hours"], 1),
        "load_cycles": int(component["load_cycles"]),
        "average_load": round(life_model.reference_utilisation(component_type) * equivalent * rated, 1),
        # Until the first service visit nothing has been measured: the part
        # is new and its readings are its new-condition values.
        "vibration": latest["vibration"] if latest else round(VIBRATION_NEW_FRACTION * limit["vibration_limit"], 3),
        "temperature": latest["temperature"] if latest else round(_ambient(component["installed_month"]) + 5.0, 1),
        "service_count": component["service_count"],
        "repair_count": component["repair_count"],
        "failure_history": component["failure_history"],
        # Before the first simulated visit: the KONE condition score when the
        # run started from the KONE record, otherwise a new part's 100.
        "inspection_score": latest["inspection_score"] if latest else float(component.get("start_inspection_score", 100.0)),
        "days_since_last_service": max(0, (today - last_service).days),
        "last_service_date": last_service,
    }


def _events_for_forecast(state: Dict[str, Any], component: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [
        {
            "event_date": _date(state, reading["month"]),
            "vibration": reading["vibration"],
            "temperature": reading["temperature"],
            "inspection_score": reading["inspection_score"],
        }
        for reading in component["readings"]
    ]


def _log(state: Dict[str, Any], component_type: Optional[str], kind: str, message: str) -> None:
    state["events"].append(
        {
            "month": state["month"],
            "date": _date(state, state["month"]).isoformat(),
            "component": component_type,
            "kind": kind,
            "message": message,
        }
    )
    state["events"] = state["events"][-MAX_EVENTS:]


# --------------------------------------------------------------------------
# One month
# --------------------------------------------------------------------------
def _true_rate(
    state: Dict[str, Any], component: Dict[str, Any], ratio: float, temperature: float, vibration: float
) -> Tuple[float, float]:
    """Design-years of life consumed per calendar year, from the true state.

    Uses the life model's own damage law on noise-free inputs, so the truth
    and the estimate share physics - and differ only through what the
    estimate cannot see (unit variation, scatter, measurement noise, the
    gap between service visits).
    """
    component_type = component["component_type"]
    rated = reference_for(component_type)["rated_load"]
    truth = {
        **parameters(state, component),
        "average_load": life_model.reference_utilisation(component_type) * ratio * rated,
        "temperature": temperature,
        "vibration": vibration,
        "inspection_score": 100.0,
        "days_since_last_service": 0,
    }
    assessment = life_model.assess(truth, today=_date(state, state["month"]))
    return float(assessment["ageing_rate"]), float(assessment["design_life_years"])


def _replace(state: Dict[str, Any], component_type: str, reason: str, proactive: bool) -> None:
    index = list(COMPONENTS).index(component_type)
    old = state["components"][component_type]
    kpis = state["kpis"]
    if proactive:
        kpis["proactive_replacements"] += 1
    else:
        kpis["breakdowns"] += 1
    lead = None
    if old.get("warned_month") is not None:
        lead = state["month"] - old["warned_month"]
        kpis["warning_lead_months"].append(lead)
    warned_text = (
        f" First predicted {lead} months earlier ({old.get('warned_issue')})."
        if lead is not None
        else " No early warning had been raised."
    )
    category = _removed_part_category(state, old)
    kpis[{
        Recommendation.COMPONENT_RECOVERY.value: "to_component_recovery",
        Recommendation.MATERIAL_RECOVERY.value: "to_material_recovery",
    }.get(category["recommendation"], "to_dispose")] += 1
    _log(
        state,
        component_type,
        "replace_proactive" if proactive else "breakdown",
        f"{reason} Replaced (life {old['life_number']} ended at true wear {old['wear']:.0%}).{warned_text} "
        f"Removed part: {category['label']} - {category['text']}",
    )
    # The replacement is the same specification as the part it replaces.
    state["components"][component_type] = _new_component(
        state, index, component_type, old["life_number"] + 1, state["month"],
        material=old.get("material"), grade=old.get("material_grade"),
    )


def _removed_part_category(state: Dict[str, Any], component: Dict[str, Any]) -> Dict[str, Any]:
    """End-of-use category of a part taken out of service, via the decision flow.

    A replaced part is by definition no longer suitable for its application,
    so the flow starts at gate 2. The classifier's last probabilities are the
    serviceability evidence when available; otherwise its life position is.
    """
    from app.ml import decision_flow

    observed = parameters(state, component)
    ai = component.get("ai") or {}
    probabilities = dict(ai.get("probabilities") or {})
    if not probabilities:
        consumed = life_model.assess(observed, today=_date(state, state["month"]))["life_consumed"]["governing"]
        still_serviceable = 1.0 if consumed < life_model.REPLACE_LIMIT else 0.0
        probabilities = {
            Recommendation.COMPONENT_RECOVERY.value: still_serviceable,
            Recommendation.MATERIAL_RECOVERY.value: 1.0 - still_serviceable,
        }
    # Not suitable for its application any more: rule out gate 1.
    probabilities[Recommendation.CONTINUE_USING.value] = 0.0
    return decision_flow.decide(
        probabilities,
        component["component_type"],
        component["material"],
        inspection_score=observed["inspection_score"],
        grade=component.get("material_grade"),
    )


def _service_visit(state: Dict[str, Any], index: int, component: Dict[str, Any], vibration: float, temperature: float) -> None:
    """Record observed readings, then act on the forecast."""
    component_type = component["component_type"]
    noise = _rng(state, state["month"], index, 7)
    reading = {
        "month": state["month"],
        "vibration": round(max(0.05, vibration * float(np.exp(noise.normal(0, VIBRATION_NOISE)))), 3),
        "temperature": round(temperature + float(noise.normal(0, TEMPERATURE_NOISE_C)), 1),
        "inspection_score": round(
            float(np.clip(100.0 - 65.0 * component["wear"] + noise.normal(0, INSPECTION_NOISE), 0, 100)), 1
        ),
    }
    component["readings"] = (component["readings"] + [reading])[-early_warning.MAX_TREND_POINTS:]
    component["service_count"] += 1
    component["last_service_month"] = state["month"]

    observed = parameters(state, component)
    today = _date(state, state["month"])
    estimate = life_model.assess(observed, today=today)
    consumed = estimate["life_consumed"]["governing"]
    forecast = early_warning.forecast(
        observed,
        _events_for_forecast(state, component),
        latest_recommendation=(component.get("ai") or {}).get("recommendation"),
        today=today,
    )

    # Pre-analysis: note the first time the forecast flags this life.
    if component["warned_month"] is None:
        flagged = [
            issue for issue in forecast.get("issues", [])
            if issue["present"] or issue["urgency"] in {"ACT_NOW", "WITHIN_A_YEAR"}
        ]
        if flagged:
            first = flagged[0]
            component["warned_month"] = state["month"]
            component["warned_issue"] = first["title"]
            state["kpis"]["warnings_raised"] += 1
            _log(
                state, component_type, "warning",
                f"Early warning: {first['title']} "
                + ("- limit already crossed." if first["present"] else f"expected {first['predicted_date']}, act by {first['act_by']}.")
                + f" ({first['confidence_label']} confidence)",
            )

    # The measure the prediction calls for. Below the replace band the part is
    # still suitable for its application and simply continues in service.
    if consumed >= life_model.REPLACE_LIMIT:
        _replace(
            state, component_type,
            f"Service visit: estimate {consumed:.0%} of life used (replace band).", proactive=True,
        )


def _step(state: Dict[str, Any], load_kg: float, values: Dict[str, float]) -> List[int]:
    """Advance one month. Returns the indices of components serviced."""
    state["month"] += 1
    month = state["month"]
    trips = values["trips_per_day"] * DAYS_PER_MONTH
    serviced: List[int] = []

    for index, component_type in enumerate(COMPONENTS):
        component = state["components"][component_type]
        share = APPORTIONMENT[component_type]
        ratio = equivalent_ratio(component_type, load_kg, values["reference_load_kg"], values["load_spread_cv"])
        p = life_model.MECHANISMS[component_type]["load_exponent"]

        component["load_cycles"] += trips * float(share["cycles"])
        component["operating_hours"] += trips * values["trip_duration_s"] / 3600.0 * float(share["hours"])
        component["stress_moment"] += (ratio ** p) * trips
        component["trips"] += trips

        thermal = _thermal_ratio(component_type, load_kg, values["reference_load_kg"], values["load_spread_cv"])
        # A part started from a real record carries its own calibration: the
        # simulated physics is anchored to what this unit actually read.
        temperature = true_temperature(component_type, thermal, component["wear"], month) + float(
            component.get("temperature_offset", 0.0)
        )
        vibration = true_vibration(component_type, ratio, component["wear"]) * float(
            component.get("vibration_scale", 1.0)
        )

        rate, design_life = _true_rate(state, component, ratio, temperature, vibration)
        scatter = float(np.exp(_rng(state, month, index, 1).normal(0.0, MONTHLY_SCATTER_SIGMA)))
        component["wear"] += rate / (design_life * 12.0) * component["unit_variation"] * scatter
        component["true_vibration"] = round(vibration, 3)
        component["true_temperature"] = round(temperature, 1)

        # Unplanned events.
        if component["wear"] >= life_model.END_OF_LIFE:
            component["failure_history"] += 1
            _replace(state, component_type, "Breakdown between service visits: part reached end of life.", proactive=False)
            continue
        # KONE first: the lift's observed callout rate, shared across the four
        # focus parts, when the KONE record is long enough to give one.
        kone_rate = values.get("callout_rate_per_month")
        base_rate = kone_rate / len(COMPONENTS) if kone_rate is not None else FAULT_BASE_RATE
        hazard = base_rate + FAULT_WEAR_RATE * max(0.0, component["wear"] - 0.6) ** 1.5
        if _rng(state, month, index, 2).random() < hazard:
            component["failure_history"] += 1
            component["repair_count"] += 1
            component["wear"] = max(0.0, component["wear"] - CALLOUT_RESTORES)
            state["kpis"]["callouts"] += 1
            _log(state, component_type, "callout", "Callout: fault reported and repaired.")

        if month - component["last_service_month"] >= values["service_interval_months"]:
            _service_visit(state, index, component, vibration, temperature)
            serviced.append(index)
    return serviced


# --------------------------------------------------------------------------
# AI classifier, batched at service visits
# --------------------------------------------------------------------------
def _ai_assess(state: Dict[str, Any]) -> None:
    """Score all four components in one batch with the trained classifier."""
    from app.ml import abstention
    from app.ml.model_registry import registry

    if not registry.is_available:
        return
    bundle = registry.bundle
    rows = [
        {name: parameters(state, component).get(name) for name in FEATURE_COLUMNS}
        for component in state["components"].values()
    ]
    probabilities = bundle["pipeline"].predict_proba(build_frame(rows))
    classes = [str(label) for label in bundle["classes"]]
    for component, row in zip(state["components"].values(), probabilities, strict=True):
        scores = {label: round(float(value), 4) for label, value in zip(classes, row, strict=True)}
        best = max(scores, key=scores.get)
        decision = abstention.decide(scores, registry.conformal_q_hat)
        component["ai"] = {
            "recommendation": Recommendation.DEFER_TO_INSPECTION.value if decision["abstain"] else best,
            "underlying": best,
            "confidence": scores[best],
            "probabilities": scores,
            "month": state["month"],
            "model_version": str(bundle.get("model_version")),
        }


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------
def advance(state: Optional[Dict[str, Any]], load_kg: float, months: int) -> Dict[str, Any]:
    """Run ``months`` months at ``load_kg`` and return the new state plus results."""
    if not 0 <= load_kg <= ref.MAX_LOAD_KG:
        raise ValueError(f"Load must be between 0 and {ref.MAX_LOAD_KG:.0f} kg (110% of rated).")
    if not 1 <= months <= MAX_MONTHS_PER_CALL:
        raise ValueError(f"Advance between 1 and {MAX_MONTHS_PER_CALL} months at a time.")

    state = validate_state(state) if state else new_state()
    if state["month"] + months > MAX_SIMULATED_MONTHS:
        raise ValueError(f"Simulation is limited to {MAX_SIMULATED_MONTHS // 12} years - reset to continue.")
    values = ref.reference_values()
    first_event = len(state["events"])

    if state.get("load_kg") is None or abs(float(state["load_kg"]) - load_kg) > 1e-6:
        _log(state, None, "load", f"Average load set to {load_kg:.0f} kg (~{load_kg / ref.KG_PER_PERSON:.1f} persons per trip).")
        state["load_kg"] = load_kg

    series: List[Dict[str, Any]] = []
    serviced_any = state["month"] == 0
    for _ in range(months):
        serviced_any = bool(_step(state, load_kg, values)) or serviced_any
        series.append(_series_point(state, load_kg))

    if serviced_any or any(c.get("ai") is None for c in state["components"].values()):
        _ai_assess(state)

    new_events = state["events"][first_event:] if first_event < len(state["events"]) else []
    return {
        "state": state,
        "series": series,
        "results": results(state),
        "new_events": new_events,
        "api_source": values["api_source"],
    }


def _series_point(state: Dict[str, Any], load_kg: float) -> Dict[str, Any]:
    today = _date(state, state["month"])
    point: Dict[str, Any] = {"month": state["month"], "date": today.isoformat(), "load_kg": load_kg}
    for component_type, component in state["components"].items():
        estimate = life_model.assess(parameters(state, component), today=today)
        point[component_type] = {
            "true_wear": round(component["wear"], 4),
            "estimated": round(estimate["life_consumed"]["governing"], 4),
            "life_number": component["life_number"],
        }
    focus = state.get("focus")
    if focus:
        # Kept in the state (not only returned) so a saved scenario is built
        # from the server's own record of the run, not from the client's chart.
        state["focus_series"].append(
            {"month": state["month"], "load_kg": load_kg, **point[focus["component_type"]]}
        )
        state["focus_series"] = state["focus_series"][-MAX_SIMULATED_MONTHS:]
    return point


def results(state: Dict[str, Any]) -> Dict[str, Any]:
    """What the page shows: the 13 parameters and every model's view of them."""
    today = _date(state, state["month"])
    load = state.get("load_kg") or 0.0
    values = ref.reference_values()
    out: Dict[str, Any] = {
        "month": state["month"],
        "date": today.isoformat(),
        "years": round(state["month"] / 12.0, 2),
        "load_kg": load,
        "persons": round(load / ref.KG_PER_PERSON, 1),
        "kpis": _kpi_summary(state["kpis"]),
        "focus": state.get("focus"),
        "components": {},
    }
    for component_type, component in state["components"].items():
        observed = parameters(state, component)
        assessment = life_model.assess(observed, today=today)
        forecast = early_warning.forecast(
            observed,
            _events_for_forecast(state, component),
            latest_recommendation=(component.get("ai") or {}).get("recommendation"),
            today=today,
        )
        ratio = equivalent_ratio(component_type, load, values["reference_load_kg"], values["load_spread_cv"])
        out["components"][component_type] = {
            "parameters": {
                **{k: v for k, v in observed.items() if k in FEATURE_COLUMNS},
            },
            "life": life_model.projection_summary(assessment),
            "factors": [
                {"label": f["label"], "multiplier": f["multiplier"]} for f in assessment.get("factors", [])
            ],
            "early_warning": forecast,
            "ai": component.get("ai"),
            "truth": {
                "wear": round(component["wear"], 4),
                "vibration": component.get("true_vibration"),
                "temperature": component.get("true_temperature"),
                "life_number": component["life_number"],
                "load_stress_ratio": round(ratio, 3),
                "vibration_limit": reference_for(component_type)["vibration_limit"],
                "temperature_limit": reference_for(component_type)["temp_limit"],
            },
            "safety_critical": is_safety_critical(component_type),
        }
    return out


def _kpi_summary(kpis: Dict[str, Any]) -> Dict[str, Any]:
    leads = kpis.get("warning_lead_months") or []
    replaced = kpis["proactive_replacements"] + kpis["breakdowns"]
    return {
        **{k: v for k, v in kpis.items() if k != "warning_lead_months"},
        "average_warning_lead_months": round(sum(leads) / len(leads), 1) if leads else None,
        "prevented_share": round(kpis["proactive_replacements"] / replaced, 3) if replaced else None,
    }


def parameter_basis() -> Dict[str, Dict[str, Any]]:
    """How each of the 13 parameters is produced - shown on the page.

    ``source`` is where the value comes from first (``kone_api`` wherever the
    KONE API publishes it); ``then``, when present, is what carries it
    forward after month 0.
    """
    values = ref.reference_values()
    start = values.get("kone_start") or {}
    interval = values["service_interval_months"]
    interval_source = "kone_api" if ref.kone_record()["rates"]["service_interval_months"] else "assumption"
    faults_from_kone = values.get("callout_rate_per_month") is not None

    def from_kone(name: str, how: str, then: str, fallback_how: str) -> Dict[str, Any]:
        if start.get(name) is not None:
            return {"source": "kone_api", "then": then, "how": how}
        return {"source": "simulated", "how": fallback_how}

    return {
        "component_type": {"source": "assumption", "how": "The four focus components of the reference lift: motor, steel ropes, sheave and overspeed governor."},
        "material": {"source": "assumption", "how": "Reference material per component; the KONE API publishes no material (see material grade)."},
        "component_age": {"source": "simulated", "how": "Not in the KONE API (no installation date is published): simulated months since this part was installed (resets on replacement)."},
        "operating_hours": {"source": "kone_api", "how": "KONE movement durationSeconds per journey x the component's running-time share, at ISO 25745-2 trips/day (the KONE movement feed gives no journey count over time, so the trip rate is the standard's)."},
        "load_cycles": {"source": "kone_api", "how": "One cycle per KONE movement journey (RUN_COMPLETED) x the component's actuations per journey, at ISO 25745-2 trips/day (the KONE movement feed gives no journey count over time, so the trip rate is the standard's)."},
        "average_load": {"source": "kone_api", "input_source": "input", "how": "KONE movement loadPercentage x rated load is the default load; if you change the load, your value is used instead. Spread over trips and turned into each component's Miner-equivalent stress on its own rating scale."},
        "vibration": {"source": "simulated", "how": "Not in the KONE API: new-condition level rising with true wear and load, read at service visits with measurement noise."},
        "temperature": {"source": "simulated", "how": "Not in the KONE API: machine-room ambient (seasonal) + heat from load + wear, read at service visits."},
        "service_count": from_kone(
            "service_count",
            f"Starts at the reference lift's {start.get('service_count')} KONE service orders; then a visit every {interval:g} months ({'from KONE' if interval_source == 'kone_api' else 'assumption - too few KONE preventive visits to derive one'}).",
            interval_source,
            f"Preventive visits every {interval:g} months since installation.",
        ),
        "repair_count": from_kone(
            "repair_count",
            f"Starts at the reference lift's {start.get('repair_count')} KONE repair/callout orders; then callouts {'at the KONE-observed rate' if faults_from_kone else 'from the simulated fault model (KONE record too short for a rate)'}.",
            "kone_api" if faults_from_kone else "simulated",
            "Callout repairs (adjustments) recorded at simulated faults.",
        ),
        "failure_history": from_kone(
            "failure_history",
            f"Starts at the reference lift's {start.get('failure_history')} KONE orders with a failure reason or entrapment; then simulated faults and breakdowns.",
            "simulated",
            "Random faults whose hazard rises steeply after 60% of true life, plus breakdowns.",
        ),
        "inspection_score": from_kone(
            "inspection_score",
            f"Starts at {start.get('inspection_score')} - the KONE condition code on departure (lift-level); then graded at each simulated visit from true wear, with grading noise.",
            "simulated",
            "100 - 65 x true wear, as a technician would grade it, with grading noise.",
        ),
        "days_since_last_service": from_kone(
            "days_since_last_service",
            f"Starts at {start.get('days_since_last_service')} days since the last KONE service order; then days since the last simulated visit.",
            "simulated",
            "Days since the last simulated visit.",
        ),
    }


# --------------------------------------------------------------------------
# Starting from a real component
# --------------------------------------------------------------------------
def implied_load_kg(component_type: str, average_load: float) -> Dict[str, Any]:
    """The average car load that would put this component's recorded
    equivalent load on it, found by search over the lift's load range.

    The motor's stress is U-shaped in load (lowest near the counterweight
    balance), so two loads can explain the same record; the one nearer the
    reference load is taken, and the other is reported.
    """
    values = ref.reference_values()
    rated = reference_for(component_type)["rated_load"]
    target = average_load / (life_model.reference_utilisation(component_type) * rated) if average_load > 0 else 1.0
    grid = np.arange(0.0, ref.MAX_LOAD_KG + 1.0, 10.0)
    ratios = np.array(
        [equivalent_ratio(component_type, kg, values["reference_load_kg"], values["load_spread_cv"]) for kg in grid]
    )
    gap = np.abs(ratios - target)
    close = np.where(gap <= gap.min() + 0.01)[0]
    best = int(min(close, key=lambda i: abs(grid[i] - values["reference_load_kg"])))
    within_range = bool(gap[best] <= 0.05)
    alternatives = sorted({int(grid[i]) for i in close if abs(grid[i] - grid[best]) > 100})
    return {
        "load_kg": float(grid[best]),
        "target_ratio": round(float(target), 3),
        "within_range": within_range,
        "alternative_load_kg": alternatives[0] if alternatives else None,
        "note": (
            "Average car load that reproduces the equivalent load on this component's record."
            if within_range
            else "The recorded load is outside what this lift's load range can reproduce; the nearest load is used."
        ),
    }


def state_from_component(
    component: Any,
    events: List[Any],
    seed: int = 7,
    start: Optional[date] = None,
) -> Dict[str, Any]:
    """A simulation whose focus part is a real component, as its record stands today.

    The real part's counters, readings, service history, age and material
    are carried over. Its hidden true wear - which no record contains - is
    started at the life model's governing estimate for today, and its unit
    variation at 1.0, because nothing about this particular part says
    otherwise. The other three parts are simulated companions, new today.
    """
    component_type = str(component.component_type)
    if component_type not in COMPONENTS:
        raise ValueError(
            f"Simulation covers {', '.join(COMPONENTS)}; {component_type} is not supported yet."
        )
    if component.installation_date is None:
        raise ValueError("This component has no installation date, so its age cannot be simulated.")

    # The real part carries its own record; its companions start new, not
    # from the KONE reference lift, which is a different lift.
    state = new_state(seed=seed, start=start, from_kone=False)
    today = date.fromisoformat(state["start_date"])
    index = list(COMPONENTS).index(component_type)

    def month_of(when: date) -> float:
        return round((when - today).days / DAYS_PER_MONTH, 3)

    record = {
        "component_type": component_type,
        "material": component.material,
        "material_grade": getattr(component, "material_grade", None),
        "installation_date": component.installation_date,
        "component_age": component.component_age,
        "operating_hours": component.operating_hours,
        "load_cycles": component.load_cycles,
        "average_load": component.average_load,
        "vibration": component.vibration,
        "temperature": component.temperature,
        "service_count": component.service_count,
        "repair_count": component.repair_count,
        "failure_history": component.failure_history,
        "inspection_score": component.inspection_score,
        "days_since_last_service": component.days_since_last_service,
        "last_service_date": component.last_service_date,
    }
    grade, provenance = life_model.resolve_grade(component_type, component.material, record["material_grade"])
    # Carry only a recorded grade into the simulated slot; an assumed
    # industry-standard grade is re-derived from the material, never stored.
    grade = grade if provenance == "recorded" else None
    today_estimate = life_model.assess(record, today=today)
    starting_wear = min(float(today_estimate["life_consumed"]["governing"]), 0.95)

    implied = implied_load_kg(component_type, float(component.average_load or 0.0))
    share = APPORTIONMENT[component_type]
    p = life_model.MECHANISMS[component_type]["load_exponent"]
    rated = reference_for(component_type)["rated_load"]
    ratio = (
        float(component.average_load) / (life_model.reference_utilisation(component_type) * rated)
        if component.average_load
        else 1.0
    )
    trips = float(component.load_cycles or 0) / max(float(share["cycles"]), 1e-9)

    readings = [
        {
            "month": month_of(event.event_date),
            "vibration": event.vibration,
            "temperature": event.temperature,
            "inspection_score": event.inspection_score,
        }
        for event in sorted(events, key=lambda e: e.event_date)
        if event.event_date <= today
        and None not in (event.vibration, event.temperature, event.inspection_score)
    ][-early_warning.MAX_TREND_POINTS:]

    slot = _new_component(state, index, component_type, 1, 0, material=component.material, grade=grade)
    slot.update(
        {
            "installed_month": month_of(component.installation_date),
            "wear": starting_wear,
            "unit_variation": 1.0,
            "load_cycles": float(component.load_cycles or 0),
            "operating_hours": float(component.operating_hours or 0.0),
            "stress_moment": (ratio ** p) * trips,
            "trips": trips,
            "service_count": int(component.service_count or 0),
            "repair_count": int(component.repair_count or 0),
            "failure_history": int(component.failure_history or 0),
            "last_service_month": month_of(component.last_service_date or component.installation_date),
            "readings": readings,
            "true_vibration": component.vibration,
            "true_temperature": component.temperature,
        }
    )
    # Calibrate the twin to the real unit: at its implied load and estimated
    # wear, the simulated readings must reproduce what it actually read.
    values = ref.reference_values()
    implied_ratio = equivalent_ratio(
        component_type, implied["load_kg"], values["reference_load_kg"], values["load_spread_cv"]
    )
    thermal = _thermal_ratio(
        component_type, implied["load_kg"], values["reference_load_kg"], values["load_spread_cv"]
    )
    modelled_temperature = true_temperature(component_type, thermal, starting_wear, 0)
    modelled_vibration = true_vibration(component_type, implied_ratio, starting_wear)
    calibration = {
        "temperature_offset": round(float(component.temperature) - modelled_temperature, 2)
        if component.temperature is not None
        else 0.0,
        "vibration_scale": round(float(np.clip(float(component.vibration) / modelled_vibration, 0.3, 3.0)), 3)
        if component.vibration
        else 1.0,
    }
    slot.update(calibration)
    state["components"][component_type] = slot
    state["focus"] = {
        "component_id": component.component_id,
        "component_type": component_type,
        "location": getattr(component, "location", None),
        "historical_load_kg": implied["load_kg"],
        "implied_load": implied,
        "starting_wear": round(starting_wear, 4),
        "calibration": {
            **calibration,
            "note": (
                "Offsets that make the simulated temperature and vibration reproduce this "
                "unit's recorded readings at its implied load; load changes move them from there."
            ),
        },
        "starting_record": {
            key: (value.isoformat() if isinstance(value, date) else value)
            for key, value in record.items()
            if key in FEATURE_COLUMNS
        },
        "note": (
            f"{component.component_id} starts from its real record: age, counters, service "
            "history and readings. Its hidden true wear starts at today's life-model estimate. "
            "The other three parts are simulated companions, new today."
        ),
    }
    state["load_kg"] = implied["load_kg"]
    _log(
        state, component_type, "load",
        f"Started from {component.component_id}'s real record. Its equivalent load corresponds to "
        f"an average car load of about {implied['load_kg']:.0f} kg.",
    )
    return state


def start_from_component(component: Any, events: List[Any]) -> Dict[str, Any]:
    """A seeded state plus its first results, in the same shape as :func:`advance`."""
    state = state_from_component(component, events)
    return {
        "state": state,
        "series": [_series_point(state, state["load_kg"])],
        "results": results(state),
        "new_events": list(state["events"]),
        "api_source": ref.reference_values()["api_source"],
    }


# --------------------------------------------------------------------------
# Saved scenarios
# --------------------------------------------------------------------------
def scenario_summary(state: Dict[str, Any]) -> Dict[str, Any]:
    """What a saved scenario keeps: the focus part's simulated future only."""
    state = validate_state(state)
    focus = state.get("focus")
    if not focus:
        raise ValueError("Only a simulation started from a real component can be saved to its passport.")
    component_type = focus["component_type"]
    outcome = results(state)
    part = outcome["components"][component_type]
    series = state.get("focus_series") or []
    step = max(1, len(series) // 120)
    events = [
        event for event in state["events"]
        if event.get("component") == component_type and event["kind"] != "load"
    ]
    loads = sorted({round(point["load_kg"]) for point in series})
    return {
        "kind": "SIMULATION",
        "not_fleet_data": True,
        "component_type": component_type,
        "start_date": state["start_date"],
        "end_date": outcome["date"],
        "months_simulated": state["month"],
        "historical_load_kg": focus["historical_load_kg"],
        "loads_simulated_kg": loads,
        "final_load_kg": outcome["load_kg"],
        "replacements": sum(1 for e in events if e["kind"] in ("replace_proactive", "breakdown")),
        "breakdowns": sum(1 for e in events if e["kind"] == "breakdown"),
        "removed_part_categories": [
            e["message"].split("Removed part: ", 1)[1].split(" - ", 1)[0]
            for e in events
            if e["kind"] in ("replace_proactive", "breakdown") and "Removed part: " in e["message"]
        ],
        "first_replacement": next(
            (e for e in events if e["kind"] in ("replace_proactive", "breakdown")), None
        ),
        "end_state": {
            "life": part["life"],
            "true_wear": part["truth"]["wear"],
            "part_number": part["truth"]["life_number"],
            "ai": part["ai"],
            "early_warning_headline": (part["early_warning"] or {}).get("headline"),
        },
        "events": events[-40:],
        "series": series[::step],
        "starting_record": focus["starting_record"],
        "starting_wear": focus["starting_wear"],
        "basis": (
            "SIMULATED projection from this component's real record at the start date. Not a "
            "measurement, not fleet data, and never counted in dashboards, forecasts or reports."
        ),
    }
