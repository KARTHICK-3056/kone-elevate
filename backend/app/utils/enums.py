"""Domain enumerations shared by the ORM models, schemas, ML pipeline and UI.

Enum *values* are the human-readable strings that are persisted in the database
and used as ML categorical levels, which keeps the dataset, the API payloads
and the UI labels perfectly aligned.
"""

from __future__ import annotations

from enum import Enum
from typing import List


class StrEnum(str, Enum):
    """String enum with a readable repr and a convenient values() helper."""

    def __str__(self) -> str:  # pragma: no cover - trivial
        return str(self.value)

    @classmethod
    def values(cls) -> List[str]:
        return [member.value for member in cls]


class ComponentType(StrEnum):
    """Replaceable elevator components covered by the prototype."""

    MOTOR = "Motor"
    STEEL_ROPE = "Steel Rope"
    BRAKE = "Brake"
    GOVERNOR = "Governor"
    DOOR_OPERATOR = "Door Operator"
    SHEAVE = "Sheave"


class Material(StrEnum):
    """Dominant material of a component."""

    STEEL = "Steel"
    CAST_IRON = "Cast Iron"
    ALUMINUM = "Aluminum"
    COPPER = "Copper"
    COMPOSITE = "Composite"


class Recommendation(StrEnum):
    """AI-assisted end-of-use decision for a component (advisory only).

    The four categories follow one decision flow (``app.ml.decision_flow``):

    1. ``CONTINUE_USING`` - the component is still suitable for its CURRENT
       device and application and keeps operating there unchanged. It is never
       moved to another device or supplied to anyone else.
    2. ``COMPONENT_RECOVERY`` - the complete component is no longer suitable,
       but usable individual SUB-COMPONENTS can be recovered after inspection
       and testing, for technically suitable lower-demand applications. The
       complete component is not refurbished or supplied again.
    3. ``MATERIAL_RECOVERY`` - no usable sub-components, but useful material
       can be recovered from the end-of-life component through the
       appropriate process.
    4. ``DISPOSE`` - no technically suitable option for continued use,
       component recovery or material recovery.

    ``DEFER_TO_INSPECTION`` is a decision-layer abstention outcome, not a
    training label: the Random Forest is trained on and predicts only the
    other four classes (see ``app.ml.train.CLASS_ORDER``). It is applied
    after inference, in ``app.ml.predict``, when the calibrated top-class
    confidence is low or the conformal prediction set contains more than one
    plausible class - see ``app.ml.conformal``.
    """

    CONTINUE_USING = "CONTINUE_USING"
    COMPONENT_RECOVERY = "COMPONENT_RECOVERY"
    MATERIAL_RECOVERY = "MATERIAL_RECOVERY"
    DISPOSE = "DISPOSE"
    DEFER_TO_INSPECTION = "DEFER_TO_INSPECTION"


#: The display names of the four categories, exactly as they are shown.
RECOMMENDATION_LABELS = {
    Recommendation.CONTINUE_USING.value: "Continue Using – No Changes Required",
    Recommendation.COMPONENT_RECOVERY.value: "Component Recovery",
    Recommendation.MATERIAL_RECOVERY.value: "Material Recovery",
    Recommendation.DISPOSE.value: "Dispose",
    Recommendation.DEFER_TO_INSPECTION.value: "Defer to Inspection",
}

#: What each category means, in the words the UI and reports use.
RECOMMENDATION_DESCRIPTIONS = {
    Recommendation.CONTINUE_USING.value: (
        "The component is still suitable for its current device and application and can "
        "continue operating there without modification."
    ),
    Recommendation.COMPONENT_RECOVERY.value: (
        "Recover usable sub-components from the existing component after inspection and "
        "testing. Suitable recovered parts may be redirected to lower-demand applications "
        "where technically appropriate. The complete component is not refurbished or "
        "supplied again."
    ),
    Recommendation.MATERIAL_RECOVERY.value: (
        "The component and its parts are no longer suitable for use. Recover useful "
        "material from the end-of-life component through the appropriate process."
    ),
    Recommendation.DISPOSE.value: (
        "No technically suitable option exists for continued use, component recovery or "
        "material recovery. Dispose of the component through the appropriate route."
    ),
    Recommendation.DEFER_TO_INSPECTION.value: (
        "The model is not confident enough to choose a category. A qualified engineer "
        "inspects the component and decides."
    ),
}

