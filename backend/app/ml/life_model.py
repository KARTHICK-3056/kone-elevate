"""Usage-adjusted life model for every component type in the registry.

What this answers that the classifier does not
----------------------------------------------
The Random Forest answers "what should happen to this part **now**". The
survival model answers "how many parts will the **fleet** need, and when".
Neither answers the two questions a reviewer asks first:

1. *On what basis is this component's life determined?*
2. *How has the way it has actually been used changed that life?*

This module answers both, per component, in a form a maintenance engineer
can check with a calculator. It is a **physics-of-failure style damage
model** (Miner's-rule life consumption), not a learned one, and it is
deliberately kept separate from the ML path: it is a cross-check and a
pre-emptive planning signal, never a model input and never an override of the
safety gate.

The model in one line
---------------------
::

    life consumed  D = calendar_age x ageing_rate / (design_life x material_factor)

* ``design_life`` - the type's nominal life at *design* duty
  (``app.ml.features.TYPE_REFERENCE``).
* ``material_factor`` - how much longer or shorter the specific material
  grade lasts than the reference grade (a hardened-steel sheave groove
  outlasts a grey-iron one; a polymer-composite brake lining wears faster than
  a sintered metallic one). See :data:`MATERIAL_GRADES`.
* ``ageing_rate`` - how many design-years of life the component consumes per
  calendar year, given how it is **actually** used::

      ageing_rate = (time_share + (1 - time_share) x duty x load)
                    x thermal x vibration x maintenance

  ``time_share`` is the part of ageing that happens whether or not the lift
  moves (corrosion, lubricant and insulation ageing). The rest scales with use.

``D = 0`` is new, ``D = 1`` is the end of the usage-adjusted design life. The
disposition bands on the passport chart are drawn on ``D``:

* ``D < 0.5``   green  - suitable to continue in its current application
* ``0.5 - 0.8`` amber  - past half its life: if removed, its sub-components
                         are still worth recovering (component recovery)
* ``D >= 0.8``  red    - replace; recover the material

Evidence beats the model
------------------------
A usage model can only see what is metered. A recorded inspection sees the
part. ``D`` is therefore also estimated from the inspection score, and the
**worse** of the two governs - the same conservative direction
``app/ml/cost_matrix.py`` prices highest. When the two disagree strongly the
result says so, because that disagreement is itself a finding.

PROTOTYPE VALUES
----------------
Every exponent, factor and threshold below is a documented engineering
approximation chosen for a prototype - not a KONE specification and not
calibrated against real removals. Each one carries its reasoning so an
engineer can disagree with a specific number. See ``docs/life-model.md``.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

from app.ml.features import reference_for
from app.utils.enums import (
    ComponentType,
    Material,
    Recommendation,
    is_safety_critical,
    recommendation_label,
)
from app.utils.helpers import utcnow

#: The components covered by the life model: the four drivetrain components
#: the mentor review asked to focus on first, and the
#: overspeed governor and door operator - every type in the registry, so every
#: passport states an expected life. A type added later without a mechanism
#: returns ``supported: False`` rather than a number with nothing behind it.
FOCUS_TYPES: Tuple[str, ...] = (
    ComponentType.MOTOR.value,
    ComponentType.STEEL_ROPE.value,
    ComponentType.SHEAVE.value,
    ComponentType.BRAKE.value,
    ComponentType.GOVERNOR.value,
    ComponentType.DOOR_OPERATOR.value,
)

#: Life-consumed thresholds that bound the three passport bands.
SUITABLE_LIMIT = 0.5
REPLACE_LIMIT = 0.8
END_OF_LIFE = 1.0

#: Average load as a share of rated load that the design life assumes. Lift
#: cars run well below rated load most of the time; this is the duty at which
#: the nominal design life is quoted.
REFERENCE_UTILISATION = 0.6

#: Recommended interval between maintenance visits the model treats as
#: "on schedule". Prototype assumption.
SERVICE_INTERVAL_DAYS = 180

#: Below this age, cumulative counters are too short a window to turn into a
#: reliable annual usage rate, so the duty factor is held at design duty.
MIN_AGE_FOR_RATE_YEARS = 0.5

#: Bounds that stop one extreme reading dominating the whole projection.
_DUTY_BOUNDS = (0.2, 3.0)
_LOAD_BOUNDS = (0.4, 3.0)
#: The thermal floor is deliberately close to 1: running cool buys a little
#: life, but an unmeasured temperature defaults to 25 C and must not be able
#: to claim a large life extension on its own.
_THERMAL_BOUNDS = (0.8, 4.0)
_RATE_BOUNDS = (0.25, 5.0)

#: Inspection score to life consumed: 100 -> 0, 67.5 -> 0.5, 48 -> 0.8, 35 -> 1.0.
_INSPECTION_SCALE = 65.0

#: A gap this large between the usage model and the inspection is reported.
_DIVERGENCE = 0.25

#: Grading scatter of an inspection score, on the life-consumed scale
#: (about 7.5 score points between inspectors). The inspection overrides the
#: usage model only when it shows more wear than the model by more than this:
#: always taking the larger of two noisy estimates biases life upwards.
_INSPECTION_SCATTER = 0.12


def inspection_life_consumed(inspection_score: float) -> float:
    """Inspection score -> life consumed.

    Uses the fitted mapping (``life_calibration``) when one exists - new parts
    do not score 100 in practice - otherwise the documented default scale
    (100 = new, 35 = end of life).
    """
    from app.ml import life_calibration

    mapping = life_calibration.inspection_mapping()
    if mapping:
        consumed = (mapping["intercept"] - inspection_score) / mapping["slope"]
    else:
        consumed = (100.0 - inspection_score) / _INSPECTION_SCALE
    return min(max(consumed, 0.0), 1.5)


def inspection_override_margin() -> float:
    """How much more wear an inspection must show before it overrides usage.

    One-sided 95% of the inspection's fitted grading scatter when calibrated
    (1.645 sd), else the documented default. Anything smaller lets grading
    noise alone override the usage estimate - biasing life upwards.
    """
    from app.ml import life_calibration

    mapping = life_calibration.inspection_mapping()
    if mapping and mapping.get("scatter"):
        return 1.645 * float(mapping["scatter"])
    return _INSPECTION_SCATTER


def reference_utilisation(component_type: str) -> float:
    """Load (share of rated) at which the design life holds - fitted from fleet
    data when a calibration exists (``app.ml.life_calibration``)."""
    from app.ml import life_calibration

    return float(life_calibration.for_type(component_type).get("reference_utilisation") or REFERENCE_UTILISATION)


def service_interval_days(component_type: str) -> float:
    """Typical days between services for the type - fitted when calibrated."""
    from app.ml import life_calibration

    return float(life_calibration.for_type(component_type).get("service_interval_days") or SERVICE_INTERVAL_DAYS)


# --------------------------------------------------------------------------
# Material grades - what each component is made of, and what that does to life
# --------------------------------------------------------------------------
def _grade(
    label: str,
    materials: List[str],
    life_factor: float,
    constituents: List[Tuple[Any, ...]],
    properties: List[Tuple[str, str]],
    life_reasoning: str,
    material_recoverability: str,
    *,
    designation: str,
    grading_system: str,
    equivalent: Optional[str],
    specifications: List[Tuple[str, str, str, Optional[str]]],
) -> Dict[str, Any]:
    return {
        "label": label,
        #: Headline grade and the standard it is graded under, e.g.
        #: "EN-GJS-600-3" under EN 1563. Typical for the construction - the
        #: actual part's grade comes from its nameplate or bill of materials.
        "designation": designation,
        "grading_system": grading_system,
        "equivalent": equivalent,
        #: Per-part grades, since most components are assemblies of several
        #: graded materials: (part, grade, standard, equivalent or None).
        "specifications": [
            {"part": part, "grade": grade, "standard": standard, "equivalent": equiv}
            for part, grade, standard, equiv in specifications
        ],
        "materials": materials,
        "life_factor": life_factor,
        # A fourth element True marks a separable sub-component that can be
        # recovered individually under Component Recovery.
        "constituents": [
            {
                "name": item[0],
                "mass_fraction": item[1],
                "role": item[2],
                "separable": bool(item[3]) if len(item) > 3 else False,
            }
            for item in constituents
        ],
        "properties": [{"property": name, "value": value} for name, value in properties],
        "life_reasoning": life_reasoning,
        "material_recoverability": material_recoverability,
    }


#: Per-type material grades. ``life_factor`` multiplies the design life:
#: 1.0 is the reference grade the design life is quoted for. Constituent mass
#: fractions are illustrative bills of materials, not supplier data.
MATERIAL_GRADES: Dict[str, Dict[str, Dict[str, Any]]] = {
    ComponentType.MOTOR.value: {
        "pmsm_class_f": _grade(
            "Permanent-magnet synchronous (gearless), Class F insulation",
            [Material.STEEL.value, Material.COPPER.value],
            1.0,
            [
                ("Electrical steel laminations", 0.42, "Stator and rotor magnetic core"),
                ("Structural steel / cast frame", 0.33, "Housing, shaft, sheave hub"),
                ("Copper windings", 0.15, "Stator coils"),
                ("NdFeB permanent magnets", 0.03, "Rotor field - critical raw material"),
                ("Bearings", 0.04, "Rotating support", True),
                ("Varnish and winding insulation", 0.03, "Electrical insulation"),
            ],
            [
                ("Insulation thermal class", "F (155 C)"),
                ("Dominant wear parts", "Bearings, winding insulation"),
                ("Corrosion resistance", "Good (painted / sealed housing)"),
            ],
            "Reference grade. Life is limited by bearing fatigue (ISO 281) and by "
            "thermal ageing of the winding insulation.",
            "High - steel and copper recover well; magnets need a specialist route.",
            designation='M270-50A core, 42CrMo4 shaft, class F',
            grading_system='EN 10106 electrical steel; EN 10083-3 shaft steel; IEC 60085 thermal class',
            equivalent='Shaft AISI 4140; bearings AISI 52100',
            specifications=[
                ('Stator / rotor laminations', 'M270-50A', 'EN 10106 non-oriented electrical steel', None),
                ('Shaft', '42CrMo4+QT', 'EN 10083-3 alloy steel, quenched and tempered', 'AISI 4140'),
                ('Frame', 'EN-GJS-400-15', 'EN 1563 spheroidal graphite cast iron', 'ASTM A536 60-40-18'),
                ('Windings', 'Cu-ETP enamelled wire, grade 2', 'EN 13601 / IEC 60317', 'UNS C11000'),
                ('Permanent magnets', 'Sintered NdFeB N42SH', 'IEC 60404-8-1 hard magnetic materials', None),
                ('Bearings', '100Cr6', 'ISO 683-17 bearing steel', 'AISI 52100'),
                ('Insulation system', 'Class F (155 C)', 'IEC 60085', None),
            ],
        ),
        "pmsm_class_h": _grade(
            "Permanent-magnet synchronous (gearless), Class H insulation",
            [Material.STEEL.value, Material.COPPER.value],
            1.2,
            [
                ("Electrical steel laminations", 0.42, "Stator and rotor magnetic core"),
                ("Structural steel / cast frame", 0.33, "Housing, shaft, sheave hub"),
                ("Copper windings", 0.15, "Stator coils"),
                ("NdFeB permanent magnets", 0.03, "Rotor field - critical raw material"),
                ("Bearings", 0.04, "Rotating support", True),
                ("Varnish and winding insulation", 0.03, "Class H insulation system"),
            ],
            [
                ("Insulation thermal class", "H (180 C)"),
                ("Dominant wear parts", "Bearings"),
                ("Corrosion resistance", "Good"),
            ],
            "25 K more thermal headroom than Class F. By the 10 K rule that more "
            "than doubles insulation life, but bearings still limit the machine, "
            "so the net gain is modest.",
            "High - as Class F.",
            designation='M270-50A core, 42CrMo4 shaft, class H',
            grading_system='EN 10106 electrical steel; EN 10083-3 shaft steel; IEC 60085 thermal class',
            equivalent='Shaft AISI 4140; bearings AISI 52100',
            specifications=[
                ('Stator / rotor laminations', 'M270-50A', 'EN 10106 non-oriented electrical steel', None),
                ('Shaft', '42CrMo4+QT', 'EN 10083-3 alloy steel, quenched and tempered', 'AISI 4140'),
                ('Frame', 'EN-GJS-400-15', 'EN 1563 spheroidal graphite cast iron', 'ASTM A536 60-40-18'),
                ('Windings', 'Cu-ETP enamelled wire, grade 2', 'EN 13601 / IEC 60317', 'UNS C11000'),
                ('Permanent magnets', 'Sintered NdFeB N42UH', 'IEC 60404-8-1 hard magnetic materials', None),
                ('Bearings', '100Cr6', 'ISO 683-17 bearing steel', 'AISI 52100'),
                ('Insulation system', 'Class H (180 C)', 'IEC 60085', None),
            ],
        ),
        "induction_cu_class_f": _grade(
            "Induction motor, copper winding, Class F",
            [Material.STEEL.value, Material.COPPER.value],
            0.95,
            [
                ("Electrical steel laminations", 0.45, "Magnetic core"),
                ("Cast iron / steel frame", 0.30, "Housing and end shields"),
                ("Copper windings", 0.17, "Stator coils"),
                ("Aluminium rotor cage", 0.03, "Squirrel-cage rotor"),
                ("Bearings", 0.03, "Rotating support", True),
                ("Varnish and winding insulation", 0.02, "Electrical insulation"),
            ],
            [
                ("Insulation thermal class", "F (155 C)"),
                ("Dominant wear parts", "Bearings, insulation, geared drive if fitted"),
                ("Corrosion resistance", "Good"),
            ],
            "Runs hotter per unit of output than a PM machine (rotor losses), so "
            "insulation ages slightly faster at the same duty.",
            "High - steel, copper and aluminium all recover.",
            designation='M400-50A core, C45E shaft, class F',
            grading_system='EN 10106 electrical steel; EN 10083-2 shaft steel; IEC 60085 thermal class',
            equivalent='Shaft AISI 1045; frame ASTM A48 Class 40',
            specifications=[
                ('Stator / rotor laminations', 'M400-50A', 'EN 10106 non-oriented electrical steel', None),
                ('Shaft', 'C45E+QT', 'EN 10083-2 non-alloy steel, quenched and tempered', 'AISI 1045'),
                ('Frame', 'EN-GJL-250', 'EN 1561 grey cast iron', 'ASTM A48 Class 40'),
                ('Windings', 'Cu-ETP enamelled wire, grade 2', 'EN 13601 / IEC 60317', 'UNS C11000'),
                ('Rotor cage', 'Al 99.7, die-cast', 'EN 576 unalloyed aluminium', None),
                ('Bearings', '100Cr6', 'ISO 683-17 bearing steel', 'AISI 52100'),
                ('Insulation system', 'Class F (155 C)', 'IEC 60085', None),
            ],
        ),
        "induction_al_class_b": _grade(
            "Induction motor, aluminium winding / frame, Class B",
            [Material.ALUMINUM.value],
            0.8,
            [
                ("Electrical steel laminations", 0.48, "Magnetic core"),
                ("Aluminium frame", 0.25, "Housing"),
                ("Aluminium windings", 0.18, "Stator coils"),
                ("Bearings", 0.05, "Rotating support", True),
                ("Varnish and winding insulation", 0.04, "Electrical insulation"),
            ],
            [
                ("Insulation thermal class", "B (130 C)"),
                ("Dominant wear parts", "Insulation, winding joints"),
                ("Corrosion resistance", "Moderate"),
            ],
            "25 K less thermal headroom than Class F, and aluminium windings run "
            "hotter for the same current - thermal ageing dominates earlier.",
            "High - aluminium and steel recover well.",
            designation='M600-50A core, C45E shaft, class B',
            grading_system='EN 10106 electrical steel; EN 10083-2 shaft steel; IEC 60085 thermal class',
            equivalent='Shaft AISI 1045; windings AA 1350',
            specifications=[
                ('Stator / rotor laminations', 'M600-50A', 'EN 10106 non-oriented electrical steel', None),
                ('Shaft', 'C45E+QT', 'EN 10083-2 non-alloy steel, quenched and tempered', 'AISI 1045'),
                ('Frame', 'EN AC-44300 (AlSi12(Fe))', 'EN 1706 aluminium casting alloy', 'A413.0'),
                ('Windings', 'EN AW-1370 enamelled wire', 'EN 573-3 electrical-conductor aluminium', 'AA 1350'),
                ('Bearings', '100Cr6', 'ISO 683-17 bearing steel', 'AISI 52100'),
                ('Insulation system', 'Class B (130 C)', 'IEC 60085', None),
            ],
        ),
    },
    ComponentType.STEEL_ROPE.value: {
        "steel_fibre_core": _grade(
            "Steel wire rope, 8-strand, fibre core",
            [Material.STEEL.value],
            1.0,
            [
                ("High-carbon steel wire", 0.90, "Load-bearing outer strands"),
                ("Fibre core (sisal / polypropylene)", 0.07, "Supports strands, holds lubricant"),
                ("Lubricant", 0.03, "Reduces inter-wire friction and corrosion"),
            ],
            [
                ("Wire tensile grade", "1570 / 1770 N/mm2 (dual tensile)"),
                ("Dominant wear mechanism", "Bending fatigue over the sheave"),
                ("Corrosion resistance", "Depends on lubrication"),
            ],
            "Reference grade. Life is set by the number of bends over the traction "
            "sheave under tension; the fibre core compresses with age, which "
            "shortens the rope and loosens the strands.",
            "High - the steel wire is recovered as scrap steel. A rope has no separable sub-components.",
            designation='8x19S-FC 1570/1770',
            grading_system='EN 12385-5 stranded ropes for lifts; wire tensile grade per EN 10264-2',
            equivalent='ISO 4344 lift rope, dual tensile',
            specifications=[
                ('Construction', '8x19 Seale, fibre core (8x19S-FC)', 'EN 12385-2 rope designation', None),
                ('Outer wires', 'Rope grade 1570 / 1770 N/mm2, bright', 'EN 10264-2 non-alloy steel wire', None),
                ('Core', 'Natural / synthetic fibre core (NFC / SFC)', 'EN 12385-2', None),
                ('Lubricant', 'Lift-rope lubricant', 'EN 12385-5 lubrication requirements', None),
            ],
        ),
        "steel_iwrc": _grade(
            "Steel wire rope, 8-strand, independent wire rope core (IWRC)",
            [Material.STEEL.value],
            1.15,
            [
                ("High-carbon steel wire", 0.95, "Outer strands and steel core"),
                ("Lubricant", 0.05, "Reduces inter-wire friction and corrosion"),
            ],
            [
                ("Wire tensile grade", "1770 N/mm2"),
                ("Dominant wear mechanism", "Bending fatigue, less core crushing"),
                ("Corrosion resistance", "Depends on lubrication"),
            ],
            "A steel core does not compress, so the rope elongates less and the "
            "strands stay supported for longer.",
            "High - all-steel, a clean material-recovery stream.",
            designation='8x19S-IWRC 1770',
            grading_system='EN 12385-5 stranded ropes for lifts; wire tensile grade per EN 10264-2',
            equivalent='ISO 4344 lift rope',
            specifications=[
                ('Construction', '8x19 Seale, independent wire rope core (8x19S-IWRC)', 'EN 12385-2 rope designation', None),
                ('Outer wires', 'Rope grade 1770 N/mm2, bright', 'EN 10264-2 non-alloy steel wire', None),
                ('Core', 'IWRC 7x7', 'EN 12385-2', None),
                ('Lubricant', 'Lift-rope lubricant', 'EN 12385-5 lubrication requirements', None),
            ],
        ),
        "steel_compacted_iwrc": _grade(
            "Steel wire rope, compacted strands, IWRC",
            [Material.STEEL.value],
            1.3,
            [
                ("High-carbon steel wire (compacted)", 0.96, "Load-bearing strands"),
                ("Lubricant", 0.04, "Reduces inter-wire friction"),
            ],
            [
                ("Wire tensile grade", "1770 / 1960 N/mm2"),
                ("Dominant wear mechanism", "Bending fatigue"),
                ("Corrosion resistance", "Good (smoother surface holds lubricant)"),
            ],
            "Compacting gives a smoother outer surface and more contact area on "
            "the groove, which lowers contact pressure and wire-on-wire wear.",
            "High - all-steel.",
            designation='8xK19S-IWRC 1770/1960',
            grading_system='EN 12385-5 stranded ropes for lifts; wire tensile grade per EN 10264-2',
            equivalent='ISO 4344 lift rope, compacted strand',
            specifications=[
                ('Construction', '8x19 Seale, compacted strands, IWRC (8xK19S-IWRC)', 'EN 12385-2 rope designation', None),
                ('Outer wires', 'Rope grade 1770 / 1960 N/mm2', 'EN 10264-2 non-alloy steel wire', None),
                ('Core', 'IWRC 7x7', 'EN 12385-2', None),
                ('Lubricant', 'Lift-rope lubricant', 'EN 12385-5 lubrication requirements', None),
            ],
        ),
    },
    ComponentType.SHEAVE.value: {
        "ductile_iron": _grade(
            "Ductile (spheroidal graphite) cast iron",
            [Material.CAST_IRON.value],
            1.0,
            [
                ("Ductile cast iron", 0.94, "Sheave body and grooves"),
                ("Steel hub / bearing seat", 0.05, "Mounting to the machine shaft", True),
                ("Paint / corrosion protection", 0.01, "Surface protection"),
            ],
            [
                ("Typical hardness", "about 200-270 HB"),
                ("Dominant wear mechanism", "Groove wear from rope creep and slip"),
                ("Fatigue behaviour", "Good - graphite nodules resist cracking"),
            ],
            "Reference grade. Groove wear follows Archard's law: wear rate "
            "rises with contact pressure and falls with groove hardness.",
            "High - cast iron is remelted.",
            designation='EN-GJS-600-3',
            grading_system='EN 1563 spheroidal graphite cast iron (min. 600 MPa tensile, 3% elongation)',
            equivalent='ASTM A536 80-55-06',
            specifications=[
                ('Sheave body and grooves', 'EN-GJS-600-3', 'EN 1563 spheroidal graphite cast iron', 'ASTM A536 80-55-06'),
                ('Hub / bearing seat', 'C45E+N', 'EN 10083-2 non-alloy steel, normalised', 'AISI 1045'),
                ('Corrosion protection', 'Epoxy primer + topcoat, C3', 'ISO 12944-2 corrosivity category', None),
            ],
        ),
        "grey_iron": _grade(
            "Grey (lamellar graphite) cast iron",
            [Material.CAST_IRON.value],
            0.8,
            [
                ("Grey cast iron", 0.95, "Sheave body and grooves"),
                ("Steel hub / bearing seat", 0.04, "Mounting", True),
                ("Paint / corrosion protection", 0.01, "Surface protection"),
            ],
            [
                ("Typical hardness", "about 180-220 HB"),
                ("Dominant wear mechanism", "Groove wear"),
                ("Fatigue behaviour", "Lower - flake graphite concentrates stress"),
            ],
            "Softer grooves wear faster under the same rope pressure, and flake "
            "graphite makes the body less fatigue-tolerant.",
            "High - cast iron is remelted.",
            designation='EN-GJL-250',
            grading_system='EN 1561 grey cast iron (min. 250 MPa tensile)',
            equivalent='ASTM A48 Class 40',
            specifications=[
                ('Sheave body and grooves', 'EN-GJL-250', 'EN 1561 grey cast iron', 'ASTM A48 Class 40'),
                ('Hub / bearing seat', 'C45E+N', 'EN 10083-2 non-alloy steel, normalised', 'AISI 1045'),
                ('Corrosion protection', 'Epoxy primer + topcoat, C3', 'ISO 12944-2 corrosivity category', None),
            ],
        ),
        "hardened_steel": _grade(
            "Steel with induction-hardened grooves",
            [Material.STEEL.value],
            1.3,
            [
                ("Forged / rolled steel", 0.97, "Sheave body"),
                ("Hardened groove layer", 0.02, "Wear surface (same steel, heat-treated)"),
                ("Paint / corrosion protection", 0.01, "Surface protection"),
            ],
            [
                ("Typical groove hardness", "about 40-50 HRC after induction hardening"),
                ("Dominant wear mechanism", "Groove wear (slow)"),
                ("Fatigue behaviour", "Good"),
            ],
            "A much harder groove surface wears slowly, so groove profile - the "
            "usual reason a sheave is retired - lasts longer.",
            "High - steel.",
            designation='42CrMo4+QT',
            grading_system='EN 10083-3 alloy steel, quenched and tempered; grooves induction-hardened',
            equivalent='AISI 4140',
            specifications=[
                ('Sheave body', '42CrMo4+QT', 'EN 10083-3 alloy steel, quenched and tempered', 'AISI 4140'),
                ('Groove surface', 'Induction-hardened case, 40-50 HRC', 'ISO 18203 effective case depth', None),
                ('Corrosion protection', 'Epoxy primer + topcoat, C3', 'ISO 12944-2 corrosivity category', None),
            ],
        ),
    },
    ComponentType.BRAKE.value: {
        "cast_iron_drum_organic": _grade(
            "Cast iron drum / plate with organic friction lining",
            [Material.CAST_IRON.value],
            1.0,
            [
                ("Cast iron drum / armature plate", 0.70, "Friction counter-face and structure"),
                ("Steel springs and levers", 0.18, "Apply force (fail-safe)", True),
                ("Copper coil", 0.06, "Electromagnet that releases the brake", True),
                ("Organic friction lining", 0.06, "Resin-bonded wear surface"),
            ],
            [
                ("Lining type", "Organic, resin-bonded"),
                ("Dominant wear mechanism", "Lining wear per stop; heat fade"),
                ("Temperature tolerance", "Moderate - resin softens when hot"),
            ],
            "Reference grade. Each stop converts kinetic energy into heat in the "
            "lining; heavier cars and hotter linings wear it faster.",
            "Mostly high - iron and steel recover; the organic lining does not.",
            designation='EN-GJL-250 drum, SAE J866 FF lining',
            grading_system='EN 1561 grey cast iron; SAE J866 friction coefficient code',
            equivalent='ASTM A48 Class 40 drum',
            specifications=[
                ('Drum / armature plate', 'EN-GJL-250', 'EN 1561 grey cast iron', 'ASTM A48 Class 40'),
                ('Apply springs', '51CrV4', 'EN 10089 spring steel', 'AISI 6150'),
                ('Release coil', 'Cu-ETP enamelled wire, class F', 'EN 13601 / IEC 60317', 'UNS C11000'),
                ('Friction lining', 'Organic resin-bonded, edge code FF (mu 0.35-0.45)', 'SAE J866', None),
            ],
        ),
        "steel_disc_sintered": _grade(
            "Steel disc / plate with sintered metallic lining",
            [Material.STEEL.value],
            1.3,
            [
                ("Steel disc / armature plate", 0.68, "Friction counter-face and structure"),
                ("Steel springs and levers", 0.18, "Apply force (fail-safe)", True),
                ("Copper coil", 0.06, "Electromagnet", True),
                ("Sintered metallic lining", 0.08, "Copper/iron-based wear surface"),
            ],
            [
                ("Lining type", "Sintered metallic"),
                ("Dominant wear mechanism", "Lining wear per stop (slow)"),
                ("Temperature tolerance", "High"),
            ],
            "A sintered metallic lining keeps its friction and wear rate at "
            "temperatures that soften an organic one.",
            "High - almost entirely metal.",
            designation='C45 disc, SAE J866 GG sintered lining',
            grading_system='EN 10083-2 non-alloy steel; SAE J866 friction coefficient code',
            equivalent='AISI 1045 disc',
            specifications=[
                ('Brake disc', 'C45E+N', 'EN 10083-2 non-alloy steel, normalised', 'AISI 1045'),
                ('Armature plate', 'S235JR', 'EN 10025-2 structural steel', 'ASTM A36'),
                ('Apply springs', '51CrV4', 'EN 10089 spring steel', 'AISI 6150'),
                ('Release coil', 'Cu-ETP enamelled wire, class F', 'EN 13601 / IEC 60317', 'UNS C11000'),
                ('Friction lining', 'Sintered Cu/Fe, edge code GG (mu 0.45-0.55)', 'SAE J866', None),
            ],
        ),
        "composite_lining": _grade(
            "Polymer-composite housing and lining",
            [Material.COMPOSITE.value],
            0.75,
            [
                ("Steel springs and plate", 0.55, "Apply force and counter-face", True),
                ("Polymer composite housing", 0.25, "Lightweight housing"),
                ("Copper coil", 0.07, "Electromagnet", True),
                ("Polymer-composite lining", 0.13, "Wear surface"),
            ],
            [
                ("Lining type", "Polymer composite"),
                ("Dominant wear mechanism", "Lining wear; thermal degradation"),
                ("Temperature tolerance", "Low - polymers soften and glaze"),
            ],
            "The plastic-vs-steel case: polymers wear faster and degrade with "
            "heat, so the same duty uses the life up sooner.",
            "Low - polymer composites have no established material-recovery route; mostly energy recovery.",
            designation='PA66-GF30 housing, SAE J866 EE lining',
            grading_system='ISO 1043-1 plastics designation; SAE J866 friction coefficient code',
            equivalent=None,
            specifications=[
                ('Housing', 'PA66-GF30', 'ISO 1043-1 / ISO 16396 polyamide, 30% glass fibre', None),
                ('Counter-face plate', 'S235JR', 'EN 10025-2 structural steel', 'ASTM A36'),
                ('Apply springs', '51CrV4', 'EN 10089 spring steel', 'AISI 6150'),
                ('Release coil', 'Cu-ETP enamelled wire, class F', 'EN 13601 / IEC 60317', 'UNS C11000'),
                ('Friction lining', 'Polymer composite, edge code EE (mu 0.25-0.35)', 'SAE J866', None),
            ],
        ),
    },
    ComponentType.GOVERNOR.value: {
        "cast_iron_centrifugal": _grade(
            "Centrifugal overspeed governor, cast-iron sheave and flyweights",
            [Material.CAST_IRON.value],
            1.0,
            [
                ("Cast iron governor sheave", 0.42, "Carries the governor rope; groove sets the tripping speed"),
                ("Steel frame and base", 0.24, "Structure and mounting"),
                ("Flyweights, springs and tripping linkage", 0.18, "Detects overspeed and trips", True),
                ("Rope-gripping jaw", 0.06, "Stops the governor rope to set the safety gear", True),
                ("Bearings", 0.05, "Sheave support", True),
                ("Overspeed switch", 0.05, "Opens the safety chain before tripping", True),
            ],
            [
                ("Standard", "EN 81-20/50 overspeed governor, type-examined"),
                ("Dominant wear mechanism", "Groove wear; pivot and spring wear; tripping mechanism sticking"),
                ("Corrosion resistance", "Moderate (painted cast iron)"),
            ],
            "Reference grade. The governor runs with the car, so its sheave groove wears "
            "with travel; the tripping linkage ages whether or not it is used, because "
            "pivots corrode and springs relax between periodic tripping tests.",
            "High - cast iron and steel recover well.",
            designation='EN-GJL-250 sheave',
            grading_system='EN 1561 grey cast iron; EN 81-50 5.3 type examination',
            equivalent='ASTM A48 Class 40 sheave',
            specifications=[
                ('Governor sheave', 'EN-GJL-250', 'EN 1561 grey cast iron', 'ASTM A48 Class 40'),
                ('Frame and base', 'S235JR', 'EN 10025-2 structural steel', 'ASTM A36'),
                ('Flyweights', 'EN-GJS-400-15', 'EN 1563 spheroidal graphite cast iron', 'ASTM A536 60-40-18'),
                ('Trip springs', 'EN 10270-1 SH', 'EN 10270-1 patented cold-drawn spring wire', None),
                ('Pivot pins', 'X8CrNiS18-9 (1.4305)', 'EN 10088-3 stainless steel', 'AISI 303'),
                ('Bearings', '100Cr6', 'ISO 683-17 bearing steel', 'AISI 52100'),
                ('Governor rope (fitted)', '6x19S-FC 1770', 'EN 12385-5 stranded rope for lifts', None),
            ],
        ),
        "steel_centrifugal": _grade(
            "Centrifugal overspeed governor, machined steel sheave",
            [Material.STEEL.value],
            1.1,
            [
                ("Machined steel governor sheave", 0.40, "Harder groove, slower wear"),
                ("Steel frame and base", 0.26, "Structure and mounting"),
                ("Flyweights, springs and tripping linkage", 0.18, "Detects overspeed and trips", True),
                ("Rope-gripping jaw", 0.06, "Stops the governor rope", True),
                ("Bearings", 0.05, "Sheave support", True),
                ("Overspeed switch", 0.05, "Opens the safety chain", True),
            ],
            [
                ("Standard", "EN 81-20/50 overspeed governor, type-examined"),
                ("Dominant wear mechanism", "Pivot and spring wear (groove wear slow)"),
                ("Corrosion resistance", "Moderate"),
            ],
            "A steel groove is harder than cast iron, so the tripping speed drifts more "
            "slowly with groove wear.",
            "High - almost entirely steel.",
            designation='C45E+QT sheave',
            grading_system='EN 10083-2 non-alloy steel, quenched and tempered; EN 81-50 5.3 type examination',
            equivalent='AISI 1045 sheave',
            specifications=[
                ('Governor sheave', 'C45E+QT', 'EN 10083-2 non-alloy steel, quenched and tempered', 'AISI 1045'),
                ('Frame and base', 'S235JR', 'EN 10025-2 structural steel', 'ASTM A36'),
                ('Flyweights', 'C45E+QT', 'EN 10083-2 non-alloy steel', 'AISI 1045'),
                ('Trip springs', 'EN 10270-1 SH', 'EN 10270-1 patented cold-drawn spring wire', None),
                ('Pivot pins', 'X8CrNiS18-9 (1.4305)', 'EN 10088-3 stainless steel', 'AISI 303'),
                ('Bearings', '100Cr6', 'ISO 683-17 bearing steel', 'AISI 52100'),
                ('Governor rope (fitted)', '6x19S-FC 1770', 'EN 12385-5 stranded rope for lifts', None),
            ],
        ),
        "aluminium_compact": _grade(
            "Compact overspeed governor, aluminium housing",
            [Material.ALUMINUM.value],
            0.9,
            [
                ("Aluminium housing", 0.38, "Lightweight structure"),
                ("Steel sheave insert", 0.22, "Rope groove"),
                ("Flyweights, springs and tripping linkage", 0.22, "Detects overspeed and trips", True),
                ("Rope-gripping jaw", 0.08, "Stops the governor rope", True),
                ("Bearings", 0.05, "Sheave support", True),
                ("Overspeed switch", 0.05, "Opens the safety chain", True),
            ],
            [
                ("Standard", "EN 81-20/50 overspeed governor, type-examined"),
                ("Dominant wear mechanism", "Groove insert wear; housing wear at bearing seats"),
                ("Corrosion resistance", "Good"),
            ],
            "Lighter construction with smaller bearings and a groove insert that wears "
            "sooner at the same travel.",
            "High - aluminium and steel recover well.",
            designation='EN AC-46000 housing',
            grading_system='EN 1706 aluminium casting alloy; EN 81-50 5.3 type examination',
            equivalent='A380 housing',
            specifications=[
                ('Housing', 'EN AC-46000 (AlSi9Cu3(Fe))', 'EN 1706 aluminium casting alloy', 'A380'),
                ('Sheave insert', 'C45E+QT', 'EN 10083-2 non-alloy steel, quenched and tempered', 'AISI 1045'),
                ('Trip springs', 'EN 10270-1 SH', 'EN 10270-1 patented cold-drawn spring wire', None),
                ('Pivot pins', 'X8CrNiS18-9 (1.4305)', 'EN 10088-3 stainless steel', 'AISI 303'),
                ('Bearings', '100Cr6', 'ISO 683-17 bearing steel', 'AISI 52100'),
                ('Governor rope (fitted)', '6x19S-FC 1770', 'EN 12385-5 stranded rope for lifts', None),
            ],
        ),
    },
    ComponentType.DOOR_OPERATOR.value: {
        "aluminium_belt_vvvf": _grade(
            "Door operator, aluminium header and track, belt drive, VVVF motor",
            [Material.ALUMINUM.value],
            1.0,
            [
                ("Aluminium header and track", 0.38, "Structure and running surface"),
                ("Steel hangers, brackets and fixings", 0.18, "Carry the door panels"),
                ("Door operator motor", 0.16, "Drives the doors", True),
                ("Door controller (electronics)", 0.08, "Speed, force and reversal control", True),
                ("Drive belt and pulleys", 0.07, "Transmits motion", True),
                ("Hanger rollers and guides (polymer)", 0.08, "Run on the track", True),
                ("Door lock and contacts", 0.05, "Safety-chain interlock", True),
            ],
            [
                ("Drive", "Toothed belt, variable-speed (VVVF) motor"),
                ("Dominant wear mechanism", "Roller, belt and lock wear per door cycle"),
                ("Corrosion resistance", "Good"),
            ],
            "Reference grade. A door operator is the most-cycled part of a lift: every "
            "stop opens and closes it, so rollers, belt and lock wear with door cycles.",
            "High - aluminium and steel recover; motor and controller go to WEEE.",
            designation='EN AW-6063-T6 header',
            grading_system='EN 573-3 / EN 755-2 aluminium extrusion; ISO 17396 synchronous belt',
            equivalent='AA 6063-T6',
            specifications=[
                ('Header and track', 'EN AW-6063-T6', 'EN 573-3 / EN 755-2 aluminium extrusion', 'AA 6063-T6'),
                ('Hangers and brackets', 'DX51D+Z275', 'EN 10346 hot-dip galvanised steel', 'ASTM A653 CS G90'),
                ('Drive belt', 'Polyurethane AT5, steel cord', 'ISO 17396 synchronous belt', None),
                ('Hanger rollers', 'PA6 / POM-C', 'ISO 1043-1 plastics designation', None),
                ('Door motor', 'Permanent-magnet, VVVF drive', 'IEC 60034-1', None),
                ('Door lock', 'Type-examined locking device', 'EN 81-20 5.3.9 / EN 81-50 5.2', None),
            ],
        ),
        "steel_linkage": _grade(
            "Door operator, steel header, linkage / chain drive",
            [Material.STEEL.value],
            0.9,
            [
                ("Steel header, track and linkage arms", 0.52, "Structure and drive linkage"),
                ("Steel hangers and brackets", 0.14, "Carry the door panels"),
                ("Door operator motor", 0.15, "Drives the doors", True),
                ("Door controller (electronics)", 0.06, "Speed and reversal control", True),
                ("Chain / linkage pivots", 0.05, "Transmit motion", True),
                ("Hanger rollers and guides", 0.05, "Run on the track", True),
                ("Door lock and contacts", 0.03, "Safety-chain interlock", True),
            ],
            [
                ("Drive", "Linkage or chain, often older fixed-speed motor"),
                ("Dominant wear mechanism", "Pivot and chain wear, track wear"),
                ("Corrosion resistance", "Moderate (needs lubrication)"),
            ],
            "More pivots and a chain or linkage to lubricate, so more wear points per door "
            "cycle than a belt drive.",
            "High - mostly steel.",
            designation='S235JR header, ISO 606 chain',
            grading_system='EN 10025-2 structural steel; ISO 606 roller chain',
            equivalent='ASTM A36',
            specifications=[
                ('Header, track and linkage arms', 'S235JR', 'EN 10025-2 structural steel', 'ASTM A36'),
                ('Hangers and brackets', 'S235JR', 'EN 10025-2 structural steel', 'ASTM A36'),
                ('Drive chain', '08B-1 roller chain', 'ISO 606', None),
                ('Linkage pivots', 'C45E+N', 'EN 10083-2 non-alloy steel', 'AISI 1045'),
                ('Door motor', 'Induction, fixed speed', 'IEC 60034-1', None),
                ('Door lock', 'Type-examined locking device', 'EN 81-20 5.3.9 / EN 81-50 5.2', None),
            ],
        ),
        "composite_track": _grade(
            "Door operator, polymer-composite track and header covers",
            [Material.COMPOSITE.value],
            0.8,
            [
                ("Polymer-composite track and covers", 0.34, "Lightweight structure and running surface"),
                ("Steel hangers, brackets and fixings", 0.24, "Carry the door panels", True),
                ("Door operator motor", 0.18, "Drives the doors", True),
                ("Door controller (electronics)", 0.09, "Speed, force and reversal control", True),
                ("Drive belt and pulleys", 0.07, "Transmits motion", True),
                ("Hanger rollers and guides (polymer)", 0.05, "Run on the track", True),
                ("Door lock and contacts", 0.03, "Safety-chain interlock", True),
            ],
            [
                ("Drive", "Toothed belt"),
                ("Dominant wear mechanism", "Track wear and creep; roller wear"),
                ("Corrosion resistance", "Good, but polymers creep and wear with heat"),
            ],
            "A polymer running surface wears and creeps faster than aluminium under the "
            "same number of door cycles.",
            "Low - the composite track has no established material-recovery route; the motor and fixings do.",
            designation='PA66-GF30 track',
            grading_system='ISO 1043-1 / ISO 16396 polyamide; ISO 17396 synchronous belt',
            equivalent=None,
            specifications=[
                ('Track', 'PA66-GF30', 'ISO 1043-1 / ISO 16396 polyamide, 30% glass fibre', None),
                ('Header covers', 'ABS', 'ISO 1043-1 plastics designation', None),
                ('Hangers and brackets', 'DX51D+Z275', 'EN 10346 hot-dip galvanised steel', 'ASTM A653 CS G90'),
                ('Drive belt', 'Polyurethane AT5, steel cord', 'ISO 17396 synchronous belt', None),
                ('Hanger rollers', 'PA6 / POM-C', 'ISO 1043-1 plastics designation', None),
                ('Door lock', 'Type-examined locking device', 'EN 81-20 5.3.9 / EN 81-50 5.2', None),
            ],
        ),
    },
}

#: Shown wherever no grade is on record AND none is catalogued for the material.
GRADE_NOT_DETERMINED = "Not Determined"

#: The industry-standard grade assumed for each (type, material) when no grade
#: is recorded. Where the material allows more than one catalogued grade, the
#: assumed one is the most common in the installed base AND the shortest-lived
#: of them, so an assumption can never flatter a component's life (a test
#: enforces this). It is always labelled as assumed; recording the real grade
#: from the nameplate or bill of materials replaces it.
INDUSTRY_DEFAULT_GRADES: Dict[Tuple[str, str], str] = {
    (ComponentType.MOTOR.value, Material.STEEL.value): "induction_cu_class_f",
    (ComponentType.MOTOR.value, Material.COPPER.value): "induction_cu_class_f",
    (ComponentType.MOTOR.value, Material.ALUMINUM.value): "induction_al_class_b",
    (ComponentType.STEEL_ROPE.value, Material.STEEL.value): "steel_fibre_core",
    (ComponentType.SHEAVE.value, Material.CAST_IRON.value): "grey_iron",
    (ComponentType.SHEAVE.value, Material.STEEL.value): "hardened_steel",
    (ComponentType.BRAKE.value, Material.CAST_IRON.value): "cast_iron_drum_organic",
    (ComponentType.BRAKE.value, Material.STEEL.value): "steel_disc_sintered",
    (ComponentType.BRAKE.value, Material.COMPOSITE.value): "composite_lining",
    (ComponentType.GOVERNOR.value, Material.CAST_IRON.value): "cast_iron_centrifugal",
    (ComponentType.GOVERNOR.value, Material.STEEL.value): "steel_centrifugal",
    (ComponentType.GOVERNOR.value, Material.ALUMINUM.value): "aluminium_compact",
    (ComponentType.DOOR_OPERATOR.value, Material.ALUMINUM.value): "aluminium_belt_vvvf",
    (ComponentType.DOOR_OPERATOR.value, Material.STEEL.value): "steel_linkage",
    (ComponentType.DOOR_OPERATOR.value, Material.COMPOSITE.value): "composite_track",
}

#: Appended to an assumed grade's name wherever it is shown.
INDUSTRY_DEFAULT_SUFFIX = " (industry standard - assumed, not recorded)"


def display_label(grade: Dict[str, Any]) -> str:
    """A grade's name with its formal designation, e.g. "... cast iron — EN-GJS-600-3"."""
    return f"{grade['label']} — {grade['designation']}"


