"""Pydantic schemas for the AI prediction API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

from app.utils import validators as v
from app.utils.enums import (
    RECOMMENDATION_DISCLAIMER,
    SYNTHETIC_DATA_NOTICE,
    canonical_recommendation,
    recommendation_label,
)


class PredictionRequest(BaseModel):
    """Raw feature payload for an ad-hoc assessment (no component required)."""

    component_type: str
    material: str
    component_age: float = Field(0.0, ge=v.MIN_COMPONENT_AGE, le=v.MAX_COMPONENT_AGE, description="Years")
    operating_hours: float = Field(0.0, ge=v.MIN_OPERATING_HOURS, le=v.MAX_OPERATING_HOURS)
    load_cycles: int = Field(0, ge=v.MIN_LOAD_CYCLES, le=v.MAX_LOAD_CYCLES)
    average_load: float = Field(0.0, ge=v.MIN_AVERAGE_LOAD, le=v.MAX_AVERAGE_LOAD, description="kg")
    vibration: float = Field(0.0, ge=v.MIN_VIBRATION, le=v.MAX_VIBRATION, description="mm/s RMS")
    temperature: float = Field(25.0, ge=v.MIN_TEMPERATURE, le=v.MAX_TEMPERATURE, description="Celsius")
    service_count: int = Field(0, ge=0, le=v.MAX_SERVICE_COUNT)
    repair_count: int = Field(0, ge=0, le=v.MAX_REPAIR_COUNT)
    failure_history: int = Field(0, ge=0, le=v.MAX_FAILURE_HISTORY)
    inspection_score: float = Field(100.0, ge=v.MIN_INSPECTION_SCORE, le=v.MAX_INSPECTION_SCORE)
    days_since_last_service: int = Field(0, ge=0, le=v.MAX_DAYS_SINCE_SERVICE)
    material_grade: Optional[str] = Field(
        None,
        max_length=64,
        description=(
            "The component's recorded material grade, if known. Not a model feature: "
            "the decision flow uses it only to name recoverable sub-components. "
            "Leave empty when no grade is recorded - none is assumed."
        ),
    )

    @field_validator("component_type")
    @classmethod
    def _check_type(cls, value: str) -> str:
        return v.validate_component_type(value)

    @field_validator("material")
    @classmethod
    def _check_material(cls, value: str) -> str:
        return v.validate_material(value)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "component_type": "Motor",
                "material": "Steel",
                "component_age": 5.2,
                "operating_hours": 18000,
                "load_cycles": 140000,
                "average_load": 650,
                "vibration": 3.8,
                "temperature": 52,
                "service_count": 5,
                "repair_count": 1,
                "failure_history": 0,
                "inspection_score": 82,
                "days_since_last_service": 90,
            }
        }
    )


class KeyFactor(BaseModel):
    """One explainability factor behind a recommendation."""

    model_config = ConfigDict(protected_namespaces=())

    factor: str = Field(..., description="Human-readable feature label")
    feature: Optional[str] = Field(None, description="Underlying model feature name")
    impact: str = Field(..., description="positive | low | moderate | high | critical")
    description: str
    value: Optional[float] = None
    unit: Optional[str] = None
    deviation_ratio: Optional[float] = None
    model_importance: Optional[float] = None


class ShapFactor(BaseModel):
    """One SHAP (Shapley value) attribution for the predicted class.

    Independent of ``KeyFactor`` - see app.ml.explain module docstring for
    why both are surfaced rather than one replacing the other.
    """

    model_config = ConfigDict(protected_namespaces=())

    factor: str
    feature: str
    shap_value: float
    direction: str = Field(..., description="increases_risk | decreases_risk | neutral")
    value: Optional[Any] = None
    unit: Optional[str] = None


class CostAnalysis(BaseModel):
    """Cost-sensitive decision analysis alongside the probability-argmax choice."""

    cost_optimal_recommendation: str
    expected_cost_by_class: Dict[str, float]
    cost_matrix_version: str
    #: The published safety-versus-circularity trade-off behind those costs
    #: (CE-4). Shipped with the analysis so the ratio can be challenged
    #: rather than inherited - see app/ml/cost_matrix.py.
    safety_circularity_exchange_rate: Optional[Dict[str, Any]] = None


class CircularStrategy(BaseModel):
    """Where this disposition sits on the circular-economy R-ladder (CE-3).

    Advisory only, and deliberately reported *alongside* ``recommendation``
    rather than replacing it: the auditable decision stays the one the model
    actually made, the same precedent ``cost_analysis`` already follows.
    """

    rung: Optional[str] = None
    name: Optional[str] = None
    base_rung: Optional[str] = None
    refined: bool = False
    rule: Optional[str] = None
    eligible: bool = True
    reason_not_eligible: Optional[str] = None
    inputs: Optional[Dict[str, Any]] = None
    version: str
    notice: Optional[str] = None


class DecisionStep(BaseModel):
    """One gate of the end-of-use decision flow and the evidence it used."""

    gate: str
    passed: bool
    evidence: str


class DecisionFlow(BaseModel):
    """The four-category decision flow behind ``recommendation``.

    Suitable for the current application -> Continue Using - No Changes
    Required; else usable sub-components -> Component Recovery; else useful
    material -> Material Recovery; else Dispose. See app.ml.decision_flow.
    """

    recommendation: str
    label: str
    steps: List[DecisionStep]
    subcomponents: Optional[Dict[str, Any]] = Field(
        None, description="Recoverable sub-components (Component Recovery only); named only from a recorded grade"
    )
    material: Optional[Dict[str, Any]] = None
    applied: bool = Field(True, description="False when the abstention rule deferred to inspection")


class HealthBreakdownItem(BaseModel):
    """One weighted term of the transparent health score."""

    factor: str
    weight: float
    ratio: float
    capped_ratio: float
    contribution: float
    penalty_points: float


class ImpactEstimate(BaseModel):
    """Prototype economic and environmental estimate for one component."""

    component_type: Optional[str] = None
    material: Optional[str] = None
    recommendation: Optional[str] = None
    new_part_cost: float
    estimated_recovery_value: float
    value_recovery_factor: float
    component_mass_kg: float
    embodied_co2_kg: float
    estimated_co2_avoided_kg: float
    co2_avoidance_factor: float
    currency: str
    currency_symbol: str
    estimate_basis: str
    disclaimer: str


class PredictionResponse(BaseModel):
    """Full explainable assessment returned by the prediction endpoints."""

    model_config = ConfigDict(protected_namespaces=())

    recommendation: str = Field(
        ...,
        description=(
            "CONTINUE_USING | COMPONENT_RECOVERY | MATERIAL_RECOVERY | DISPOSE | "
            "DEFER_TO_INSPECTION - the result of the decision flow"
        ),
    )
    recommendation_label: Optional[str] = Field(
        None, description="Display name, e.g. 'Continue Using – No Changes Required'"
    )
    recommendation_text: Optional[str] = Field(
        None, description="What the category means for this component (component-aware)"
    )
    decision_flow: Optional[DecisionFlow] = None
    underlying_recommendation: Optional[str] = Field(
        None, description="The classifier's own argmax, before the decision flow and abstention"
    )
    confidence: float = Field(..., ge=v.MIN_CONFIDENCE, le=v.MAX_CONFIDENCE)
    abstained: bool = Field(False, description="True when the abstention rule overrode the model's argmax")
    prediction_set: Optional[List[str]] = Field(
        None, description="Split-conformal prediction set - classes plausible enough not to rule out"
    )
    health_score: float = Field(..., ge=v.MIN_HEALTH_SCORE, le=v.MAX_HEALTH_SCORE)
    health_band: str
    degradation_index: float
    safety_flag: bool
    safety_message: Optional[str] = None
    safety_note: str
    key_factors: List[KeyFactor]
    shap_factors: Optional[List[ShapFactor]] = None
    cost_analysis: Optional[CostAnalysis] = None
    circular_strategy: Optional[CircularStrategy] = None
    probabilities: Dict[str, float] = Field(default_factory=dict)
    model_version: str
    model_available: bool
    health_breakdown: List[HealthBreakdownItem] = Field(default_factory=list)
    health_methodology: str
    explanation_method: str
    disclaimer: str = RECOMMENDATION_DISCLAIMER
    data_notice: str = SYNTHETIC_DATA_NOTICE
    input_snapshot: Dict[str, Any] = Field(default_factory=dict)
    impact: Optional[ImpactEstimate] = None
    #: Pre-emptive issue forecast (``app.ml.early_warning``): which issues the
    #: component is heading towards, when, what to do first, and the evidence.
    #: Present only for stored components - it needs their service history.
    early_warning: Optional[Dict[str, Any]] = None

    # Present only when the assessment was persisted against a component.
    component_id: Optional[str] = None
    prediction_id: Optional[int] = None
    predicted_at: Optional[datetime] = None


class PredictionRead(BaseModel):
    """A stored prediction row."""

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: int
    component_id: int
    health_score: float
    recommendation: str
    underlying_recommendation: Optional[str] = None
    abstained: bool = False
    confidence: float
    model_version: str
    key_factors: Optional[List[Any]] = None
    probabilities: Optional[Dict[str, float]] = None
    safety_flag: bool
    safety_message: Optional[str] = None
    predicted_at: datetime

    @field_validator("recommendation", "underlying_recommendation", mode="before")
    @classmethod
    def _canonical(cls, value: Optional[str]) -> Optional[str]:
        # Rows written before the category rework carry legacy codes.
        return canonical_recommendation(value) if value else value

    @computed_field  # type: ignore[prop-decorator]
    @property
    def recommendation_label(self) -> str:
        return recommendation_label(self.recommendation)


class PredictionHistory(BaseModel):
    """Assessment history for one component."""

    component_id: str
    total: int
    items: List[PredictionRead]


class ModelInfo(BaseModel):
    """Metadata about the deployed model, surfaced in the UI."""

    model_config = ConfigDict(protected_namespaces=())

    model_available: bool
    model_version: str
    model_path: Optional[str] = None
    trained_at: Optional[str] = None
    classes: List[str] = Field(default_factory=list)
    n_features: Optional[int] = None
    accuracy: Optional[float] = None
    f1_macro: Optional[float] = None
    training_records: Optional[int] = None
    data_source: str = "synthetic"
    error: Optional[str] = None
    data_notice: str = SYNTHETIC_DATA_NOTICE


class PredictionFeedback(BaseModel):
    """One-tap technician trust rating for a single assessment (P6)."""

    trust_rating: int = Field(..., ge=1, le=5, description="1 (do not trust) - 5 (fully trust)")
    notes: Optional[str] = Field(None, max_length=512)
