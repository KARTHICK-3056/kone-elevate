"""Pydantic schemas for the dashboard and analytics endpoints."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.utils.enums import SYNTHETIC_DATA_NOTICE


class CountItem(BaseModel):
    """Generic name/value pair used by the charts."""

    name: str
    value: float
    secondary: Optional[float] = None


class DashboardSummary(BaseModel):
    """Headline figures for the command-centre dashboard."""

    total_components: int
    assessed_components: int
    continue_using: int
    component_recovery: int
    material_recovery: int
    disposal: int
    average_health_score: float
    potential_recovery_value: float
    estimated_co2_avoided_kg: float
    estimated_co2_avoided_tonnes: float
    components_awaiting_inspection: int
    safety_critical_components: int
    audit_records: int
    currency: str
    currency_symbol: str
    estimate_basis: str
    data_notice: str = SYNTHETIC_DATA_NOTICE


class DispositionBreakdown(BaseModel):
    """Distribution of AI dispositions across the assessed fleet."""

    items: List[CountItem]
    total: int
    unassessed: int


class HealthDistribution(BaseModel):
    """Health-score histogram plus band counts."""

    buckets: List[CountItem]
    bands: List[CountItem]
    average: float
    median: float
    assessed: int


class ComponentTypeBreakdown(BaseModel):
    """Fleet composition by component type."""

    items: List[CountItem]
    total: int


class LifecycleBreakdown(BaseModel):
    """Fleet composition by lifecycle status."""

    items: List[CountItem]
    total: int


class MonthlyActivity(BaseModel):
    """Service events and assessments per calendar month."""

    items: List[Dict[str, Any]]


class ConfidenceDistribution(BaseModel):
    """Distribution of model confidence across stored predictions."""

    buckets: List[CountItem]
    average: float
    total: int


class ImpactSummary(BaseModel):
    """Prototype economic and environmental impact of the assessed fleet."""

    model_config = ConfigDict(protected_namespaces=())

    components_assessed: int
    components_diverted_from_disposal: int
    diversion_rate_percent: float
    total_recovery_value: float
    total_new_part_cost: float
    avoided_procurement_share_percent: float
    total_co2_avoided_kg: float
    total_co2_avoided_tonnes: float
    by_disposition: Dict[str, Dict[str, float]]
    by_component_type: Dict[str, Dict[str, float]]
    currency: str
    currency_symbol: str
    estimate_basis: str
    disclaimer: str
    constants: Optional[Dict[str, Any]] = None


class AnalyticsResponse(BaseModel):
    """Everything the analytics page needs, in a single round trip."""

    summary: DashboardSummary
    disposition: DispositionBreakdown
    health: HealthDistribution
    component_types: ComponentTypeBreakdown
    lifecycle: LifecycleBreakdown
    confidence: ConfidenceDistribution
    monthly_activity: MonthlyActivity
    impact: ImpactSummary
    recovery_value_by_type: List[CountItem] = Field(default_factory=list)
    safety_queue: List[Dict[str, Any]] = Field(default_factory=list)
    feature_importance: List[Dict[str, Any]] = Field(default_factory=list)
    filters_applied: Dict[str, Any] = Field(default_factory=dict)
    data_notice: str = SYNTHETIC_DATA_NOTICE