def grade_label(component: Any) -> str:
    """The recorded grade's name; else the industry-standard grade, marked as assumed.

    A stored grade that does not fit the component's type and material is not
    shown (see ``resolve_grade``). "Not Determined" remains only for a
    material with no catalogued grade.
    """
    component_type = str(_get(component, "component_type"))
    key, provenance = resolve_grade(
        component_type,
        str(_get(component, "material")),
        _get(component, "material_grade"),
    )
    if key is None:
        return GRADE_NOT_DETERMINED
    label = display_label(MATERIAL_GRADES[component_type][key])
    return label if provenance == "recorded" else label + INDUSTRY_DEFAULT_SUFFIX


#: Every grade key known to the catalogue, for input validation.
ALL_GRADES = frozenset(key for grades in MATERIAL_GRADES.values() for key in grades)


# --------------------------------------------------------------------------
# Failure mechanisms - how each type actually wears out
# --------------------------------------------------------------------------
#: ``cycle_weight`` - share of usage ageing driven by load cycles (the rest by
#: running hours). ``load_exponent`` - how steeply life falls with load.
#: ``thermal`` - (K below the type's temperature limit at which ageing is
#: nominal, K per doubling) or None where heat is not a dominant mechanism;
#: relative to the limit because the reading is a housing temperature on the
#: type's own scale, not a winding hot-spot. ``discard_criteria`` - what an inspector measures,
#: which no telemetry feed replaces.
MECHANISMS: Dict[str, Dict[str, Any]] = {
    ComponentType.MOTOR.value: {
        "mechanism": "Bearing fatigue and thermal ageing of winding insulation",
        "time_share": 0.25,
        "cycle_weight": 0.35,
        "load_exponent": 1.5,
        "load_basis": (
            "Bearing L10 life falls with the cube of load (ISO 281); the motor "
            "as a whole is less sensitive, so 1.5 is used."
        ),
        "thermal": (10.0, 10.0),
        "thermal_basis": "Insulation life roughly halves for every 10 K of extra heat (Arrhenius / 10 K rule).",
        "vibration_sensitive": True,
        "maintenance_weight": 0.3,
        "discard_criteria": [
            "Insulation resistance (megger test) below the acceptance limit",
            "Bearing noise, temperature or vibration above limit",
            "Encoder / magnet degradation (PM machines)",
        ],
    },
    ComponentType.STEEL_ROPE.value: {
        "mechanism": "Bending fatigue over the traction sheave, wear and corrosion",
        "time_share": 0.2,
        "cycle_weight": 0.85,
        "load_exponent": 2.0,
        "load_basis": (
            "Rope bending life falls steeply with rope tension (Feyrer); an "
            "exponent of 2 approximates that relationship."
        ),
        "thermal": None,
        "thermal_basis": "Temperature is not a dominant rope ageing mechanism in a normal machine room.",
        "vibration_sensitive": False,
        "maintenance_weight": 0.4,
        "discard_criteria": [
            "Visible broken wires per reference length (ISO 4344 discard criteria)",
            "Reduction of rope diameter against the nominal",
            "Corrosion, kinks, strand looseness or core protrusion",
        ],
    },
    ComponentType.SHEAVE.value: {
        "mechanism": "Groove wear from rope creep and slip (Archard wear)",
        "time_share": 0.15,
        "cycle_weight": 0.8,
        "load_exponent": 1.0,
        "load_basis": "Archard's law: wear volume is proportional to contact pressure, so exponent 1.",
        "thermal": None,
        "thermal_basis": "Temperature is not a dominant sheave wear mechanism.",
        "vibration_sensitive": True,
        "maintenance_weight": 0.25,
        "discard_criteria": [
            "Groove profile worn beyond the gauge (loss of traction / undercut)",
            "Uneven groove depth between grooves (rope load sharing)",
            "Cracks in the rim or spokes",
        ],
    },
    ComponentType.BRAKE.value: {
        "mechanism": "Friction lining wear per stop and heat fade",
        "time_share": 0.2,
        "cycle_weight": 0.9,
        "load_exponent": 1.0,
        "load_basis": "Energy dissipated per stop scales with moving mass, so lining wear rises with load.",
        "thermal": (10.0, 15.0),
        "thermal_basis": "Lining wear accelerates as the friction surface runs hotter.",
        "vibration_sensitive": False,
        "maintenance_weight": 0.3,
        "discard_criteria": [
            "Lining thickness below minimum",
            "Air gap out of adjustment range",
            "Brake-release monitoring faults, spring set loss",
        ],
    },
    ComponentType.GOVERNOR.value: {
        "mechanism": "Governor-rope groove wear and ageing of the tripping linkage",
        "time_share": 0.35,
        "cycle_weight": 0.7,
        "load_exponent": 0.5,
        "load_basis": (
            "The governor rope is tensioned by its own weight, not by the car load, so "
            "load matters only weakly (through car speed and travel) - exponent 0.5."
        ),
        "thermal": None,
        "thermal_basis": "Temperature is not a dominant governor ageing mechanism.",
        "vibration_sensitive": True,
        "maintenance_weight": 0.4,
        "discard_criteria": [
            "Tripping speed outside tolerance at the periodic test (EN 81-20/50)",
            "Governor-rope groove worn - rope slips instead of pulling the safety gear",
            "Overspeed switch or rope-gripping jaw not acting",
            "Pivots seized, springs corroded or relaxed",
        ],
    },
    ComponentType.DOOR_OPERATOR.value: {
        "mechanism": "Roller, belt and lock wear per door cycle; door motor wear",
        "time_share": 0.15,
        "cycle_weight": 0.9,
        "load_exponent": 1.0,
        "load_basis": "Heavier door panels mean more force on rollers and belt per cycle, so wear rises with load.",
        "thermal": None,
        "thermal_basis": "Temperature is not a dominant door operator wear mechanism.",
        "vibration_sensitive": True,
        "maintenance_weight": 0.35,
        "discard_criteria": [
            "Door closing force or kinetic energy outside the EN 81-20 limits",
            "Hanger rollers flat-spotted, belt cracked or stretched beyond adjustment",
            "Door lock contacts worn - intermittent safety-chain faults",
            "Repeated door reversals or re-openings logged",
        ],
    },
}


