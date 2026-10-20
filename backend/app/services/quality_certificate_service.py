"""Manufacturer quality certificate (EN 10204 type 3.1 layout) for a passport.

A digital product passport carries the manufacturer's inspection certificate
for the part. No supplier certificate feed is connected yet, so this builds a
SAMPLE in the exact layout the real one arrives in: every field is derived
deterministically from the component's own record (type, recorded or assumed
material grade, per-part specification, origin plant, installation date), and
the test results are values consistent with that grade and within the cited
requirement. The certificate says plainly that it is a sample, to be replaced
by the manufacturer's issued certificate when supplier data is connected.

No person, notified-body number or type-examination certificate number is
invented: the inspector is named by role and the type-examination reference
by the clause it is held under.
"""

from __future__ import annotations

import hashlib
import random
from datetime import timedelta
from typing import Any, Dict, List, Optional

from app.ml import life_model
from app.utils.enums import ComponentType

CERTIFICATE_TYPE = "Inspection certificate type 3.1 (EN 10204:2004)"
SAMPLE_NOTICE = (
    "Sample certificate: replaced by the manufacturer's issued certificate when "
    "supplier data is connected."
)

#: Rated speed of the reference lift (m/s) - the governor is tested against it.
RATED_SPEED = 1.6

_PLANT_CODES = {
    "Chennai Plant": "CHN",
    "Hyvinkaa Plant": "HYV",
    "Giessen Plant": "GIE",
    "Pero Plant": "PER",
    "Kunshan Plant": "KSH",
}


def _rng(component_id: str) -> random.Random:
    """Same component, same certificate - on every request and every machine."""
    return random.Random(int(hashlib.sha256(component_id.encode()).hexdigest()[:16], 16))


def _test(name: str, method: str, requirement: str, result: str, unit: str = "") -> Dict[str, Any]:
    return {
        "test": name,
        "method": method,
        "requirement": requirement,
        "result": f"{result} {unit}".strip(),
        "verdict": "Pass",
    }


def _motor_tests(rng: random.Random, grade: Optional[str]) -> List[Dict[str, Any]]:
    # Permitted winding temperature rise by insulation class (IEC 60034-1, resistance method).
    insulation = {"induction_al_class_b": ("B", 80), "pmsm_class_h": ("H", 125)}.get(grade, ("F", 105))
    rise_limit = insulation[1]
    return [
        _test(
            "Winding insulation resistance, 500 V DC, 1 min",
            "IEC 60034-1 / IEEE 43",
            ">= 100 MOhm",
            f"{rng.randint(650, 2400):,}",
            "MOhm",
        ),
        _test(
            "High-voltage withstand test, 1 min",
            "IEC 60034-1 cl. 9.2",
            "No breakdown at test voltage",
            "Withstood, no breakdown",
        ),
        _test(
            "Winding resistance unbalance between phases",
            "IEC 60034-1",
            "<= 2.0 %",
            f"{rng.uniform(0.2, 1.1):.1f}",
            "%",
        ),
        _test(
            f"Temperature rise at rated load (insulation class {insulation[0]})",
            "IEC 60034-1 cl. 8, resistance method",
            f"<= {rise_limit} K",
            f"{rng.randint(round(rise_limit * 0.62), round(rise_limit * 0.85))}",
            "K",
        ),
        _test(
            "Vibration velocity, no load",
            "IEC 60034-14, grade A",
            "<= 1.6 mm/s RMS",
            f"{rng.uniform(0.5, 1.2):.2f}",
            "mm/s RMS",
        ),
        _test(
            "Bearing noise and run-out check",
            "Manufacturer's routine test",
            "No abnormal noise; run-out within drawing",
            "Conforms",
        ),
    ]


def _rope_tests(rng: random.Random, grade: Optional[str]) -> List[Dict[str, Any]]:
    tensile = {"steel_fibre_core": 1570, "steel_iwrc": 1770, "steel_compacted_iwrc": 1770}.get(grade, 1570)
    nominal = 10.0
    return [
        _test(
            "Actual rope diameter, measured under tension",
            "EN 12385-1 / EN 12385-5",
            f"Nominal {nominal:.1f} mm, within lift-rope tolerance",
            f"{nominal * rng.uniform(1.012, 1.035):.2f}",
            "mm",
        ),
        _test(
            "Breaking-force test on rope sample",
            "EN 12385-1, determination of breaking force",
            ">= minimum breaking force for the construction",
            f"Actual / minimum = {rng.uniform(1.04, 1.14):.2f}",
        ),
        _test(
            "Wire tensile strength",
            "EN 10264-2",
            f">= {tensile} N/mm2 (rope grade)",
            f"{tensile + rng.randint(40, 190):,}",
            "N/mm2",
        ),
        _test(
            "Wire torsion test",
            "EN 10264-2",
            ">= specified number of torsions, no fracture",
            "Conforms",
        ),
        _test(
            "Lay length, lay direction and lubrication",
            "EN 12385-5",
            "As designated; lubricated throughout",
            "Conforms",
        ),
    ]


