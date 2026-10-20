"""Engineering standards basis, cited per component type.

The pitch calls the passport "standards-based". Until now no standard number
appeared anywhere in the code, which made that an adjective rather than a
claim an auditor could check. This module is the claim: for each component
type, which published standard governs it, and which part of that standard is
the relevant one.

READ THIS BEFORE RELYING ON A CLAUSE NUMBER
-------------------------------------------
Standards are copyrighted documents sold by ISO, CEN and IEC. They were not
available to this build, so the clause references below were assembled from
public scopes, abstracts and tables of contents - **not** from the purchased
text. Every entry therefore carries a ``verification`` field:

* ``STANDARD_VERIFIED``  - the standard's number, year and scope are correct
                           and the citation is at document level.
* ``CLAUSE_UNVERIFIED``  - the clause pointer is a good-faith locator that has
                           NOT been checked against the published text.

Nothing here is ``CLAUSE_VERIFIED`` yet, and nothing should be until someone
with the purchased standards has checked each pointer and changed the flag.
Rendering an unverified clause number to a technician as though it were
authoritative is exactly the kind of confident-looking wrongness this project
spends the rest of its code avoiding.
"""

from __future__ import annotations

from typing import Any, Dict, List

from app.utils.enums import ComponentType

STANDARD_VERIFIED = "STANDARD_VERIFIED"
CLAUSE_UNVERIFIED = "CLAUSE_UNVERIFIED"
CLAUSE_VERIFIED = "CLAUSE_VERIFIED"

VERIFICATION_NOTICE = (
    "Standard identity (number, year, scope) is verified. Clause-level "
    "pointers marked CLAUSE_UNVERIFIED were assembled from public scopes and "
    "contents listings, not from the purchased standard text, and must be "
    "confirmed against the published document before external use."
)


def _citation(
    standard: str,
    title: str,
    relevance: str,
    clause: str | None = None,
    clause_topic: str | None = None,
    verification: str = CLAUSE_UNVERIFIED,
) -> Dict[str, Any]:
    return {
        "standard": standard,
        "title": title,
        "clause": clause,
        "clause_topic": clause_topic,
        "relevance": relevance,
        "verification": verification if clause else STANDARD_VERIFIED,
    }


#: Applies to every component type: EN 81-80 is the framework a decision to
#: modernize rather than repair an existing lift sits inside, which is the
#: decision this platform informs.
_MODERNIZATION_CONTEXT = _citation(
    standard="EN 81-80:2019",
    title=(
        "Safety rules for the construction and installation of lifts - "
        "Existing lifts - Rules for the improvement of safety of existing "
        "passenger and goods passenger lifts (SNEL)"
    ),
    relevance=(
        "Hazard-ranked framework for improving the safety of lifts already in "
        "service. An end-of-use recommendation on a removed component is an "
        "input to a modernization decision governed by this standard."
    ),
)

#: Applies to every type whose service life is bearing-bound.
_BEARING_LIFE = _citation(
    standard="ISO 281:2007",
    title="Rolling bearings - Dynamic load ratings and rating life",
    clause_topic="Basic rating life (L10)",
    clause="5",
    relevance=(
        "L10 basic rating life is the accepted basis for the design life "
        "envelope this platform compares observed operating hours and load "
        "cycles against."
    ),
)