# --------------------------------------------------------------------------
# Where each input comes from - the "what does KONE actually collect" answer
# --------------------------------------------------------------------------
#: For each input the life model reads: the platform field, and the honest
#: source a KONE deployment would have for it. ``published_api`` means the
#: field exists in KONE's published Equipment / Service Info API (see
#: ``app/integrations/kone_features``). ``not_published`` means no public
#: KONE feed carries it.
DATA_SOURCES: Dict[str, Dict[str, str]] = {
    "load_cycles": {
        "kone_source": "Equipment API movement events - one journey counted as one cycle, apportioned per component",
        "availability": "published_api",
    },
    "operating_hours": {
        "kone_source": "Equipment API movement durationSeconds x journeys observed",
        "availability": "published_api",
    },
    "average_load": {
        "kone_source": "Equipment API decks[].loadPercentage (percent of rated load)",
        "availability": "published_api",
    },
    "temperature": {
        "kone_source": (
            "No channel in the published KONE API. KONE's connected-services "
            "sensor data is not exposed publicly - needs a data-sharing "
            "agreement or a retrofit sensor"
        ),
        "availability": "not_published",
    },
    "vibration": {
        "kone_source": (
            "No channel in the published KONE API - same situation as temperature"
        ),
        "availability": "not_published",
    },
    "days_since_last_service": {
        "kone_source": "Service Info API service orders - finishedDateTime of the latest order",
        "availability": "published_api",
    },
    "inspection_score": {
        "kone_source": (
            "Service Info API equipmentConditionOnDeparture - a 4-level code "
            "describing the whole lift, used as a proxy"
        ),
        "availability": "published_api",
    },
    "material_grade": {
        "kone_source": "Not in any KONE API - from the bill of materials or nameplate at installation",
        "availability": "manual_record",
    },
    "installation_date": {
        "kone_source": "Not in any published KONE schema - from the installation record",
        "availability": "manual_record",
    },
}


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def _clamp(value: float, bounds: Tuple[float, float]) -> float:
    low, high = bounds
    return max(low, min(high, value))