def _sheave_tests(rng: random.Random, grade: Optional[str]) -> List[Dict[str, Any]]:
    if grade == "hardened_steel":
        hardness = ("Groove surface hardness", "ISO 6508-1 (Rockwell C)", "40 - 50 HRC", f"{rng.randint(43, 48)}", "HRC")
        tensile = ("Tensile strength, test bar", "ISO 6892-1", ">= 900 MPa (42CrMo4+QT)", f"{rng.randint(930, 1060)}", "MPa")
    elif grade == "grey_iron":
        hardness = ("Groove hardness", "ISO 6506-1 (Brinell)", "180 - 220 HB", f"{rng.randint(190, 214)}", "HB")
        tensile = ("Tensile strength, separately cast test bar", "EN 1561", ">= 250 MPa (EN-GJL-250)", f"{rng.randint(262, 298)}", "MPa")
    else:
        hardness = ("Groove hardness", "ISO 6506-1 (Brinell)", "200 - 270 HB", f"{rng.randint(215, 255)}", "HB")
        tensile = ("Tensile strength, separately cast test bar", "EN 1563", ">= 600 MPa, >= 3 % elongation (EN-GJS-600-3)", f"{rng.randint(615, 690)}", "MPa")
    return [
        _test(*hardness),
        _test(*tensile),
        _test(
            "Groove profile and pitch-diameter check",
            "Manufacturer's groove gauge",
            "All grooves within gauge; depth difference <= 0.1 mm",
            f"Max. depth difference {rng.uniform(0.02, 0.07):.2f} mm",
        ),
        _test(
            "Surface crack inspection, rim and spokes",
            "ISO 3452-1 (penetrant testing)",
            "No relevant indications",
            "No relevant indications",
        ),
        _test(
            "Balance quality",
            "ISO 21940-11",
            "G 6.3",
            "Within G 6.3",
        ),
    ]


def _governor_tests(rng: random.Random, grade: Optional[str]) -> List[Dict[str, Any]]:
    # EN 81-20:2020 5.6.2.2.1: trip at >= 115 % of rated speed and, for
    # progressive safety gear, below 1.25 v + 0.25 / v.
    lower = 1.15 * RATED_SPEED
    upper = 1.25 * RATED_SPEED + 0.25 / RATED_SPEED
    tripping = rng.uniform(lower + 0.04, upper - 0.08)
    return [
        _test(
            "Mechanical tripping speed",
            "EN 81-20 cl. 5.6.2.2.1 / EN 81-50 cl. 5.3",
            f"{lower:.2f} - {upper:.2f} m/s (rated {RATED_SPEED} m/s)",
            f"{tripping:.2f} m/s ({tripping / RATED_SPEED:.0%} of rated)",
        ),
        _test(
            "Electrical overspeed switch operates before mechanical trip",
            "EN 81-20 cl. 5.6.2.2.1",
            "Switch opens the safety chain first",
            f"Opened at {tripping - rng.uniform(0.05, 0.10):.2f} m/s",
        ),
        _test(
            "Tensile force in the governor rope on tripping",
            "EN 81-20 cl. 5.6.2.2.1",
            ">= 300 N and >= 2 x force to engage the safety gear",
            f"{rng.randint(560, 780)}",
            "N",
        ),
        _test(
            "Governor rope",
            "EN 81-20 cl. 5.6.2.2 / EN 12385-5",
            "Nominal diameter >= 6 mm, safety factor >= 8",
            "Conforms",
        ),
        _test(
            "Rope-gripping jaw and tripping linkage function",
            "Manufacturer's routine test",
            "Jaw arrests the rope on every trip; linkage free",
            "Conforms, 3 of 3 trips",
        ),
    ]


_TESTS = {
    ComponentType.MOTOR.value: _motor_tests,
    ComponentType.STEEL_ROPE.value: _rope_tests,
    ComponentType.SHEAVE.value: _sheave_tests,
    ComponentType.GOVERNOR.value: _governor_tests,
}

_TYPE_EXAMINATION = {
    ComponentType.GOVERNOR.value: "EN 81-50 cl. 5.3 type examination of the overspeed governor",
    ComponentType.STEEL_ROPE.value: "EN 12385-5 conformity of lift ropes",
}


def build(component: Any) -> Optional[Dict[str, Any]]:
    """The manufacturer's quality certificate for one component, or None if unsupported."""
    component_type = str(component.component_type)
    tests_for = _TESTS.get(component_type)
    if tests_for is None:
        return None

    rng = _rng(component.component_id)
    profile = life_model.material_profile(component) or {}
    grade = profile.get("grade")
    origin = component.origin or "Manufacturing plant"
    plant_code = _PLANT_CODES.get(origin, "MFG")
    issue_date = (
        component.installation_date - timedelta(days=rng.randint(35, 110))
        if component.installation_date
        else None
    )
    year = issue_date.year if issue_date else "0000"
    certificate_no = f"QC-{plant_code}-{year}-{rng.randint(10000, 99999)}"
    heat_or_lot = f"{plant_code}{rng.randint(100000, 999999)}"

    return {
        "certificate_type": CERTIFICATE_TYPE,
        "certificate_no": certificate_no,
        "issued_by": f"{component.manufacturer or 'Manufacturer'} - {origin}, Quality Assurance",
        "date_of_issue": issue_date.isoformat() if issue_date else None,
        "issued_for": "Dispatch inspection before installation",
        "product": {
            "component_type": component_type,
            "component_id": component.component_id,
            "serial_number": component.serial_number,
            "material": component.material,
            "grade": profile.get("designation"),
            "grade_label": profile.get("grade_label"),
            "heat_or_lot_no": heat_or_lot,
        },
        "materials": [
            {"part": row["part"], "grade": row["grade"], "standard": row["standard"]}
            for row in profile.get("specifications") or []
        ],
        "tests": tests_for(rng, grade),
        "type_examination": _TYPE_EXAMINATION.get(component_type),
        "conformity_statement": (
            "We certify that the product described above has been inspected and tested "
            "in accordance with the order and the standards cited, and that the results "
            "conform to the stated requirements."
        ),
        "inspector": "Authorised inspection representative, independent of manufacturing (EN 10204 3.1)",
        "verdict": "Conforms",
        "notice": SAMPLE_NOTICE,
    }
