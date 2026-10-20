"""The end-of-use decision flow: four categories, evaluated in order.

::

    Is the component still suitable for its CURRENT application?
        YES -> CONTINUE_USING      (it keeps operating where it is, unchanged)
        NO  -> Can usable individual SUB-COMPONENTS be recovered?
                YES -> COMPONENT_RECOVERY  (parts inspected, tested, and used only in
                                            technically suitable lower-demand applications)
                NO  -> Can useful MATERIAL be recovered?
                        YES -> MATERIAL_RECOVERY
                        NO  -> DISPOSE

No complete component is ever recommended for transfer to another device,
resale or supply to another customer, in any branch.

What each gate is decided on
----------------------------
Every gate uses evidence the platform already holds - nothing here is an
age rule:

* **Suitability (gate 1)** - the trained classifier's calibrated probability
  that the component is fit to continue, which is computed from all 13
  features (usage, load, condition readings, service history, inspection,
  material); and the inspection result, which vetoes continued use when the
  measured condition is already in the replace band.
* **Recoverable sub-components (gate 2)** - whether the component type is
  built from separable sub-components at all (a steel wire rope is not), the
  actual sub-components of its recorded material grade where one is on
  record, and whether the classifier still judges the parts serviceable
  (probability mass on continue + component recovery).
* **Recoverable material (gate 3)** - the metal content of the recorded grade
  (its bill of materials) or, without a grade, of the primary material.

Sub-components are only named when the component's recorded material grade
lists them. Without a grade the recommendation stays generic rather than
inventing parts.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.utils.enums import (
    RECOMMENDATION_DESCRIPTIONS,
    ComponentType,
    Material,
    Recommendation,
    is_safety_critical,
    recommendation_label,
)

CONTINUE = Recommendation.CONTINUE_USING.value
COMPONENT = Recommendation.COMPONENT_RECOVERY.value
MATERIAL = Recommendation.MATERIAL_RECOVERY.value
DISPOSE = Recommendation.DISPOSE.value

#: Inspection score at or below which the measured condition is in the
#: replace band (same scale as the life model: 100 - 0.8 x 65).
INSPECTION_REPLACE_BAND = 48.0

#: Gate 2 needs the classifier to judge the part serviceable more likely than
#: not: P(continue) + P(component recovery) at or above this.
SERVICEABLE_PARTS_PROBABILITY = 0.5

#: Whether a component type is built from separable sub-components that can
#: be recovered individually. A wire rope is a single drawn product;
#: everything else is an assembly.
HAS_SEPARABLE_SUBCOMPONENTS: Dict[str, bool] = {
    ComponentType.MOTOR.value: True,
    ComponentType.SHEAVE.value: True,
    ComponentType.BRAKE.value: True,
    ComponentType.GOVERNOR.value: True,
    ComponentType.DOOR_OPERATOR.value: True,
    ComponentType.STEEL_ROPE.value: False,
}

#: Primary materials from which useful material can be recovered.
RECOVERABLE_MATERIALS = frozenset(
    {
        Material.STEEL.value,
        Material.CAST_IRON.value,
        Material.ALUMINUM.value,
        Material.COPPER.value,
    }
)

#: Share of metal in a grade's bill of materials above which material
#: recovery is technically worthwhile.
MIN_RECOVERABLE_METAL_SHARE = 0.5

_METAL_WORDS = ("steel", "iron", "copper", "alumin", "metal", "magnet", "sintered")


def _grade(component_type: str, material: str, grade: Optional[str]) -> Optional[Dict[str, Any]]:
    """The recorded grade's catalogue entry, only if it is valid for this part."""
    from app.ml import life_model

    key, provenance = life_model.resolve_grade(component_type, material, grade)
    if key is None or provenance != "recorded":
        return None
    return life_model.MATERIAL_GRADES[component_type][key]


def recoverable_subcomponents(
    component_type: str, material: str, grade: Optional[str] = None
) -> Dict[str, Any]:
    """Which sub-components could be recovered, and how that is known."""
    component_type = str(component_type)
    separable = HAS_SEPARABLE_SUBCOMPONENTS.get(component_type, False)
    if not separable:
        return {
            "possible": False,
            "parts": [],
            "basis": f"A {component_type.lower()} is a single product with no separable sub-components.",
        }
    entry = _grade(component_type, material, grade)
    if entry is not None:
        parts = [item["name"] for item in entry["constituents"] if item.get("separable")]
        return {
            "possible": bool(parts),
            "parts": parts,
            "basis": f"Separable sub-components listed for the recorded grade ({entry['label']}).",
        }
    return {
        "possible": True,
        "parts": [],
        "basis": (
            f"A {component_type.lower()} is an assembly of separable sub-components. Its "
            "material grade is not recorded, so which parts are recoverable is decided at "
            "inspection rather than named here."
        ),
    }


