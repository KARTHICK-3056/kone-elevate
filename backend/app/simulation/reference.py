"""Calibration reference for the elevator simulation, with a source for every value.

What "realistic" can honestly mean here
---------------------------------------
There is no real KONE data in this build. The recorded KONE API responses in
``app/integrations/fixtures`` carry KONE's published field names with values
**invented for the prototype** (their own README says so), and no live call
has ever been made. So the simulation cannot be "trained on real trends" -
and it does not pretend to be.

What it does instead is take every number from the most real source that
exists for it, and say which:

``kone_api``    Read through the KONE Equipment API adapter
                (``kone_adapters.equipment_telemetry``). Today that adapter
                replays recorded example values; the day credentials are
                configured it returns the live lift's figures and this
                reference - and the simulation built on it - recalibrates
                with no code change. ``api_source`` says which one ran.
``standard``    A published standard (number and year verified; clause and
                table pointers flagged as unverified, as in
                ``app/utils/standards.py``).
``physics``     A physical law applied to the stated lift geometry.
``assumption``  A documented engineering assumption for a typical lift.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.core.logging_config import get_logger
from app.integrations import kone_adapters, kone_features

logger = get_logger(__name__)

#: The lift the simulation models. KONE's Equipment API publishes no rated
#: load, car mass or counterweight, so these describe a typical 13-person
#: machine-room traction lift.
RATED_LOAD_KG = 1000.0
CAR_MASS_KG = 1100.0
#: Counterweight = car + this share of rated load. 40-50% is standard
#: practice; 50% balances the car when it is half full.
COUNTERWEIGHT_BALANCE = 0.5
COUNTERWEIGHT_KG = CAR_MASS_KG + COUNTERWEIGHT_BALANCE * RATED_LOAD_KG
RATED_SPEED_MPS = 1.6

#: EN 81-20 rates passenger lifts at 75 kg per person (1000 kg = 13 persons).
KG_PER_PERSON = 75.0

#: Load-weighing devices stop a lift at 110% of rated load (EN 81-20), so the
#: simulation accepts up to that and no further.
MAX_LOAD_KG = 1.10 * RATED_LOAD_KG

#: ISO 25745-2:2015 usage categories - average trips per day. The standard
#: identity is verified; the table values are from public summaries and are
#: CLAUSE_UNVERIFIED in the sense of app/utils/standards.py.
ISO_25745_2_TRIPS_PER_DAY = {1: 50, 2: 125, 3: 300, 4: 750, 5: 1500, 6: 2500}
USAGE_CATEGORY = 3

#: Machine-room ambient and its seasonal swing (a warm-climate site).
AMBIENT_C = 30.0
AMBIENT_SWING_C = 5.0

#: Months between preventive-maintenance visits when the KONE service orders
#: cannot establish one (fewer than two preventive visits) - the life model's
#: on-schedule assumption.
SERVICE_INTERVAL_MONTHS = 6

#: A per-month fault rate is only taken from the KONE service orders when
#: they cover at least this long a window; a shorter window cannot tell a
#: rate from chance, and the simulation's own fault model is used instead.
MIN_KONE_RATE_WINDOW_MONTHS = 12
DAYS_PER_MONTH = 30.4375

#: Used only if the adapter cannot be read at all.
_FALLBACK_MOVEMENT = {"durationSeconds": 22, "distanceMeters": 24.5, "load_percentage": 40.0, "floors": 8}

REFERENCE_EQUIPMENT = "ken:38999833"


def _movement() -> Dict[str, Any]:
    """The latest movement event from the KONE adapter, flattened."""
    try:
        telemetry = kone_adapters.equipment_telemetry(REFERENCE_EQUIPMENT)
    except Exception:  # pragma: no cover - adapter failure must not break the page
        logger.exception("KONE telemetry unavailable; simulation uses fallback reference")
        return {**_FALLBACK_MOVEMENT, "api_source": "unavailable"}
    movement = telemetry.get("movement") or {}
    decks = movement.get("decks") or [{}]
    deck = decks[0]
    start = (deck.get("startFloor") or {}).get("floorIndex", 0)
    stop = (deck.get("stopFloor") or {}).get("floorIndex", 7)
    return {
        "durationSeconds": float(movement.get("durationSeconds") or _FALLBACK_MOVEMENT["durationSeconds"]),
        "distanceMeters": float(movement.get("distanceMeters") or _FALLBACK_MOVEMENT["distanceMeters"]),
        "load_percentage": float(deck.get("loadPercentage") or _FALLBACK_MOVEMENT["load_percentage"]),
        "persons": deck.get("estimatedPersons"),
        "floors": abs(int(stop) - int(start)) + 1,
        "api_source": telemetry.get("source", "unknown"),
    }


def _parse(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _orders() -> List[Dict[str, Any]]:
    try:
        return kone_adapters.service_order_details(REFERENCE_EQUIPMENT)
    except Exception:  # pragma: no cover - adapter failure must not break the page
        logger.exception("KONE service orders unavailable; simulation starts without them")
        return []


def kone_record() -> Dict[str, Any]:
    """The reference lift's KONE record: the simulation's starting values and rates.

    KONE API first: every model input the KONE API publishes is read here,
    through the platform's own KONE feature mapping
    (``kone_features.derive_features``), so the simulation and the KONE
    integration agree on what each field means. Values KONE does not publish
    (vibration, temperature, a component's age) are left to the simulation.

    ``start`` holds the values month 0 begins from. ``rates`` holds the
    per-month figures the forward months use, each ``None`` when the KONE
    record is too thin to establish it - the caller then falls back to the
    simulation's own figure and says so in ``notes``.
    """
    try:
        telemetry = kone_adapters.equipment_telemetry(REFERENCE_EQUIPMENT)
    except Exception:  # pragma: no cover - adapter failure must not break the page
        telemetry = {}
    orders = _orders()
    derived = kone_features.derive_features("Motor", telemetry, orders)
    features, provenance = derived["features"], derived["provenance"]

    def kone_value(name: str) -> Optional[Any]:
        if provenance.get(name, {}).get("source") == "unavailable":
            return None
        return features.get(name)

    start = {
        name: kone_value(name)
        for name in (
            "service_count", "repair_count", "failure_history", "days_since_last_service", "inspection_score",
        )
    }

    dated = sorted(
        (
            (when, order)
            for order in orders
            for when in [_parse(order.get("finishedDateTime") or order.get("actualArrivalDateTime"))]
            if when is not None
        ),
        key=lambda pair: pair[0],
    )
    notes: Dict[str, str] = {}

    preventive = [
        when for when, order in dated if str(order.get("activityType") or "").upper() == "PREVENTIVE_MAINTENANCE"
    ]
    service_interval = None
    if len(preventive) >= 2:
        gaps = [(b - a).days / DAYS_PER_MONTH for a, b in zip(preventive, preventive[1:])]
        service_interval = max(1, round(sum(gaps) / len(gaps)))
        notes["service_interval_months"] = f"Mean gap between {len(preventive)} KONE preventive visits."
    else:
        notes["service_interval_months"] = (
            f"The KONE service orders hold {len(preventive)} preventive visit(s) - too few to derive an "
            f"interval, so the simulation uses {SERVICE_INTERVAL_MONTHS} months."
        )

    window_months = 0.0
    if dated:
        window_months = (datetime.now(timezone.utc) - dated[0][0]).days / DAYS_PER_MONTH
    repairs = start.get("repair_count")
    callout_rate = None
    if window_months >= MIN_KONE_RATE_WINDOW_MONTHS and repairs is not None:
        callout_rate = repairs / window_months
        notes["callout_rate_per_month"] = f"{repairs} KONE repair/callout orders over {window_months:.1f} months."
    else:
        notes["callout_rate_per_month"] = (
            f"The KONE service orders cover {window_months:.1f} months - under "
            f"{MIN_KONE_RATE_WINDOW_MONTHS}, too short to tell a fault rate from chance - so new faults "
            "come from the simulation's own wear-driven fault model."
        )

    return {
        "api_source": derived.get("source") or telemetry.get("source", "unknown"),
        "equipment_id": REFERENCE_EQUIPMENT,
        "orders": len(dated),
        "window_months": round(window_months, 1),
        "start": start,
        "start_notes": {name: provenance.get(name, {}).get("note") for name in start},
        "rates": {"service_interval_months": service_interval, "callout_rate_per_month": callout_rate},
        "notes": notes,
    }


def _item(value: Any, unit: str, source: str, basis: str) -> Dict[str, Any]:
    return {"value": value, "unit": unit, "source": source, "basis": basis}


def reference_profile() -> Dict[str, Any]:
    """Everything the simulation is calibrated on, each value with its source."""
    movement = _movement()
    api_source = movement["api_source"]
    recorded = api_source != "live"
    api_note = (
        "KONE API field, recorded EXAMPLE value (schema is KONE's, value is illustrative). "
        "Recalibrates automatically once live credentials are configured."
        if recorded
        else "KONE API field, live value."
    )
    floors = movement["floors"]
    floor_height = movement["distanceMeters"] / max(floors - 1, 1)
    trips_per_day = ISO_25745_2_TRIPS_PER_DAY[USAGE_CATEGORY]
    reference_load = RATED_LOAD_KG * movement["load_percentage"] / 100.0
    record = kone_record()
    interval = record["rates"]["service_interval_months"]

    return {
        "api_source": api_source,
        "api_values_are_real": not recorded,
        "lift": {
            "rated_load_kg": _item(RATED_LOAD_KG, "kg", "assumption", "Typical 13-person traction lift; KONE publishes no rated-load field."),
            "car_mass_kg": _item(CAR_MASS_KG, "kg", "assumption", "Typical car mass for a 1000 kg lift."),
            "counterweight_kg": _item(COUNTERWEIGHT_KG, "kg", "physics", f"Car mass + {COUNTERWEIGHT_BALANCE:.0%} of rated load - standard balancing practice."),
            "rated_speed_mps": _item(RATED_SPEED_MPS, "m/s", "assumption", "Common mid-rise office speed."),
            "floors": _item(floors, "floors", "kone_api", f"From the movement event's start/stop floors. {api_note}"),
            "floor_height_m": _item(round(floor_height, 2), "m", "kone_api", f"distanceMeters / floors travelled. {api_note}"),
            "kg_per_person": _item(KG_PER_PERSON, "kg", "standard", "EN 81-20 passenger rating (75 kg per person)."),
            "max_load_kg": _item(MAX_LOAD_KG, "kg", "standard", "Overload device trips at 110% of rated load (EN 81-20)."),
        },
        "traffic": {
            "trips_per_day": _item(trips_per_day, "trips/day", "standard", f"ISO 25745-2:2015 usage category {USAGE_CATEGORY} (table values from public summaries - unverified against the purchased text)."),
            "trip_duration_s": _item(movement["durationSeconds"], "s", "kone_api", f"Movement event durationSeconds. {api_note}"),
            "reference_load_kg": _item(round(reference_load, 1), "kg", "kone_api", f"Movement event loadPercentage x rated load - the load the design life is referenced to. {api_note}"),
            "load_spread_cv": _item(0.7, "", "assumption", "Per-trip load varies around the average (coefficient of variation 0.7): lifts run nearly empty and nearly full within a day."),
        },
        "environment": {
            "ambient_c": _item(AMBIENT_C, "C", "assumption", f"Machine-room ambient, +/- {AMBIENT_SWING_C:g} C seasonal swing."),
            "service_interval_months": (
                _item(interval, "months", "kone_api", f"{record['notes']['service_interval_months']} {api_note}")
                if interval
                else _item(SERVICE_INTERVAL_MONTHS, "months", "assumption", record["notes"]["service_interval_months"])
            ),
        },
        "kone_record": record,
        "notice": (
            "No real KONE data exists in this build. Values marked kone_api come through the "
            "KONE API adapter, which currently replays recorded example responses; standards and "
            "physics are real; assumptions are stated. The simulation starts from the reference "
            "lift's KONE record and takes every rate KONE publishes from it; only what KONE does "
            "not publish (vibration, temperature, component age) is simulated. It is a model, not a record."
        ),
    }


def reference_values() -> Dict[str, float]:
    """The plain numbers the engine needs, pulled from :func:`reference_profile`."""
    profile = reference_profile()
    record = profile["kone_record"]
    return {
        "api_source": profile["api_source"],
        "service_interval_months": float(profile["environment"]["service_interval_months"]["value"]),
        "callout_rate_per_month": record["rates"]["callout_rate_per_month"],
        "kone_start": record["start"],
        "trips_per_day": float(profile["traffic"]["trips_per_day"]["value"]),
        "trip_duration_s": float(profile["traffic"]["trip_duration_s"]["value"]),
        "reference_load_kg": float(profile["traffic"]["reference_load_kg"]["value"]),
        "load_spread_cv": float(profile["traffic"]["load_spread_cv"]["value"]),
        "floors": int(profile["lift"]["floors"]["value"]),
        "floor_height_m": float(profile["lift"]["floor_height_m"]["value"]),
    }