STANDARDS_BASIS: Dict[str, List[Dict[str, Any]]] = {
    ComponentType.STEEL_ROPE.value: [
        _citation(
            standard="ISO 4344:2022",
            title="Steel wire ropes for lifts - Minimum requirements",
            clause="5",
            clause_topic="Rope classes, constructions and grades",
            relevance=(
                "Minimum construction, grade and breaking-force requirements "
                "for lift suspension ropes. Sets what a compliant replacement "
                "rope must be, and therefore what a recovered rope is "
                "measured against."
            ),
        ),
        _citation(
            standard="ISO 4344:2022",
            title="Steel wire ropes for lifts - Minimum requirements",
            clause="Annex",
            clause_topic="Discard criteria for lift ropes",
            relevance=(
                "Broken-wire counts, diameter reduction and corrosion are the "
                "discard criteria that decide whether a rope may stay in "
                "service. No AI output may override them."
            ),
        ),
        _MODERNIZATION_CONTEXT,
    ],
    ComponentType.BRAKE.value: [
        _citation(
            standard="EN 81-20:2020",
            title=(
                "Safety rules for the construction and installation of lifts - "
                "Lifts for the transport of persons and goods - Part 20: "
                "Passenger and goods passenger lifts"
            ),
            clause="5.9.2.2",
            clause_topic="Braking system",
            relevance=(
                "Requirements for the braking system of a traction lift. A "
                "brake is a safety component: return to service requires "
                "inspection and conformity assessment, never a model output."
            ),
        ),
        _MODERNIZATION_CONTEXT,
    ],
    ComponentType.GOVERNOR.value: [
        _citation(
            standard="EN 81-20:2020",
            title=(
                "Safety rules for the construction and installation of lifts - "
                "Part 20: Passenger and goods passenger lifts"
            ),
            clause="5.6.2",
            clause_topic="Overspeed governor and safety gear",
            relevance=(
                "Overspeed governor tripping speed and its interaction with "
                "the safety gear. Type-examined safety component under the "
                "Lifts Directive 2014/33/EU Annex IV."
            ),
        ),
        _citation(
            standard="EN 81-50:2020",
            title=(
                "Safety rules for the construction and installation of lifts - "
                "Examinations and tests - Part 50: Design rules, calculations, "
                "examinations and tests of lift components"
            ),
            clause="5.3",
            clause_topic="Type test of overspeed governors",
            relevance=(
                "The type-test regime a governor must satisfy. Governs what "
                "re-qualification of a recovered governor would require."
            ),
        ),
        _MODERNIZATION_CONTEXT,
    ],
    ComponentType.MOTOR.value: [
        _BEARING_LIFE,
        _citation(
            standard="IEC 60034-1:2022",
            title="Rotating electrical machines - Part 1: Rating and performance",
            clause="8",
            clause_topic="Thermal and performance limits",
            relevance=(
                "Rating, duty class and temperature-rise limits for the "
                "machine. The temperature feature this platform scores against "
                "is meaningful only relative to these limits."
            ),
        ),
        _MODERNIZATION_CONTEXT,
    ],
    ComponentType.SHEAVE.value: [
        _BEARING_LIFE,
        _citation(
            standard="EN 81-20:2020",
            title=(
                "Safety rules for the construction and installation of lifts - "
                "Part 20: Passenger and goods passenger lifts"
            ),
            clause="5.5.3",
            clause_topic="Traction sheaves, pulleys and groove wear",
            relevance=(
                "Groove profile and traction requirements. Groove wear is the "
                "dominant end-of-life mode for a sheave and the reason a "
                "sheave and its ropes are assessed together."
            ),
        ),
        _MODERNIZATION_CONTEXT,
    ],
    ComponentType.DOOR_OPERATOR.value: [
        _citation(
            standard="EN 81-20:2020",
            title=(
                "Safety rules for the construction and installation of lifts - "
                "Part 20: Passenger and goods passenger lifts"
            ),
            clause="5.3",
            clause_topic="Landing and car doors, closing force and protection",
            relevance=(
                "Door closing force, kinetic energy and protective device "
                "requirements - the parameters a door operator must satisfy to "
                "continue in use."
            ),
        ),
        _MODERNIZATION_CONTEXT,
    ],
}


def standards_basis(component_type: str) -> List[Dict[str, Any]]:
    """Return the cited standards basis for a component type.

    Unknown types return the modernization context alone rather than an empty
    list: EN 81-80 frames any decision about a component in an existing lift,
    whatever the component is.
    """
    return list(STANDARDS_BASIS.get(str(component_type), [_MODERNIZATION_CONTEXT]))


def standards_summary(component_type: str) -> Dict[str, Any]:
    """Standards basis plus the honesty flags the UI must render with it."""
    citations = standards_basis(component_type)
    return {
        "component_type": component_type,
        "citations": citations,
        "unverified_clause_count": sum(
            1 for citation in citations if citation["verification"] == CLAUSE_UNVERIFIED
        ),
        "verification_notice": VERIFICATION_NOTICE,
    }


def all_standards() -> Dict[str, Any]:
    """Every citation in the catalogue, for the compliance documentation view."""
    return {
        "by_component_type": {
            component_type: standards_basis(component_type)
            for component_type in ComponentType.values()
        },
        "distinct_standards": sorted(
            {
                citation["standard"]
                for citations in STANDARDS_BASIS.values()
                for citation in citations
            }
        ),
        "verification_notice": VERIFICATION_NOTICE,
    }