def _get(component: Any, name: str, default: Any = None) -> Any:
    if isinstance(component, dict):
        return component.get(name, default)
    return getattr(component, name, default)


def is_supported(component_type: str) -> bool:
    """True for the component types this model covers."""
    return str(component_type) in FOCUS_TYPES


def resolve_grade(component_type: str, material: str, grade: Optional[str]) -> Tuple[Optional[str], str]:
    """Return ``(grade_key, provenance)`` for a component.

    ``provenance`` is ``recorded`` when the stored grade is valid for the type
    and material. Otherwise the key is the industry-standard grade for the
    material (:data:`INDUSTRY_DEFAULT_GRADES`) with provenance
    ``industry_default`` (nothing recorded) or ``recorded_grade_rejected`` (a
    stored grade that does not fit the material) - or None with
    ``not_determined`` when no grade is catalogued for the material at all.

    Callers that must act only on a *recorded* grade (the recoverable
    sub-components the decision flow names, the circularity mass split) check
    ``provenance == "recorded"``.
    """
    grades = MATERIAL_GRADES.get(str(component_type), {})
    if grade and grade in grades and str(material) in grades[grade]["materials"]:
        return grade, "recorded"
    default = INDUSTRY_DEFAULT_GRADES.get((str(component_type), str(material)))
    if grade:
        return default, "recorded_grade_rejected"
    if default is None:
        return None, "not_determined"
    return default, "industry_default"