#: Codes stored before the categories were renamed. Used by the database
#: migration and wherever historical records (e.g. the append-only audit
#: chain, which cannot be rewritten) are read back.
LEGACY_RECOMMENDATIONS = {
    "REUSE": Recommendation.CONTINUE_USING.value,
    "REFURBISH": Recommendation.COMPONENT_RECOVERY.value,
    "RECYCLE": Recommendation.MATERIAL_RECOVERY.value,
}


def canonical_recommendation(value):
    """A recommendation code in the current vocabulary (legacy codes mapped)."""
    if value is None:
        return None
    return LEGACY_RECOMMENDATIONS.get(str(value), str(value))


def recommendation_label(value) -> str:
    """The display name of a recommendation code (legacy codes accepted)."""
    code = canonical_recommendation(value)
    return RECOMMENDATION_LABELS.get(code, str(code) if code else "Not assessed")


class LifecycleStatus(StrEnum):
    """Physical/administrative lifecycle state of a component.

    This is deliberately distinct from :class:`Recommendation`: the AI proposes
    a disposition, humans move the component through the lifecycle.
    """

    ACTIVE = "ACTIVE"
    UNDER_INSPECTION = "UNDER_INSPECTION"
    REMOVED = "REMOVED"
    RECOVERED = "RECOVERED"
    #: Being dismantled so its usable sub-components can be recovered and
    #: tested for technically suitable lower-demand applications. The complete
    #: component itself never returns to service.
    PART_RECOVERY = "PART_RECOVERY"
    MATERIAL_RECOVERED = "MATERIAL_RECOVERED"
    DISPOSED = "DISPOSED"


class MaterialFlowDirection(StrEnum):
    """Where a lifecycle transition sits relative to the reporting boundary.

    The boundary is the *installed fleet under management*. Material crossing
    it in either direction is disclosable under ESRS E5; movement inside it is
    recorded for traceability but must not be counted in E5-4 or E5-5.
    """

    INFLOW = "INFLOW"
    OUTFLOW = "OUTFLOW"
    INTERNAL = "INTERNAL"


class OutflowRoute(StrEnum):
    """ESRS E5-5 treatment route for material leaving the boundary.

    The first three are 'diverted from disposal', the last three are 'directed
    to disposal' - the split E5-5 requires.
    """

    PREPARATION_FOR_REUSE = "PREPARATION_FOR_REUSE"
    RECYCLING = "RECYCLING"
    OTHER_RECOVERY = "OTHER_RECOVERY"
    INCINERATION = "INCINERATION"
    LANDFILL = "LANDFILL"
    OTHER_DISPOSAL = "OTHER_DISPOSAL"


#: E5-5 routes that count as diverted from disposal.
DIVERTED_FROM_DISPOSAL = frozenset(
    {
        OutflowRoute.PREPARATION_FOR_REUSE.value,
        OutflowRoute.RECYCLING.value,
        OutflowRoute.OTHER_RECOVERY.value,
    }
)

#: E5-5 routes that count as directed to disposal.
DIRECTED_TO_DISPOSAL = frozenset(
    {
        OutflowRoute.INCINERATION.value,
        OutflowRoute.LANDFILL.value,
        OutflowRoute.OTHER_DISPOSAL.value,
    }
)


class MassSource(StrEnum):
    """Provenance of the mass figure recorded on a material-flow row.

    ESRS assurance asks where a kilogram came from. ``CONFIG_ESTIMATE`` is the
    prototype default and is *not* an acceptable basis for a filed disclosure;
    it is recorded explicitly so a report can state how much of its total rests
    on estimates rather than weighed values.
    """

    MEASURED = "MEASURED"
    COMPONENT_RECORD = "COMPONENT_RECORD"
    CONFIG_ESTIMATE = "CONFIG_ESTIMATE"


