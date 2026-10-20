"""Pydantic schemas for the Components API."""

from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.prediction import ImpactEstimate
from app.utils import validators as v
from app.utils.enums import ComponentType, LifecycleStatus, Material


class ComponentBase(BaseModel):
    """Fields shared by create and update payloads."""

    component_type: str = Field(..., description="One of the supported elevator component types")
    material: str = Field(..., description="Dominant material of the component")
    serial_number: Optional[str] = Field(None, max_length=64)
    manufacturer: Optional[str] = Field(None, max_length=96)
    origin: Optional[str] = Field(None, max_length=96, description="Site or plant of origin")
    installation_date: Optional[date] = None
    mass_kg: Optional[float] = Field(
        None, gt=0, le=100_000,
        description=(
            "Weighed mass of this individual unit in kg. When null the "
            "material-flow ledger falls back to the illustrative per-type "
            "estimate and records that it did so."
        ),
    )
    location: Optional[str] = Field(None, max_length=96, description="Current physical location")
    material_grade: Optional[str] = Field(
        None,
        max_length=48,
        description=(
            "Specific material grade, e.g. 'ductile_iron' for a sheave. When null "
            "the life model assumes the default grade for the material."
        ),
    )

    operating_hours: float = Field(
        0.0, ge=v.MIN_OPERATING_HOURS, le=v.MAX_OPERATING_HOURS, description="Cumulative run hours"
    )
    load_cycles: int = Field(0, ge=v.MIN_LOAD_CYCLES, le=v.MAX_LOAD_CYCLES)
    average_load: float = Field(0.0, ge=v.MIN_AVERAGE_LOAD, le=v.MAX_AVERAGE_LOAD, description="kg")
    vibration: float = Field(
        0.0, ge=v.MIN_VIBRATION, le=v.MAX_VIBRATION, description="mm/s RMS"
    )
    temperature: float = Field(
        25.0, ge=v.MIN_TEMPERATURE, le=v.MAX_TEMPERATURE, description="Degrees Celsius"
    )

    service_count: int = Field(0, ge=0, le=v.MAX_SERVICE_COUNT)
    repair_count: int = Field(0, ge=0, le=v.MAX_REPAIR_COUNT)
    failure_history: int = Field(0, ge=0, le=v.MAX_FAILURE_HISTORY)
    inspection_score: float = Field(
        100.0, ge=v.MIN_INSPECTION_SCORE, le=v.MAX_INSPECTION_SCORE
    )
    last_service_date: Optional[date] = None
    notes: Optional[str] = Field(None, max_length=512)
    country: Optional[str] = Field(
        None,
        max_length=64,
        description=(
            "Tenant boundary. Defaults to the caller's own country; a caller "
            "with no default (a global role) must supply one explicitly."
        ),
    )
    frontline_unit: Optional[str] = Field(
        None, max_length=96, description="Home branch/site. Defaults to the caller's own unit."
    )

    @field_validator("component_type")
    @classmethod
    def _check_type(cls, value: str) -> str:
        return v.validate_component_type(value)

    @field_validator("material")
    @classmethod
    def _check_material(cls, value: str) -> str:
        return v.validate_material(value)

    @field_validator("material_grade")
    @classmethod
    def _check_grade(cls, value):
        return v.validate_material_grade(value)

    @field_validator("installation_date")
    @classmethod
    def _check_installation(cls, value):
        return v.validate_installation_date(value)

    @field_validator("last_service_date")
    @classmethod
    def _check_service_date(cls, value):
        return v.validate_event_date(value)


class ComponentCreate(ComponentBase):
    """Payload for creating a component."""

    current_status: str = Field(LifecycleStatus.ACTIVE.value)
    run_initial_prediction: bool = Field(
        True, description="Run an AI assessment immediately after creation"
    )

    @field_validator("current_status")
    @classmethod
    def _check_status(cls, value: str) -> str:
        if value not in LifecycleStatus.values():
            raise ValueError(
                f"Invalid current_status '{value}'. Expected one of: "
                + ", ".join(LifecycleStatus.values())
            )
        return value

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "component_type": "Motor",
                "material": "Steel",
                "manufacturer": "KONE MonoSpace",
                "origin": "Chennai Plant",
                "installation_date": "2018-04-12",
                "location": "Chennai, India",
                "operating_hours": 18000,
                "load_cycles": 140000,
                "average_load": 650,
                "vibration": 3.8,
                "temperature": 52,
                "service_count": 5,
                "repair_count": 1,
                "failure_history": 0,
                "inspection_score": 82,
                "run_initial_prediction": True,
            }
        }
    )