def undetermined_grade_factor(component_type: str, material: str) -> Tuple[float, List[str]]:
    """Life factor to use when the grade is not determined.

    The most conservative (shortest-lived) grade consistent with the recorded
    material - so a missing grade can never flatter a component's life - and
    the candidate grades it was chosen from. 1.0 when none are catalogued.
    """
    candidates = [
        (key, grade["life_factor"])
        for key, grade in grades_for(component_type).items()
        if str(material) in grade["materials"]
    ]
    if not candidates:
        return 1.0, []
    return min(factor for _, factor in candidates), [key for key, _ in candidates]


def grades_for(component_type: str) -> Dict[str, Dict[str, Any]]:
    """The grade catalogue for one type (empty for unsupported types)."""
    return MATERIAL_GRADES.get(str(component_type), {})


def grade_cost_comparison(
    component_type: str, current_grade: Optional[str], ageing_rate: Optional[float] = None
) -> Optional[Dict[str, Any]]:
    """Cost of ownership of every catalogued grade of this type, cheapest per year first.

    Each grade's life is its design life (base x life factor) at this
    component's own ageing rate - the rate does not depend on the grade, so
    the comparison answers "which grade should the replacement be, for this
    lift's duty". Cost per year = (part price + fitting) / expected life.
    Returns None for a type with no grade prices configured.
    """
    from app.core.config import settings

    prices = settings.IMPACT_GRADE_PRICE_FACTOR.get(component_type)
    base_price = settings.IMPACT_NEW_PART_COST.get(component_type)
    if not prices or base_price is None:
        return None
    fitting = float(settings.IMPACT_REPLACEMENT_FITTING_COST.get(component_type, 0.0))
    own_duty = bool(ageing_rate and ageing_rate > 0)
    rate = float(ageing_rate) if own_duty else 1.0
    base_life = float(reference_for(component_type)["design_life_years"])

    options = []
    for key, grade in grades_for(component_type).items():
        if key not in prices:
            continue
        part_price = round(float(base_price) * float(prices[key]), 2)
        life = base_life * float(grade["life_factor"]) / rate
        options.append(
            {
                "grade": key,
                "label": grade["label"],
                "designation": grade["designation"],
                "materials": grade["materials"],
                "life_factor": grade["life_factor"],
                "part_price": part_price,
                "fitting_cost": fitting,
                "expected_life_years": round(life, 1),
                "cost_per_year": round((part_price + fitting) / life, 2),
                "current": key == current_grade,
            }
        )
    if not options:
        return None
    options.sort(key=lambda option: option["cost_per_year"])
    best = options[0]
    lowest_price = min(options, key=lambda option: option["part_price"])
    current = next((option for option in options if option["current"]), None)
    for option in options:
        option["most_cost_effective"] = option is best
        option["lowest_price"] = option is lowest_price
        option["extra_per_year_vs_best"] = round(option["cost_per_year"] - best["cost_per_year"], 2)

    symbol = settings.IMPACT_CURRENCY_SYMBOL
    if current is None:
        summary = (
            f"{best['label']} has the lowest cost per year of service: "
            f"{symbol} {best['cost_per_year']:,.0f}."
        )
    elif current is best:
        summary = (
            f"This component's grade is already the most cost-effective option at "
            f"{symbol} {best['cost_per_year']:,.0f} per year of service."
        )
    else:
        saving = current["cost_per_year"] - best["cost_per_year"]
        summary = (
            f"Replacing it with {best['label']} would cost "
            f"{symbol} {saving:,.0f} less per year of service "
            f"({saving / current['cost_per_year']:.0%}) than the current grade."
        )
    if lowest_price is not best:
        summary += (
            f" The cheapest to buy, {lowest_price['label']}, costs more per year because it "
            "is replaced sooner."
        )

    return {
        "currency": settings.IMPACT_CURRENCY,
        "currency_symbol": symbol,
        "ageing_rate": round(rate, 3),
        "duty_basis": "this component's own usage" if own_duty else "the design duty",
        "current_grade": current["grade"] if current else None,
        "most_cost_effective_grade": best["grade"],
        "saving_per_year": round(current["cost_per_year"] - best["cost_per_year"], 2) if current else None,
        "summary": summary,
        "options": options,
        "basis": (
            "PROTOTYPE ESTIMATE. Cost per year of service = (part price + fitting cost) / "
            "expected life. Part prices are illustrative ratios of the reference-grade price and "
            "fitting costs are illustrative; expected life is each grade's design life at this "
            "component's ageing rate. Energy use, downtime beyond fitting and end-of-life "
            "recovery value are not included. Replace with supplier quotes before quoting a saving."
        ),
    }


