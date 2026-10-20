"""Turning KONE equipment telemetry into component-level model features.

The mismatch this module exists for
-----------------------------------
KONE addresses **equipment**: one whole lift behind one KONE Equipment
Number. This platform assesses **components**. Every duty figure the
Equipment Status API returns therefore describes the lift, and attributing
it to one sheave inside that lift is an **apportionment assumption we are
making**, not a measurement KONE handed us.

That distinction is the entire point of this module. Every feature it
produces carries a provenance tag:

``measured``     - read from a KONE field with no reinterpretation.
``apportioned``  - an equipment-level figure divided down to a component
                   by an assumption stated in ``APPORTIONMENT`` below.
``derived``      - computed from KONE fields (a count, an interval).
``unavailable``  - no source exists; the caller must decide what to do.

A prediction built on these can then report how much of its own input was
real, which nothing in this system could do while every feature came from
the same synthetic generator. It is the natural extension of the pattern
``material_flow.mass_source`` already established for mass.

What has no source at all
-------------------------
``vibration`` and ``temperature`` appear in no published KONE feed. There
is no accelerometer or thermal channel in the Equipment Status API. They
are returned as ``unavailable`` with a null value, and it is deliberately
**not** this module's job to quietly substitute a default: feeding an
invented vibration reading into a safety-relevant model is precisely the
failure this codebase spends its effort avoiding. See
:func:`missing_for_model`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.utils.enums import ComponentType

#: KONE ``failedComponentCode`` values onto this platform's component types.
#: The only component-level key anywhere in KONE's public API surface, so
#: this table is the hinge the whole integration turns on. Codes are the
#: plausible spellings from the published examples; a real deployment must
#: reconcile it against KONE's actual code list before being trusted.
FAILED_COMPONENT_CODE_MAP: Dict[str, str] = {
    "DOOR_OPERATOR": ComponentType.DOOR_OPERATOR.value,
    "DOOR": ComponentType.DOOR_OPERATOR.value,
    "MOTOR": ComponentType.MOTOR.value,
    "TRACTION_MOTOR": ComponentType.MOTOR.value,
    "MACHINE": ComponentType.MOTOR.value,
    "BRAKE": ComponentType.BRAKE.value,
    "GOVERNOR": ComponentType.GOVERNOR.value,
    "OVERSPEED_GOVERNOR": ComponentType.GOVERNOR.value,
    "ROPE": ComponentType.STEEL_ROPE.value,
    "SUSPENSION_ROPE": ComponentType.STEEL_ROPE.value,
    "STEEL_ROPE": ComponentType.STEEL_ROPE.value,
    "SHEAVE": ComponentType.SHEAVE.value,
    "TRACTION_SHEAVE": ComponentType.SHEAVE.value,
}

#: How much of the lift's duty each component type actually absorbs, and
#: why. These are **prototype engineering judgements**, not KONE data -
#: they are the assumption the honesty of this whole layer rests on, so
#: each one states its reasoning and a workshop engineer should expect to
#: rewrite the numbers.
#:
#: ``hours``  - share of lift running time the component is under load.
#: ``cycles`` - component actuations per lift journey.
APPORTIONMENT: Dict[str, Dict[str, Any]] = {
    ComponentType.MOTOR.value: {
        "hours": 1.0,
        "cycles": 1.0,
        "rationale": "Runs for the whole of every journey; one start per journey.",
    },
    ComponentType.SHEAVE.value: {
        "hours": 1.0,
        "cycles": 1.0,
        "rationale": "Rope passes over it for the whole journey.",
    },
    ComponentType.STEEL_ROPE.value: {
        "hours": 1.0,
        "cycles": 1.0,
        "rationale": "In tension throughout; one bending cycle per journey.",
    },
    ComponentType.BRAKE.value: {
        "hours": 0.05,
        "cycles": 1.0,
        "rationale": (
            "Applied only at the end of a journey - a small share of running "
            "time, but one full actuation every journey."
        ),
    },
    ComponentType.DOOR_OPERATOR.value: {
        "hours": 0.15,
        "cycles": 2.0,
        "rationale": (
            "Active only while doors move, but opens and closes once each per "
            "journey - the highest cycle count in the lift."
        ),
    },
    ComponentType.GOVERNOR.value: {
        "hours": 1.0,
        "cycles": 1.0,
        "rationale": "Rope-driven continuously; trips essentially never.",
    },
}

_DEFAULT_APPORTIONMENT = {
    "hours": 1.0,
    "cycles": 1.0,
    "rationale": "Unknown component type - lift-level duty passed through unscaled.",
}

#: KONE condition codes are ordinal (1 best). Mapped onto this platform's
#: 0-100 inspection score. Coarse by nature: four buckets cannot carry the
#: resolution a 0-100 score implies, and the score is reported as a proxy
#: for exactly that reason.
CONDITION_CODE_TO_SCORE: Dict[str, float] = {
    "1": 90.0,
    "2": 72.0,
    "3": 48.0,
    "4": 20.0,
}

#: Features the model consumes that no KONE feed carries.
UNAVAILABLE_FEATURES = ("vibration", "temperature")


def map_failed_component(code: Optional[str]) -> Optional[str]:
    """KONE ``failedComponentCode`` -> this platform's component type."""
    if not code:
        return None
    return FAILED_COMPONENT_CODE_MAP.get(str(code).strip().upper())


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _parse(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def derive_features(
    component_type: str,
    telemetry: Dict[str, Any],
    service_orders: List[Dict[str, Any]],
    journeys_observed: Optional[int] = None,
    observation_days: Optional[float] = None,
) -> Dict[str, Any]:
    """Build model features for one component from its lift's KONE data.

    ``telemetry`` is the dict :func:`kone_adapters.equipment_telemetry`
    returns; ``service_orders`` the raw detail documents from
    :func:`kone_adapters.service_order_details`.

    ``journeys_observed`` / ``observation_days`` describe the window the
    movement feed covers. KONE's movement endpoint returns *events*, not
    lifetime totals, so without a stated window there is no honest way to
    scale one journey into a duty figure - and this returns the count it
    actually saw rather than extrapolating silently.
    """
    share = APPORTIONMENT.get(component_type, _DEFAULT_APPORTIONMENT)
    movement = telemetry.get("movement") or {}
    status = telemetry.get("status") or {}

    features: Dict[str, Any] = {}
    provenance: Dict[str, Dict[str, Any]] = {}

    def record(name: str, value: Any, source: str, note: str) -> None:
        features[name] = value
        provenance[name] = {"source": source, "note": note}

    record("component_type", component_type, "measured", "Caller-supplied component identity.")

    # --- duty -------------------------------------------------------------
    journeys = journeys_observed if journeys_observed is not None else _journey_count(movement)
    seconds = float(movement.get("durationSeconds") or 0.0)
    if journeys and seconds:
        lift_hours = (seconds * journeys) / 3600.0
        record(
            "operating_hours",
            round(lift_hours * float(share["hours"]), 2),
            "apportioned",
            (
                f"{lift_hours:.1f} lift running hours over {journeys} observed "
                f"journeys x {share['hours']} duty share. {share['rationale']}"
            ),
        )
        record(
            "load_cycles",
            int(round(journeys * float(share["cycles"]))),
            "apportioned",
            f"{journeys} observed journeys x {share['cycles']} actuations. {share['rationale']}",
        )
    else:
        record("operating_hours", None, "unavailable", "No movement window observed.")
        record("load_cycles", None, "unavailable", "No movement window observed.")

    load_percentage = _load_percentage(movement)
    if load_percentage is not None:
        record(
            "average_load",
            round(load_percentage, 2),
            "apportioned",
            (
                "Mean deck loadPercentage. Reported as a PERCENTAGE of rated "
                "load, not kilograms: KONE publishes no rated-load field, so "
                "converting would require a capacity figure this platform does "
                "not have."
            ),
        )
    else:
        record("average_load", None, "unavailable", "No loadPercentage in the movement feed.")

    # --- service history --------------------------------------------------
    completed = [order for order in service_orders if _parse(_finished(order))]
    record(
        "service_count",
        len(completed),
        "derived",
        "Count of dated service orders for the equipment (lift-level, not per component).",
    )
    repairs = [
        order
        for order in completed
        if str(order.get("activityType") or "").upper() in {"REPAIR", "CALLOUT"}
    ]
    record(
        "repair_count",
        len(repairs),
        "derived",
        "Service orders of activityType REPAIR or CALLOUT.",
    )
    failures = [
        order
        for order in completed
        if order.get("equipmentFailureReason") or order.get("entrapment")
    ]
    record(
        "failure_history",
        len(failures),
        "derived",
        "Orders carrying an equipmentFailureReason, or an entrapment.",
    )

    latest = max(
        (_parse(_finished(order)) for order in completed if _parse(_finished(order))),
        default=None,
    )
    if latest is not None:
        record(
            "days_since_last_service",
            max(0, (_now() - _aware(latest)).days),
            "derived",
            f"Days since finishedDateTime of the most recent order ({latest.date()}).",
        )
    else:
        record("days_since_last_service", None, "unavailable", "No dated service order.")

    # --- condition --------------------------------------------------------
    inspection = _latest_condition(completed)
    if inspection is not None:
        record(
            "inspection_score",
            inspection,
            "apportioned",
            (
                "Mapped from the ordinal equipmentConditionOnDeparture code. "
                "Four buckets cannot carry 0-100 resolution, and the code "
                "describes the LIFT, not this component."
            ),
        )
    else:
        record("inspection_score", None, "unavailable", "No condition code on any order.")

    # --- component age ----------------------------------------------------
    record(
        "component_age",
        None,
        "unavailable",
        (
            "No commissioning date exists in any published KONE schema, and a "
            "component's own age is not the lift's in any case."
        ),
    )

    # --- the two with no channel at all ------------------------------------
    for name in UNAVAILABLE_FEATURES:
        record(
            name,
            None,
            "unavailable",
            (
                f"No {name} channel exists in any published KONE feed. Deliberately "
                "not defaulted: feeding an invented reading into a safety-relevant "
                "model is the failure this layer exists to prevent."
            ),
        )

    return {
        "component_type": component_type,
        "features": features,
        "provenance": provenance,
        "coverage": _coverage(provenance),
        "equipment_id": status.get("equipmentId") or movement.get("equipmentId"),
        "observation_days": observation_days,
        "source": telemetry.get("source", "unknown"),
        "notice": (
            "Equipment-level KONE telemetry apportioned to one component. The "
            "apportionment is this platform's assumption, not a KONE "
            "measurement - see app/integrations/kone_features.APPORTIONMENT."
        ),
    }


def _journey_count(movement: Dict[str, Any]) -> int:
    """How many journeys the movement payload represents.

    KONE's endpoint returns the last saved event, so a single document is
    one journey. A real deployment consuming the stream would accumulate
    these; counting one is the honest reading of one document.
    """
    return 1 if movement.get("movementEventType") else 0


def _load_percentage(movement: Dict[str, Any]) -> Optional[float]:
    decks = movement.get("decks") or []
    values = [
        float(deck["loadPercentage"])
        for deck in decks
        if deck.get("loadPercentage") is not None
    ]
    return sum(values) / len(values) if values else None


def _finished(order: Dict[str, Any]) -> Optional[str]:
    return order.get("finishedDateTime") or order.get("actualArrivalDateTime")


def _latest_condition(orders: List[Dict[str, Any]]) -> Optional[float]:
    dated = [
        (_parse(_finished(order)), order)
        for order in orders
        if _parse(_finished(order)) and order.get("equipmentConditionOnDeparture")
    ]
    if not dated:
        return None
    _when, newest = max(dated, key=lambda pair: pair[0])
    return CONDITION_CODE_TO_SCORE.get(str(newest["equipmentConditionOnDeparture"]).strip())


def _coverage(provenance: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """How much of this feature vector is real, as a headline figure."""
    counts: Dict[str, int] = {}
    for entry in provenance.values():
        counts[entry["source"]] = counts.get(entry["source"], 0) + 1
    total = sum(counts.values())
    grounded = total - counts.get("unavailable", 0)
    return {
        "by_source": counts,
        "fields": total,
        "grounded_fields": grounded,
        "grounded_percent": round(100.0 * grounded / total, 1) if total else 0.0,
    }


def missing_for_model(derived: Dict[str, Any]) -> List[str]:
    """Features the model needs that this derivation could not supply.

    A caller must decide explicitly what to do with these - impute and flag,
    or decline to score. Returning the list rather than silently filling
    them is the whole contract: a prediction whose vibration reading was
    invented should never be indistinguishable from one whose was measured.
    """
    return [
        name
        for name, entry in derived.get("provenance", {}).items()
        if entry["source"] == "unavailable"
    ]


def validate_condition_code_direction(orders: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Check the riskiest assumption in this integration against real data.

    ``CONDITION_CODE_TO_SCORE`` assumes KONE's condition codes are ordinal
    with **1 = best**. Nothing in the published reference implementation
    states the direction, and if it is inverted every inspection score this
    layer produces is inverted too - a silent, total corruption of the one
    condition signal the model has, with no error and no crash.

    It is also *detectable*, which is why this exists. Orders carrying a
    failure should skew toward the worse end of the scale. If the opposite
    holds on real data, the mapping is upside down.

    Returns a verdict rather than raising: on the recorded fixtures there
    is far too little data to conclude anything, and a check that cried
    wolf on four rows would just get switched off.
    """
    with_failure: List[float] = []
    without_failure: List[float] = []
    for order in orders:
        code = str(order.get("equipmentConditionOnArrival") or "").strip()
        if code not in CONDITION_CODE_TO_SCORE:
            continue
        score = CONDITION_CODE_TO_SCORE[code]
        failed = bool(order.get("equipmentFailureReason") or order.get("entrapment"))
        (with_failure if failed else without_failure).append(score)

    if len(with_failure) < 3 or len(without_failure) < 3:
        return {
            "verdict": "insufficient_data",
            "assumption": "KONE condition codes are ordinal with 1 = best.",
            "failed_orders": len(with_failure),
            "healthy_orders": len(without_failure),
            "note": (
                "Needs at least 3 of each to say anything. Re-run against a "
                "real equipment history before trusting inspection_score."
            ),
        }

    failed_mean = sum(with_failure) / len(with_failure)
    healthy_mean = sum(without_failure) / len(without_failure)
    consistent = failed_mean < healthy_mean
    return {
        "verdict": "consistent" if consistent else "SUSPECT_INVERTED",
        "assumption": "KONE condition codes are ordinal with 1 = best.",
        "mean_score_when_failed": round(failed_mean, 1),
        "mean_score_when_healthy": round(healthy_mean, 1),
        "failed_orders": len(with_failure),
        "healthy_orders": len(without_failure),
        "note": (
            "Orders with a recorded failure score worse, as expected."
            if consistent
            else (
                "Orders WITH a failure are scoring BETTER than those without. "
                "CONDITION_CODE_TO_SCORE is probably inverted, which would "
                "invert every inspection_score this layer produces. Do not "
                "use derived features until this is resolved."
            )
        ),
    }