class Role(StrEnum):
    """User roles enforced by the authentication and authorisation layer.

    ``READ_ONLY_AUDITOR`` is the one role every mutating endpoint checks for
    and rejects: an auditor can see everything and change nothing. The other
    four roles are treated as equally able to author changes, except the two
    endpoints that name a narrower role explicitly (see ``deps.require_roles``
    call sites) - creating a user, and anchoring the audit chain.
    """

    TECHNICIAN = "technician"
    SUPERVISOR = "supervisor"
    RECOVERY_PLANNER = "recovery_planner"
    SUSTAINABILITY_CONTROLLER = "sustainability_controller"
    READ_ONLY_AUDITOR = "read_only_auditor"


class ServiceEventType(StrEnum):
    """Types of lifecycle events recorded against a component."""

    INSTALLATION = "INSTALLATION"
    INSPECTION = "INSPECTION"
    MAINTENANCE = "MAINTENANCE"
    REPAIR = "REPAIR"
    MODERNIZATION = "MODERNIZATION"
    REMOVAL = "REMOVAL"


class WorkshopOutcome(StrEnum):
    """What actually happened to a component - the label vocabulary.

    Used by the weak labels harvested from KONE service orders
    (``app.integrations.kone_labels``) and scored against the AI's
    recommendation by ``agreement_service.score_weak_labels``. Deliberately a
    small, fixed set rather than free text, so it aggregates into a training
    label without an NLP step.
    """

    #: The component stayed in its current application.
    CONTINUED_IN_SERVICE = "CONTINUED_IN_SERVICE"
    #: Usable sub-components were recovered, tested and used.
    PARTS_RECOVERED = "PARTS_RECOVERED"
    MATERIAL_RECOVERED = "MATERIAL_RECOVERED"
    DISPOSED = "DISPOSED"
    FAILED_INSPECTION = "FAILED_INSPECTION"


class AuditAction(StrEnum):
    """Actions recorded in the append-only audit chain."""

    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    PREDICT = "PREDICT"
    SERVICE_EVENT = "SERVICE_EVENT"
    STATUS_CHANGE = "STATUS_CHANGE"
    MATERIAL_FLOW = "MATERIAL_FLOW"
    CHAIN_ANCHOR = "CHAIN_ANCHOR"
    PREDICTION_FEEDBACK = "PREDICTION_FEEDBACK"
    SCENARIO_SAVED = "SCENARIO_SAVED"
    SCENARIO_DELETED = "SCENARIO_DELETED"
    INSPECTION_RECORDED = "INSPECTION_RECORDED"
    TELEMETRY_INGESTED = "TELEMETRY_INGESTED"


class ImpactLevel(StrEnum):
    """Qualitative strength of an explainability factor."""

    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"
    POSITIVE = "positive"


#: Component types that can never be released on an AI recommendation alone.
SAFETY_CRITICAL_TYPES = frozenset(
    {
        ComponentType.STEEL_ROPE.value,
        ComponentType.BRAKE.value,
        ComponentType.GOVERNOR.value,
    }
)

#: The mandatory banner shown for safety-critical components.
SAFETY_GATE_MESSAGE = "MANDATORY HUMAN INSPECTION"

#: Wording used everywhere a recommendation is surfaced.
RECOMMENDATION_DISCLAIMER = (
    "AI-assisted end-of-use recommendation. Advisory only - this is not a "
    "certification, approval or authorisation to operate an elevator."
)

#: Prototype data disclosure shown in the UI and documentation.
SYNTHETIC_DATA_NOTICE = (
    "Prototype uses synthetic degradation data. Production deployment requires "
    "validation against real historical component service, inspection, sensor "
    "and removal records."
)


def is_safety_critical(component_type: str) -> bool:
    """Return True when the component type requires human inspection."""
    return str(component_type) in SAFETY_CRITICAL_TYPES