def material_profile(component: Any, ageing_rate: Optional[float] = None) -> Optional[Dict[str, Any]]:
    """What this component is made of, and what that means for its life.

    ``ageing_rate`` (from :func:`assess`) prices each grade at this
    component's own duty in the cost comparison; without it the design duty
    is used.
    """
    component_type = str(_get(component, "component_type"))
    if not is_supported(component_type):
        return None
    material = str(_get(component, "material"))
    stored = _get(component, "material_grade")
    key, provenance = resolve_grade(component_type, material, stored)
    cost_comparison = grade_cost_comparison(component_type, key, ageing_rate)
    siblings = [
        {
            "grade": other_key,
            "label": other["label"],
            "designation": other["designation"],
            "life_factor": other["life_factor"],
        }
        for other_key, other in grades_for(component_type).items()
    ]
    if key is None:
        factor, candidates = undetermined_grade_factor(component_type, material)
        return {
            "supported": True,
            "primary_material": material,
            "grade": None,
            "grade_label": GRADE_NOT_DETERMINED,
            "grade_provenance": provenance,
            "grade_note": (
                f"No grade is catalogued for a {material} {component_type.lower()}, so none "
                "is shown. Record it from the nameplate or bill of materials."
            ),
            "life_factor": factor,
            "life_reasoning": "No grade catalogued for this material: the type's reference life is used.",
            "constituents": None,
            "properties": [],
            "designation": None,
            "grading_system": None,
            "equivalent": None,
            "specifications": [],
            "material_recoverability": None,
            "alternatives": [s for s in siblings if s["grade"] in candidates],
            "cost_comparison": cost_comparison,
            "basis": "Composition is shown once the material grade is recorded.",
        }
    grade = MATERIAL_GRADES[component_type][key]
    if provenance == "recorded":
        label = display_label(grade)
        note = "Grade recorded on this component."
    else:
        label = display_label(grade) + INDUSTRY_DEFAULT_SUFFIX
        note = (
            "No grade is recorded for this component"
            if provenance == "industry_default"
            else f"The recorded grade '{stored}' does not fit a {material} {component_type.lower()}"
        ) + (
            f", so the industry-standard grade for {material} is assumed. Where more than "
            "one grade is possible, the assumed one is the shortest-lived, so the "
            "assumption cannot overstate this component's life. Record the actual grade "
            "from the nameplate or bill of materials to replace it."
        )
    return {
        "supported": True,
        "primary_material": material,
        "grade": key,
        "grade_label": label,
        "grade_provenance": provenance,
        "grade_note": note,
        "designation": grade["designation"],
        "grading_system": grade["grading_system"],
        "equivalent": grade["equivalent"],
        "specifications": grade["specifications"],
        "specification_notice": (
            "Typical grades for this construction, cited by standard. Confirm each "
            "against the nameplate, mill certificate or bill of materials before "
            "relying on it."
        ),
        "life_factor": grade["life_factor"],
        "life_reasoning": grade["life_reasoning"],
        "constituents": grade["constituents"],
        "properties": grade["properties"],
        "material_recoverability": grade["material_recoverability"],
        "alternatives": siblings
        if provenance == "recorded"
        else [s for s in siblings if material in MATERIAL_GRADES[component_type][s["grade"]]["materials"]],
        "cost_comparison": cost_comparison,
        "basis": (
            "Illustrative bill of materials - PROTOTYPE ESTIMATE, not supplier data."
            if provenance == "recorded"
            else "Typical bill of materials for the assumed industry-standard grade - "
            "PROTOTYPE ESTIMATE, not measured on this component."
        ),
    }