class ComponentUpdate(BaseModel):
    """Partial update payload - every field is optional."""

    component_type: Optional[str] = None
    material: Optional[str] = None
    manufacturer: Optional[str] = Field(None, max_length=96)
    origin: Optional[str] = Field(None, max_length=96)
    installation_date: Optional[date] = None
    mass_kg: Optional[float] = Field(
        None, gt=0, le=100_000,
        description=(
            "Weighed mass of this individual unit in kg. When null the "
            "material-flow ledger falls back to the illustrative per-type "
            "estimate and records that it did so."
        ),
    )
    location: Optional[str] = Field(None, max_length=96)
    material_grade: Optional[str] = Field(None, max_length=48)
    operating_hours: Optional[float] = Field(None, ge=v.MIN_OPERATING_HOURS, le=v.MAX_OPERATING_HOURS)
    load_cycles: Optional[int] = Field(None, ge=v.MIN_LOAD_CYCLES, le=v.MAX_LOAD_CYCLES)
    average_load: Optional[float] = Field(None, ge=v.MIN_AVERAGE_LOAD, le=v.MAX_AVERAGE_LOAD)
    vibration: Optional[float] = Field(None, ge=v.MIN_VIBRATION, le=v.MAX_VIBRATION)
    temperature: Optional[float] = Field(None, ge=v.MIN_TEMPERATURE, le=v.MAX_TEMPERATURE)
    service_count: Optional[int] = Field(None, ge=0, le=v.MAX_SERVICE_COUNT)
    repair_count: Optional[int] = Field(None, ge=0, le=v.MAX_REPAIR_COUNT)
    failure_history: Optional[int] = Field(None, ge=0, le=v.MAX_FAILURE_HISTORY)
    inspection_score: Optional[float] = Field(
        None, ge=v.MIN_INSPECTION_SCORE, le=v.MAX_INSPECTION_SCORE
    )
    last_service_date: Optional[date] = None
    current_status: Optional[str] = None
    notes: Optional[str] = Field(None, max_length=512)
    frontline_unit: Optional[str] = Field(None, max_length=96)

    @field_validator("component_type")
    @classmethod
    def _check_type(cls, value):
        return v.validate_component_type(value) if value is not None else value

    @field_validator("material")
    @classmethod
    def _check_material(cls, value):
        return v.validate_material(value) if value is not None else value

    @field_validator("material_grade")
    @classmethod
    def _check_grade(cls, value):
        return v.validate_material_grade(value)

    @field_validator("current_status")
    @classmethod
    def _check_status(cls, value):
        if value is not None and value not in LifecycleStatus.values():
            raise ValueError(
                f"Invalid current_status '{value}'. Expected one of: "
                + ", ".join(LifecycleStatus.values())
            )
        return value

    @field_validator("installation_date")
    @classmethod
    def _check_installation(cls, value):
        return v.validate_installation_date(value)


class PredictionSummary(BaseModel):
    """Compact view of the latest AI assessment, embedded in component reads."""

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: int
    recommendation: str
    confidence: float
    health_score: float
    safety_flag: bool
    safety_message: Optional[str] = None
    model_version: str
    predicted_at: datetime
    #: Recomputed at read time from (component_type, material, recommendation)
    #: - it is cheap and deterministic, so it is never persisted on the row.
    impact: Optional[ImpactEstimate] = None


