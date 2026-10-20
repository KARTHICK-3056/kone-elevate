"""Standards-based inspection: the condition score from real measurements.

Why this exists
---------------
Until now ``inspection_score`` was a number a technician typed in - "82/100"
- with nothing behind it. Every model in this platform leans on that number
(the life model lets it govern, the early-warning forecast trends it, the
classifier uses it as a feature), so it is the single most important input
to make real.

Technicians already take real measurements at a maintenance visit, because
the standards require them: rope diameter and broken wires, sheave groove
wear, brake lining thickness and a torque test, motor insulation resistance
and bearing vibration. This module turns those measurements into the score,
and records which one governed it.

Scoring
-------
Each measurement is placed on a scale from new condition (0) to its discard
or action limit (1)::

    consumption = (measured - new) / (limit - new)       clipped to [0, 1.5]

The **worst** measurement governs - a rope with a perfect diameter and ten
broken wires is a rope to discard - and maps onto the same scale the life
model uses (``life_model``: score 100 = new, 48 = replace band, 35 = end)::

    inspection_score = 100 - 65 x governing consumption

A measurement at or beyond its limit is reported as a **discard criterion
met**, which is a safety finding, not a score.

READ BEFORE RELYING ON A LIMIT
------------------------------
Standards are copyrighted and were not available to this build (see
``app/utils/standards.py``). Every limit carries a ``basis`` and a
``verification`` flag:

* ``MANUFACTURER`` - the limit is component-specific and must be entered
  from the manufacturer's data (e.g. brake lining minimum thickness).
* ``PROTOTYPE_DEFAULT`` - a typical value used so the checklist works out of
  the box. It must be replaced with the value from the named standard or
  the manufacturer before any real discard decision.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from app.ml import life_model
from app.utils.enums import ComponentType, is_safety_critical

MANUFACTURER = "MANUFACTURER"
PROTOTYPE_DEFAULT = "PROTOTYPE_DEFAULT"

#: Score scale shared with the life model (100 - 65 x consumption).
_SCORE_SPAN = 65.0
_MAX_CONSUMPTION = 1.5


def _numeric(
    key: str,
    label: str,
    unit: str,
    new: float,
    limit: float,
    how: str,
    basis: str,
    verification: str = PROTOTYPE_DEFAULT,
    scale: str = "linear",
    reading: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "kind": "numeric",
        "unit": unit,
        "new": new,
        "limit": limit,
        "scale": scale,
        "how_measured": how,
        "basis": basis,
        "verification": verification,
        "reading": reading,
    }


def _check(key: str, label: str, fail_consumption: float, how: str, basis: str) -> Dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "kind": "pass_fail",
        "fail_consumption": fail_consumption,
        "how_measured": how,
        "basis": basis,
        "verification": PROTOTYPE_DEFAULT,
    }


def _choice(key: str, label: str, options: Dict[str, float], how: str, basis: str) -> Dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "kind": "choice",
        "options": [{"value": value, "consumption": weight} for value, weight in options.items()],
        "how_measured": how,
        "basis": basis,
        "verification": PROTOTYPE_DEFAULT,
    }


#: What a technician measures, per component type.
CHECKLISTS: Dict[str, List[Dict[str, Any]]] = {
    ComponentType.STEEL_ROPE.value: [
        _numeric(
            "rope_diameter_reduction_pct", "Rope diameter reduction", "% of nominal", 0.0, 6.0,
            "Measure the diameter across the crowns at the most-used section (over the sheave "
            "at the usual stopping floors) and compare with the nominal diameter.",
            "ISO 4344 discard criteria for lift ropes. 6% is a commonly applied lift-rope limit.",
            reading="Enter nominal and measured diameter; the reduction is computed.",
        ),
        _numeric(
            "broken_wires_6d", "Visible broken wires over 6 x rope diameter", "wires", 0.0, 5.0,
            "Count visible broken outer wires over a length of six rope diameters at the worst section.",
            "ISO 4344 discard criteria - the permitted count depends on rope construction; take it "
            "from the standard's table or the rope manufacturer.",
        ),
        _choice(
            "rope_corrosion", "Corrosion",
            {"none": 0.0, "surface rust, lubricated": 0.35, "pitting or dry and rusted": 1.0},
            "Visual check along the working length.",
            "ISO 4344 lists corrosion as a discard condition when wires are pitted.",
        ),
    ],
    ComponentType.SHEAVE.value: [
        _numeric(
            "groove_wear_mm", "Groove wear depth", "mm", 0.0, 1.5,
            "Groove gauge on each groove; record the worst.",
            "Traction depends on groove profile (EN 81-20 traction verification). Limit from the "
            "machine manufacturer's groove gauge.",
        ),
        _numeric(
            "groove_depth_difference_mm", "Depth difference between grooves", "mm", 0.0, 1.0,
            "Deepest minus shallowest groove - uneven grooves make the ropes share load unequally.",
            "Manufacturer's groove gauge tolerance.",
        ),
        _check(
            "sheave_no_cracks", "Rim and spokes free of cracks", 1.0,
            "Visual / dye-penetrant check of rim and spokes.",
            "Any crack in a traction sheave is a replacement criterion.",
        ),
    ],
    ComponentType.BRAKE.value: [
        _numeric(
            "lining_wear_pct", "Lining worn towards minimum thickness", "% of wear allowance", 0.0, 100.0,
            "Measure lining thickness; the wear allowance is new thickness minus the manufacturer's "
            "minimum.",
            "Manufacturer's minimum lining thickness.",
            verification=MANUFACTURER,
            reading="Enter new, minimum and measured thickness; the share of allowance used is computed.",
        ),
        _check(
            "air_gap_in_range", "Air gap within the manufacturer's range", 0.5,
            "Feeler gauge between armature and magnet body.",
            "Manufacturer's air-gap range. Out of range needs adjustment, not replacement.",
        ),
        _check(
            "brake_torque_test_passed", "Brake torque / holding test passed", 1.0,
            "Holding test with the car loaded as the test procedure requires.",
            "EN 81-20 / EN 81-50 brake requirements; a failed test is a safety finding.",
        ),
    ],
    ComponentType.MOTOR.value: [
        _numeric(
            "insulation_resistance_mohm", "Winding insulation resistance", "MOhm", 100.0, 1.0,
            "Insulation-resistance (megger) test, winding to earth, at the rated test voltage.",
            "Common maintenance acceptance minimum of 1 MOhm for low-voltage machines; IEEE 43 "
            "recommends higher minimums for modern windings.",
            scale="log",
        ),
        _numeric(
            "bearing_vibration_mm_s", "Bearing vibration velocity", "mm/s RMS", 1.4, 7.1,
            "Velocity RMS on the bearing housing, machine running.",
            "ISO 10816-3 / ISO 20816-3 evaluation zones: 1.4 (new, zone A) to 7.1 mm/s (zone D) for "
            "medium machines on flexible supports. Table values from public summaries.",
        ),
        _numeric(
            "bearing_temperature_c", "Bearing temperature", "C", 40.0, 90.0,
            "Surface temperature of the bearing housing after running.",
            "Manufacturer's bearing temperature limit.",
        ),
        _check(
            "no_abnormal_noise", "No abnormal bearing noise", 0.6,
            "Listen with a stethoscope / acoustic probe.",
            "Bearing noise precedes failure; it calls for replacement planning, not immediate discard.",
        ),
    ],
    ComponentType.GOVERNOR.value: [
        _numeric(
            "governor_tripping_speed_deviation_pct", "Tripping speed deviation from the type-test certificate",
            "% of rated speed", 0.0, 5.0,
            "Overspeed test on the governor test rig (or the periodic examination record) compared "
            "with the tripping speed on the nameplate / type-test certificate.",
            "EN 81-20:2020 cl. 5.6.2 - the governor must trip within its type-tested range. The "
            "acceptance tolerance is component-specific; take it from the certificate.",
            verification=MANUFACTURER,
        ),
        _numeric(
            "governor_rope_groove_wear_mm", "Governor rope groove wear depth", "mm", 0.0, 1.0,
            "Groove gauge on the governor sheave; record the worst.",
            "Groove wear reduces the pinch on the governor rope, so the rope can slip instead of "
            "pulling the safety gear (EN 81-20:2020 cl. 5.6.2).",
        ),
        _check(
            "governor_switch_trips_before_mechanical", "Electrical overspeed switch trips before the mechanical trip speed",
            1.0,
            "Run the car up to the switch's set speed, below the mechanical trip speed, and confirm "
            "the safety chain opens.",
            "EN 81-20:2020 cl. 5.6.2 requires an electrical safety device operated by the governor "
            "before mechanical tripping; a failed switch is a safety finding.",
        ),
        _check(
            "governor_jaw_grips_rope", "Rope-gripping jaw stops the governor rope on trip", 1.0,
            "During the periodic tripping test, confirm the jaw grips and stops the rope without "
            "slipping.",
            "The jaw pulls the safety-gear linkage; a slipping jaw means the safety gear will not "
            "apply (EN 81-20:2020 cl. 5.6.2).",
        ),
        _choice(
            "governor_linkage_condition", "Tripping linkage and springs",
            {"free and lubricated": 0.0, "stiff or lightly corroded": 0.4, "seized or springs relaxed": 1.0},
            "Hand-check the pivots move freely and the springs return the flyweights; look for "
            "corrosion.",
            "Pivots seize and springs relax between periodic tests even without travel - a "
            "discard condition the life model already tracks for this mechanism.",
        ),
    ],
}

#: Which checklist measurement also fills the component's vibration and
#: temperature readings, so the trend models see measured values.
READING_FIELDS: Dict[str, Dict[str, str]] = {
    ComponentType.MOTOR.value: {
        "vibration": "bearing_vibration_mm_s",
        "temperature": "bearing_temperature_c",
    },
}


def checklist(component_type: str) -> Optional[Dict[str, Any]]:
    """The measurement checklist for a component type, or None if not covered."""
    items = CHECKLISTS.get(str(component_type))
    if items is None:
        return None
    return {
        "component_type": component_type,
        "items": items,
        "safety_critical": is_safety_critical(component_type),
        "scoring": (
            "Each measurement is placed between new condition (0) and its limit (1); the worst "
            "one governs, and inspection score = 100 - 65 x that value - the scale the life "
            "model uses. A measurement at or past its limit is a discard criterion met."
        ),
        "notice": (
            "Limits marked PROTOTYPE_DEFAULT are typical values for demonstration and must be "
            "replaced with the named standard's or manufacturer's value before any real "
            "discard decision. MANUFACTURER limits are entered per component."
        ),
    }


def derive(component_type: str, raw: Dict[str, Any]) -> Dict[str, Any]:
    """Turn raw helper inputs into checklist measurements.

    Some checklist items are ratios a technician does not measure directly:
    rope diameter reduction from nominal and measured diameter, and brake
    lining wear from new, minimum and measured thickness.
    """
    values = dict(raw)
    if component_type == ComponentType.STEEL_ROPE.value:
        nominal = values.pop("nominal_diameter_mm", None)
        measured = values.pop("measured_diameter_mm", None)
        if nominal and measured is not None and "rope_diameter_reduction_pct" not in values:
            values["rope_diameter_reduction_pct"] = round(100.0 * (nominal - measured) / nominal, 2)
    if component_type == ComponentType.BRAKE.value:
        new = values.pop("lining_new_mm", None)
        minimum = values.pop("lining_minimum_mm", None)
        measured = values.pop("lining_measured_mm", None)
        if new and minimum is not None and measured is not None and "lining_wear_pct" not in values:
            if new <= minimum:
                raise ValueError("New lining thickness must be greater than the minimum.")
            values["lining_wear_pct"] = round(100.0 * (new - measured) / (new - minimum), 1)
    return values


def _consumption(item: Dict[str, Any], value: Any) -> float:
    kind = item["kind"]
    if kind == "pass_fail":
        return 0.0 if bool(value) else float(item["fail_consumption"])
    if kind == "choice":
        for option in item["options"]:
            if option["value"] == value:
                return float(option["consumption"])
        raise ValueError(f"'{value}' is not an option for {item['label']}.")
    value = float(value)
    new, limit = float(item["new"]), float(item["limit"])
    if item["scale"] == "log":
        if value <= 0:
            return _MAX_CONSUMPTION
        span = math.log10(new) - math.log10(limit)
        raw = (math.log10(new) - math.log10(value)) / span
    else:
        raw = (value - new) / (limit - new)
    return max(0.0, min(_MAX_CONSUMPTION, raw))


def score(component_type: str, raw_measurements: Dict[str, Any]) -> Dict[str, Any]:
    """Score one inspection. Raises ValueError for an unknown type or bad value."""
    component_type = str(component_type)
    items = CHECKLISTS.get(component_type)
    if items is None:
        raise ValueError(
            f"No measurement checklist for {component_type} yet. Covered: {', '.join(CHECKLISTS)}."
        )
    measurements = derive(component_type, raw_measurements)
    by_key = {item["key"]: item for item in items}
    unknown = set(measurements) - set(by_key)
    if unknown:
        raise ValueError(f"Unknown measurements for {component_type}: {', '.join(sorted(unknown))}.")
    if not measurements:
        raise ValueError("Record at least one measurement.")

    results = []
    for key, value in measurements.items():
        item = by_key[key]
        consumption = _consumption(item, value)
        results.append(
            {
                "key": key,
                "label": item["label"],
                "value": value,
                "unit": item.get("unit"),
                "limit": item.get("limit"),
                "consumption": round(consumption, 3),
                "discard_criterion_met": consumption >= 1.0,
                "verification": item["verification"],
                "basis": item["basis"],
            }
        )
    governing = max(results, key=lambda r: r["consumption"])
    inspection_score = round(max(0.0, min(100.0, 100.0 - _SCORE_SPAN * governing["consumption"])), 1)
    discard = [r["label"] for r in results if r["discard_criterion_met"]]
    missing = [item["label"] for item in items if item["key"] not in measurements]

    return {
        "component_type": component_type,
        "inspection_score": inspection_score,
        "governing": {"key": governing["key"], "label": governing["label"]},
        "band": (
            "green" if governing["consumption"] < life_model.SUITABLE_LIMIT
            else "amber" if governing["consumption"] < life_model.REPLACE_LIMIT
            else "red"
        ),
        "discard_criteria_met": discard,
        "measurements": results,
        "not_measured": missing,
        "measured_values": measurements,
        "readings": {
            field: float(measurements[key])
            for field, key in READING_FIELDS.get(component_type, {}).items()
            if key in measurements
        },
        "method": "measured-checklist-v1",
    }