def material_recoverability(component_type: str, material: str, grade: Optional[str] = None) -> Dict[str, Any]:
    """Whether useful material can be recovered, from the grade's BOM or the material."""
    entry = _grade(str(component_type), str(material), grade)
    if entry is not None:
        metal = sum(
            item["mass_fraction"]
            for item in entry["constituents"]
            if any(word in item["name"].lower() for word in _METAL_WORDS)
        )
        return {
            "possible": metal >= MIN_RECOVERABLE_METAL_SHARE,
            "metal_share": round(metal, 3),
            "basis": f"{metal:.0%} of the recorded grade's mass is metal.",
        }
    possible = str(material) in RECOVERABLE_MATERIALS
    return {
        "possible": possible,
        "metal_share": None,
        "basis": (
            f"{material} is a recoverable material stream."
            if possible
            else f"{material} has no established material-recovery route; energy recovery or disposal applies."
        ),
    }


def recommendation_text(
    recommendation: str,
    component_type: str,
    subcomponents: Optional[Dict[str, Any]] = None,
) -> str:
    """The recommendation sentence shown to the user, component-aware."""
    base = RECOMMENDATION_DESCRIPTIONS.get(recommendation, "")
    if recommendation != COMPONENT or not subcomponents:
        return base
    parts = subcomponents.get("parts") or []
    what = (
        f"Recover usable sub-components of this {component_type.lower()} - for its recorded grade: "
        + ", ".join(p.lower() for p in parts)
        + " -"
        if parts
        else f"Recover usable sub-components from this {component_type.lower()}"
    )
    text = (
        f"{what} after inspection and testing. Suitable recovered parts may be redirected to "
        "lower-demand applications where technically appropriate. The complete component is "
        "not refurbished or supplied again."
    )
    if is_safety_critical(component_type):
        text += " Parts recovered from a safety component are not used in a safety function."
    return text


def decide(
    probabilities: Dict[str, float],
    component_type: str,
    material: str,
    inspection_score: Optional[float] = None,
    grade: Optional[str] = None,
) -> Dict[str, Any]:
    """Run the four gates in order. Returns the category and every gate's evidence."""
    component_type = str(component_type)
    p = {key: float(value) for key, value in (probabilities or {}).items()}
    p_continue = p.get(CONTINUE, 0.0)
    top = max(p, key=p.get) if p else None
    steps: List[Dict[str, Any]] = []

    # Gate 1 - still suitable for its current application?
    inspection_blocks = inspection_score is not None and inspection_score <= INSPECTION_REPLACE_BAND
    suitable = top == CONTINUE and not inspection_blocks
    steps.append(
        {
            "gate": "Suitable for its current application?",
            "passed": suitable,
            "evidence": (
                f"Classifier: {p_continue:.0%} probability it is fit to continue"
                + (" (its most likely outcome)" if top == CONTINUE else f"; most likely is {recommendation_label(top)}")
                + "."
                + (
                    f" Inspection score {inspection_score:.0f}/100 is in the replace band."
                    if inspection_blocks
                    else ""
                )
            ),
        }
    )
    subcomponents = recoverable_subcomponents(component_type, material, grade)
    material_info = material_recoverability(component_type, material, grade)

    if suitable:
        result = CONTINUE
    else:
        # Gate 2 - usable individual sub-components?
        serviceable = p_continue + p.get(COMPONENT, 0.0)
        parts_ok = subcomponents["possible"] and serviceable >= SERVICEABLE_PARTS_PROBABILITY
        steps.append(
            {
                "gate": "Usable individual sub-components recoverable?",
                "passed": parts_ok,
                "evidence": (
                    subcomponents["basis"]
                    + (
                        f" Classifier judges the parts serviceable with {serviceable:.0%} probability"
                        f" (needs {SERVICEABLE_PARTS_PROBABILITY:.0%})."
                        if subcomponents["possible"]
                        else ""
                    )
                ),
            }
        )
        if parts_ok:
            result = COMPONENT
        else:
            # Gate 3 - useful material?
            steps.append(
                {
                    "gate": "Useful material recoverable?",
                    "passed": material_info["possible"],
                    "evidence": material_info["basis"],
                }
            )
            result = MATERIAL if material_info["possible"] else DISPOSE

    return {
        "recommendation": result,
        "label": recommendation_label(result),
        "text": recommendation_text(result, component_type, subcomponents),
        "steps": steps,
        "subcomponents": subcomponents if result == COMPONENT else None,
        "material": material_info,
        "safety_critical": is_safety_critical(component_type),
    }


def label_from_wear(effective_wear: float, component_type: str, material: str, thresholds) -> str:
    """The training-label policy: the same flow, on the simulator's latent wear.

    Used only by the synthetic dataset generator. ``thresholds`` are the wear
    levels at which the component stops being suitable for its current
    application and at which its parts stop being serviceable.
    """
    suitable_limit, parts_limit = thresholds
    if effective_wear < suitable_limit:
        return CONTINUE
    if effective_wear < parts_limit and HAS_SEPARABLE_SUBCOMPONENTS.get(component_type, False):
        return COMPONENT
    if str(material) in RECOVERABLE_MATERIALS:
        return MATERIAL
    return DISPOSE