# --------------------------------------------------------------------------
# Stress factors
# --------------------------------------------------------------------------
def _duty_factor(component: Any, ref: Dict[str, float], mechanism: Dict[str, Any], age: float) -> Dict[str, Any]:
    design_life = float(ref["design_life_years"])
    if age < MIN_AGE_FOR_RATE_YEARS:
        return {
            "key": "duty",
            "label": "Usage intensity (cycles and running hours)",
            "multiplier": 1.0,
            "observed": None,
            "reference": "design duty",
            "explanation": (
                f"Under {MIN_AGE_FOR_RATE_YEARS} years in service - too short a window "
                "to turn the counters into an annual rate, so design duty is assumed."
            ),
            "inputs": ["load_cycles", "operating_hours"],
            "provenance": "assumed",
        }
    cycles_per_year = float(_get(component, "load_cycles", 0) or 0) / age
    hours_per_year = float(_get(component, "operating_hours", 0) or 0) / age
    design_cycles = ref["design_cycles"] / design_life
    design_hours = ref["design_hours"] / design_life
    weight = mechanism["cycle_weight"]
    ratio = weight * cycles_per_year / design_cycles + (1 - weight) * hours_per_year / design_hours
    multiplier = _clamp(ratio, _DUTY_BOUNDS)
    return {
        "key": "duty",
        "label": "Usage intensity (cycles and running hours)",
        "multiplier": round(multiplier, 3),
        "observed": f"{cycles_per_year:,.0f} cycles/yr, {hours_per_year:,.0f} h/yr",
        "reference": f"{design_cycles:,.0f} cycles/yr, {design_hours:,.0f} h/yr at design duty",
        "explanation": (
            f"Weighted {int(weight * 100)}% cycles / {int((1 - weight) * 100)}% hours for this "
            f"mechanism. {multiplier:.2f}x design duty."
        ),
        "inputs": ["load_cycles", "operating_hours"],
        "provenance": "measured",
    }


def _load_factor(component: Any, ref: Dict[str, float], mechanism: Dict[str, Any]) -> Dict[str, Any]:
    average_load = float(_get(component, "average_load", 0) or 0)
    exponent = mechanism["load_exponent"]
    if average_load <= 0:
        return {
            "key": "load",
            "label": "Load carried",
            "multiplier": 1.0,
            "observed": None,
            "reference": f"{reference_utilisation(_get(component, 'component_type')):.0%} of rated load",
            "explanation": "No load reading recorded - design load assumed.",
            "inputs": ["average_load"],
            "provenance": "assumed",
        }
    utilisation = average_load / ref["rated_load"]
    nominal = reference_utilisation(_get(component, "component_type"))
    multiplier = _clamp((utilisation / nominal) ** exponent, _LOAD_BOUNDS)
    return {
        "key": "load",
        "label": "Load carried",
        "multiplier": round(multiplier, 3),
        "observed": f"{average_load:,.0f} kg ({utilisation:.0%} of rated)",
        "reference": f"{nominal:.0%} of rated load ({ref['rated_load']:,.0f} kg rated) - the fleet's typical duty",
        "explanation": f"(load ratio)^{exponent}. {mechanism['load_basis']}",
        "inputs": ["average_load"],
        "provenance": "measured",
    }


def _thermal_factor(component: Any, ref: Dict[str, float], mechanism: Dict[str, Any]) -> Dict[str, Any]:
    thermal = mechanism["thermal"]
    raw = _get(component, "temperature")
    temperature = 25.0 if raw is None else float(raw)
    if thermal is None:
        return {
            "key": "thermal",
            "label": "Operating temperature",
            "multiplier": 1.0,
            "observed": f"{temperature:.0f} C",
            "reference": "not a dominant mechanism",
            "explanation": mechanism["thermal_basis"],
            "inputs": ["temperature"],
            "provenance": "not_applicable",
        }
    margin_k, doubling_k = thermal
    reference_c = ref["temp_limit"] - margin_k
    multiplier = _clamp(2.0 ** ((temperature - reference_c) / doubling_k), _THERMAL_BOUNDS)
    return {
        "key": "thermal",
        "label": "Operating temperature",
        "multiplier": round(multiplier, 3),
        "observed": f"{temperature:.0f} C",
        "reference": (
            f"{reference_c:.0f} C, {margin_k:.0f} K under the {ref['temp_limit']:.0f} C limit "
            f"(ageing doubles every {doubling_k:.0f} K above)"
        ),
        "explanation": mechanism["thermal_basis"],
        "inputs": ["temperature"],
        "provenance": "measured",
    }


def _vibration_factor(component: Any, ref: Dict[str, float], mechanism: Dict[str, Any]) -> Dict[str, Any]:
    vibration = float(_get(component, "vibration", 0) or 0)
    limit = ref["vibration_limit"]
    if not mechanism["vibration_sensitive"]:
        return {
            "key": "vibration",
            "label": "Vibration",
            "multiplier": 1.0,
            "observed": f"{vibration:.1f} mm/s",
            "reference": "not a dominant mechanism",
            "explanation": "Vibration is a symptom here, not a driver of this wear mechanism.",
            "inputs": ["vibration"],
            "provenance": "not_applicable",
        }
    ratio = vibration / limit if limit else 0.0
    multiplier = _clamp(1.0 + 0.8 * max(0.0, ratio - 0.6), (1.0, 2.0))
    return {
        "key": "vibration",
        "label": "Vibration",
        "multiplier": round(multiplier, 3),
        "observed": f"{vibration:.1f} mm/s ({ratio:.0%} of limit)",
        "reference": f"accelerates above 60% of the {limit:.1f} mm/s limit",
        "explanation": (
            "Sustained vibration indicates misalignment or bearing distress, "
            "which loads the wear surfaces unevenly."
        ),
        "inputs": ["vibration"],
        "provenance": "measured",
    }


def _readings_history(component: Any) -> List[Tuple[date, Optional[float], Optional[float]]]:
    """Dated (vibration, temperature) readings from the component's service history."""
    events = _get(component, "readings")
    if events is None:
        events = _get(component, "service_events") or []
    out = []
    for event in events:
        when = _get(event, "event_date")
        if when is None:
            continue
        out.append((when, _get(event, "vibration"), _get(event, "temperature")))
    return sorted(out, key=lambda item: item[0])


def _history_average(
    installation_date: date,
    today: date,
    history: List[Tuple[date, float]],
    current: float,
) -> float:
    """Time-weighted average of a factor over the component's life.

    Condition readings describe the part when they were taken, not for its
    whole life. The factor is integrated (trapezoid rule) from installation -
    the commissioning reading when one was taken that day, else 1.0 for a new
    part - through each dated reading to today's value, and averaged over the
    age. Without any history this is the average of new condition and today.
    """
    commissioning = [value for when, value in history if when == installation_date]
    points = [(installation_date, commissioning[-1] if commissioning else 1.0)]
    points += [(when, value) for when, value in history if installation_date < when < today]
    points.append((today, current))
    span = (today - installation_date).days
    if span <= 0:
        return current
    area = 0.0
    for (d0, v0), (d1, v1) in zip(points, points[1:]):
        area += (d1 - d0).days * (v0 + v1) / 2.0
    return area / span


def _historical_maintenance(component: Any, mechanism: Dict[str, Any], age: float) -> float:
    """Maintenance factor over the whole life, from how often it was serviced."""
    if age < MIN_AGE_FOR_RATE_YEARS:
        return 1.0
    visits = max(int(_get(component, "service_count", 0) or 0), 1)
    interval_days = age * 365.25 / visits
    nominal = service_interval_days(_get(component, "component_type"))
    overdue_years = max(0.0, (interval_days - nominal) / 365.0)
    return 1.0 + mechanism["maintenance_weight"] * min(overdue_years, 2.0)


def _maintenance_factor(component: Any, mechanism: Dict[str, Any]) -> Dict[str, Any]:
    days = int(_get(component, "days_since_last_service", 0) or 0)
    weight = mechanism["maintenance_weight"]
    nominal = service_interval_days(_get(component, "component_type"))
    overdue_years = max(0.0, (days - nominal) / 365.0)
    multiplier = 1.0 + weight * min(overdue_years, 2.0)
    return {
        "key": "maintenance",
        "label": "Maintenance regularity",
        "multiplier": round(multiplier, 3),
        "observed": f"{days} days since last service",
        "reference": f"service every {nominal:.0f} days (typical for the fleet)",
        "explanation": (
            "Missed lubrication and adjustment speed wear up. "
            f"+{int(weight * 100)}% per year overdue, capped at two years."
        ),
        "inputs": ["days_since_last_service"],
        "provenance": "measured",
    }


# --------------------------------------------------------------------------
# Assessment
# --------------------------------------------------------------------------
def _combined_rate(time_share, duty, load, thermal, vibration, maintenance, key: str) -> float:
    """Ageing rate from the stress factors, as competing mechanisms.

    Mechanical wear (load, and vibration where it loads the surfaces
    unevenly) and thermal ageing are different mechanisms, and a part is worn
    out by whichever runs faster - not by their product. Multiplying them
    double-counted: a hot motor is usually hot *because* it is loaded, so load
    and heat were both charged for the same cause, and extreme-duty parts aged
    many times faster than any single mechanism supports. Duty scales both;
    poor maintenance accelerates both.
    """
    mechanical = load[key] * vibration[key]
    stress = max(mechanical, thermal[key]) if thermal.get("provenance") != "not_applicable" else mechanical
    return (time_share + (1.0 - time_share) * duty[key] * stress) * maintenance[key]


def _band(consumed: float) -> str:
    if consumed < SUITABLE_LIMIT:
        return "green"
    if consumed < REPLACE_LIMIT:
        return "amber"
    return "red"


def _years_to(threshold: float, consumed: float, rate: float, design_life: float) -> float:
    """Calendar years from now until ``consumed`` reaches ``threshold``."""
    return max(0.0, (threshold - consumed) * design_life / rate)


def _date_in(today: date, years: float) -> date:
    return today + timedelta(days=round(years * 365.25))


def _status(consumed: float, years_to_half_life: float, years_to_replace: float) -> Dict[str, str]:
    if consumed >= END_OF_LIFE:
        return {"level": "OVERDUE", "message": "Has used up its expected life at the way it has been used. Inspect and plan replacement now."}
    if consumed >= REPLACE_LIMIT:
        return {"level": "ACT", "message": "Over 80% of its expected life is used (replace band). Schedule replacement at the next planned visit."}
    if consumed >= SUITABLE_LIMIT or years_to_replace <= 2.0:
        return {"level": "PLAN", "message": "Over half of its expected life is used. Plan its end-of-use route and the replacement now."}
    if years_to_half_life <= 2.0:
        return {"level": "WATCH", "message": "Will pass half of its expected life within two years at current usage."}
    return {"level": "OK", "message": "Less than half of its expected life is used - healthy margin at current usage."}