class ComponentRead(BaseModel):
    """Full component representation returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    component_id: str
    serial_number: str
    component_type: str
    material: str
    manufacturer: Optional[str] = None
    origin: Optional[str] = None
    installation_date: Optional[date] = None
    mass_kg: Optional[float] = None
    material_grade: Optional[str] = None
    #: The recorded grade's name, or "Not Determined". Never guessed.
    material_grade_label: str = "Not Determined"
    location: Optional[str] = None

    operating_hours: float
    load_cycles: int
    average_load: float
    vibration: float
    temperature: float

    service_count: int
    repair_count: int
    failure_history: int
    inspection_score: float
    last_service_date: Optional[date] = None

    health_score: Optional[float] = None
    current_status: str
    life_cycle_number: int = 1
    qr_token: str
    notes: Optional[str] = None
    country: Optional[str] = None
    frontline_unit: Optional[str] = None

    created_at: datetime
    updated_at: datetime

    # Derived, computed on the ORM instance.
    component_age: float = 0.0
    days_since_last_service: int = 0
    is_safety_critical: bool = False
    latest_prediction: Optional[PredictionSummary] = None


class ComponentListItem(BaseModel):
    """Lightweight row used by the components table (keeps payloads small)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    component_id: str
    serial_number: str
    component_type: str
    material: str
    material_grade: Optional[str] = None
    #: The recorded grade's name, or "Not Determined". Never guessed.
    material_grade_label: str = "Not Determined"
    location: Optional[str] = None
    installation_date: Optional[date] = None
    component_age: float = 0.0
    health_score: Optional[float] = None
    current_status: str
    life_cycle_number: int = 1
    country: Optional[str] = None
    frontline_unit: Optional[str] = None
    is_safety_critical: bool = False
    last_service_date: Optional[date] = None
    recommendation: Optional[str] = None
    recommendation_label: Optional[str] = None
    confidence: Optional[float] = None
    safety_flag: bool = False


class ComponentPage(BaseModel):
    """Paginated component listing."""

    items: List[ComponentListItem]
    total: int
    page: int
    page_size: int
    pages: int


class ComponentFilters(BaseModel):
    """Distinct values available for the UI filter controls."""

    component_types: List[str] = Field(default_factory=ComponentType.values)
    materials: List[str] = Field(default_factory=Material.values)
    statuses: List[str] = Field(default_factory=LifecycleStatus.values)
    locations: List[str] = Field(default_factory=list)
    manufacturers: List[str] = Field(default_factory=list)


class QRInfo(BaseModel):
    """QR metadata for a component passport."""

    component_id: str
    qr_token: Optional[str] = None
    passport_url: str
    #: What the printed label actually encodes: the DPP resolver URL, which
    #: outlives any particular deployment of this application.
    encoded_payload: Optional[str] = None
    dpp_id: Optional[str] = None
    qr_image_url: str
    format: str = "PNG"
    error_correction: str = "M"


class ComponentPassport(BaseModel):
    """The complete digital passport for one component."""

    component: ComponentRead
    qr: QRInfo
    qr_data_uri: str
    service_events: List[dict] = Field(default_factory=list)
    predictions: List[dict] = Field(default_factory=list)
    audit_trail: List[dict] = Field(default_factory=list)
    impact: Optional[dict] = None
    #: Which published standard governs this component type, and which clause.
    standards_basis: Optional[dict] = None
    #: Digital Product Passport identity (CPR (EU) 2024/3110).
    dpp: Optional[dict] = None
    #: What the component is made of and what that does to its life
    #: (``app.ml.life_model.material_profile``). Null for types the life
    #: model does not cover yet.
    material_profile: Optional[dict] = None
    #: Manufacturer quality certificate, EN 10204 3.1 layout
    #: (``app.services.quality_certificate_service``).
    quality_certificate: Optional[dict] = None
    #: Usage-adjusted life projection (``app.ml.life_model.assess``).
    life_assessment: Optional[dict] = None
    #: Pre-emptive issue forecast (``app.ml.early_warning``).
    early_warning: Optional[dict] = None
    #: Saved SIMULATED scenarios (app.api.simulation). Never fleet data.
    scenarios: List[dict] = Field(default_factory=list)
    safety_flag: bool = False
    safety_message: Optional[str] = None
    disclaimer: str
    data_notice: str
    generated_at: datetime