def _implication(component: Any, component_type: str, consumed: float) -> Dict[str, Any]:
    """What the life position means if the part were taken out of service today.

    Follows the same decision flow as the assessment (``decision_flow``), with
    the life position standing in for the classifier: suitable for its
    current application while under half its adjusted life; sub-components
    worth recovering while under the replace band; otherwise material
    recovery if the material allows it, else disposal.
    """
    from app.ml import decision_flow

    material = str(_get(component, "material"))
    grade = _get(component, "material_grade")
    parts = decision_flow.recoverable_subcomponents(component_type, material, grade)
    material_info = decision_flow.material_recoverability(component_type, material, grade)
    band = _band(consumed)
    if band == "green":
        recommendation = Recommendation.CONTINUE_USING.value
    elif band == "amber" and parts["possible"]:
        recommendation = Recommendation.COMPONENT_RECOVERY.value
    elif material_info["possible"]:
        recommendation = Recommendation.MATERIAL_RECOVERY.value
    else:
        recommendation = Recommendation.DISPOSE.value
    return {
        "recommendation": recommendation,
        "label": recommendation_label(recommendation),
        "reason": decision_flow.recommendation_text(recommendation, component_type, parts),
        "material_recoverability": material_info["basis"],
        "safety_gate": is_safety_critical(component_type),
    }


def _trajectory(
    install_year: float,
    age: float,
    governing: float,
    historical_rate: float,
    rate: float,
    design_life: float,
    years_to_eol: float,
) -> List[Dict[str, Any]]:
    """Chart series: design baseline, actual history, and projection."""
    horizon = max(design_life * 1.15, age + years_to_eol * 1.15, age + 2.0)
    horizon = min(horizon, 80.0)
    steps = 48
    # Compare against the same rounded "today" that is inserted into the
    # series, or history and projection can miss each other and leave a gap.
    age = round(age, 3)
    times = sorted({round(horizon * i / steps, 3) for i in range(steps + 1)} | {age})
    points: List[Dict[str, Any]] = []
    for t in times:
        design = 100.0 * t / design_life
        history = 100.0 * t * historical_rate / design_life if t <= age else None
        projected = (
            100.0 * (governing + (t - age) * rate / design_life) if t >= age else None
        )
        points.append(
            {
                "years_in_service": t,
                "year": round(install_year + t, 2),
                "design": round(min(design, 160.0), 2),
                "actual": round(min(history, 160.0), 2) if history is not None else None,
                "projected": round(min(projected, 160.0), 2) if projected is not None else None,
            }
        )
    # The history line ends at the usage model's value; when the inspection
    # governs, the projection starts from the (worse) inspected position, so
    # the two lines visibly separate at "today".
    return points


def assess(component: Any, today: Optional[date] = None) -> Dict[str, Any]:
    """Usage-adjusted life assessment for one component.

    Accepts a ``Component`` ORM instance or a dict carrying the same fields.
    Returns ``supported: False`` for types outside :data:`FOCUS_TYPES`.
    """
    component_type = str(_get(component, "component_type"))
    if not is_supported(component_type):
        return {
            "supported": False,
            "component_type": component_type,
            "reason": (
                "The usage-adjusted life model currently covers "
                f"{', '.join(FOCUS_TYPES)} only."
            ),
        }

    today = today or utcnow().date()
    installation_date = _get(component, "installation_date")
    if installation_date is None:
        return {
            "supported": True,
            "available": False,
            "component_type": component_type,
            "reason": (
                "No installation date is recorded, so there is no calendar age to "
                "project from. Record it from the installation record."
            ),
        }

    age = max((today - installation_date).days / 365.25, 0.0)
    ref = reference_for(component_type)
    mechanism = MECHANISMS[component_type]
    profile = material_profile(component)
    material_factor = float(profile["life_factor"]) if profile else 1.0
    base_life = float(ref["design_life_years"])
    design_life = base_life * material_factor

    duty = _duty_factor(component, ref, mechanism, age)
    load = _load_factor(component, ref, mechanism)
    thermal = _thermal_factor(component, ref, mechanism)
    vibration = _vibration_factor(component, ref, mechanism)
    maintenance = _maintenance_factor(component, mechanism)

    # Two rates. Duty and load come from lifetime counters and averages, so
    # they describe the whole life. Temperature, vibration and days since
    # service describe the part NOW - applying today's worn-state readings
    # to its entire history would age it as if it had always been worn, which
    # is what used to make effective age run far ahead of calendar age. The
    # past is therefore integrated over the dated readings in its service
    # history (and maintenance judged from its service count over its life);
    # the present values drive only the forward projection.
    history = _readings_history(component)
    thermal["history_multiplier"] = round(
        _history_average(
            installation_date, today,
            [
                (when, _thermal_factor({"temperature": temp}, ref, mechanism)["multiplier"])
                for when, _vib, temp in history
                if temp is not None
            ],
            thermal["multiplier"],
        ),
        3,
    )
    vibration["history_multiplier"] = round(
        _history_average(
            installation_date, today,
            [
                (when, _vibration_factor({"vibration": vib}, ref, mechanism)["multiplier"])
                for when, vib, _temp in history
                if vib is not None
            ],
            vibration["multiplier"],
        ),
        3,
    )
    maintenance["history_multiplier"] = round(_historical_maintenance(component, mechanism, age), 3)
    duty["history_multiplier"] = duty["multiplier"]
    load["history_multiplier"] = load["multiplier"]

    time_share = mechanism["time_share"]
    raw_rate = _combined_rate(time_share, duty, load, thermal, vibration, maintenance, "multiplier")
    rate = _clamp(raw_rate, _RATE_BOUNDS)
    historical_rate = _clamp(
        _combined_rate(time_share, duty, load, thermal, vibration, maintenance, "history_multiplier"),
        _RATE_BOUNDS,
    )

    model_consumed = age * historical_rate / design_life
    inspection_score = float(_get(component, "inspection_score", 100.0) or 0.0)
    inspection_consumed = inspection_life_consumed(inspection_score)
    # The inspection governs when it shows materially more wear than usage
    # explains - beyond its own grading scatter - which keeps the conservative
    # direction without the upward bias of always taking the larger estimate.
    if inspection_consumed > model_consumed + inspection_override_margin():
        governing, governed_by = inspection_consumed, "inspection"
    else:
        governing, governed_by = model_consumed, "usage_model"

    divergence = None
    if inspection_consumed - model_consumed > _DIVERGENCE:
        divergence = (
            "The inspection shows more wear than the usage explains. Look for a cause "
            "the counters cannot see - misalignment, contamination, an installation "
            "fault - before trusting the projection."
        )
    elif model_consumed - inspection_consumed > _DIVERGENCE + 0.1:
        divergence = (
            "Usage predicts more wear than the inspection found. The stress factors "
            "may overstate this unit's duty - worth a targeted inspection to confirm."
        )

    years_to_half_life = _years_to(SUITABLE_LIMIT, governing, rate, design_life)
    years_to_replace = _years_to(REPLACE_LIMIT, governing, rate, design_life)
    years_to_eol = _years_to(END_OF_LIFE, governing, rate, design_life)
    # Signed, unlike years_to_eol: a part already past end of life reached it
    # (1 - D) * L / rate years ago, and its total life is that, not its age.
    projected_total_life = age + (END_OF_LIFE - governing) * design_life / rate
    install_year = installation_date.year + (installation_date.timetuple().tm_yday - 1) / 365.25

    factors = [duty, load, thermal, vibration, maintenance]
    for factor in factors:
        factor["sources"] = [
            {"field": field, **DATA_SOURCES[field]} for field in factor["inputs"]
        ]

    return {
        "supported": True,
        "available": True,
        "component_type": component_type,
        "mechanism": mechanism["mechanism"],
        "calendar_age_years": round(age, 2),
        "effective_age_years": round(governing * design_life, 2),
        "ageing_rate": round(rate, 3),
        "ageing_rate_uncapped": round(raw_rate, 3),
        "historical_ageing_rate": round(historical_rate, 3),
        "readings_in_history": len(history),
        "base_design_life_years": base_life,
        "material_factor": material_factor,
        "design_life_years": round(design_life, 2),
        "life_consumed": {
            "governing": round(governing, 4),
            "usage_model": round(model_consumed, 4),
            "inspection": round(inspection_consumed, 4),
            "governed_by": governed_by,
            "divergence_note": divergence,
        },
        "band": _band(governing),
        "status": _status(governing, years_to_half_life, years_to_replace),
        "projection": {
            "years_to_half_life": round(years_to_half_life, 2),
            "years_to_replace_band": round(years_to_replace, 2),
            "years_to_end_of_life": round(years_to_eol, 2),
            "half_life_date": _date_in(today, years_to_half_life).isoformat(),
            "replace_band_date": _date_in(today, years_to_replace).isoformat(),
            "end_of_life_date": _date_in(today, years_to_eol).isoformat(),
            "projected_total_life_years": round(projected_total_life, 2),
            "design_total_life_years": round(design_life, 2),
            "life_change_years": round(projected_total_life - design_life, 2),
            "assumption": (
                "Past wear uses lifetime usage and the readings history; the projection "
                "assumes today's conditions continue."
            ),
        },
        "thresholds": {
            "suitable_limit": SUITABLE_LIMIT,
            "replace_limit": REPLACE_LIMIT,
            "end_of_life": END_OF_LIFE,
        },
        "factors": factors,
        "implication": _implication(component, component_type, governing),
        "discard_criteria": mechanism["discard_criteria"],
        "trajectory": _trajectory(
            install_year, age, governing, historical_rate, rate, design_life, years_to_eol
        ),
        "basis": (
            "Physics-of-failure life-consumption model (Miner's rule) with documented "
            "prototype exponents - not a KONE specification and not calibrated against "
            "real removals. Advisory only; it never overrides the safety gate."
        ),
    }


def projection_summary(assessment: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """The trajectory-free subset of an assessment, for exports."""
    if not assessment.get("supported") or not assessment.get("available"):
        return None
    return {
        key: assessment[key]
        for key in (
            "mechanism",
            "calendar_age_years",
            "effective_age_years",
            "ageing_rate",
            "design_life_years",
            "life_consumed",
            "band",
            "status",
            "projection",
            "implication",
            "basis",
        )
    }
