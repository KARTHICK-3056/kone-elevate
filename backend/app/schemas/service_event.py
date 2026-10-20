"""Pydantic schemas for component service history."""

from __future__ import annotations

from datetime import date, datetime
from typing import Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.utils import validators as v
from app.utils.enums import ServiceEventType


class ServiceEventCreate(BaseModel):
    """Payload for appending an event to a component lifecycle history."""

    event_type: str = Field(
        ...,
        description=(
            "INSTALLATION | INSPECTION | MAINTENANCE | REPAIR | MODERNIZATION | "
            "REMOVAL"
        ),
    )
    event_date: date = Field(default_factory=date.today)
    technician: Optional[str] = Field(None, max_length=96)
    description: Optional[str] = Field(None, max_length=2000)

    operating_hours: Optional[float] = Field(
        None, ge=v.MIN_OPERATING_HOURS, le=v.MAX_OPERATING_HOURS
    )
    vibration: Optional[float] = Field(None, ge=v.MIN_VIBRATION, le=v.MAX_VIBRATION)
    temperature: Optional[float] = Field(None, ge=v.MIN_TEMPERATURE, le=v.MAX_TEMPERATURE)
    inspection_score: Optional[float] = Field(
        None, ge=v.MIN_INSPECTION_SCORE, le=v.MAX_INSPECTION_SCORE
    )
    sensor_metadata: Optional[Dict[str, Union[str, float, int, bool]]] = Field(
        None,
        description=(
            "Vendor/sensor-specific readings that do not fit the fixed columns "
            "above (e.g. current_draw_amps, acoustic_emission_db, "
            "door_cycle_count). Flat key/value pairs only - stored as JSONB on "
            "PostgreSQL so the shape can vary freely by component type and "
            "sensor vendor without a schema migration."
        ),
    )

    @field_validator("sensor_metadata")
    @classmethod
    def _check_sensor_metadata(cls, value):
        if value is None:
            return value
        if len(value) > v.MAX_SENSOR_METADATA_KEYS:
            raise ValueError(
                f"sensor_metadata accepts at most {v.MAX_SENSOR_METADATA_KEYS} keys"
            )
        for key in value:
            if not key or len(key) > 64:
                raise ValueError("sensor_metadata keys must be 1-64 characters")
        return value

    #: When true the component record absorbs the readings from this event.
    update_component: bool = Field(
        True, description="Apply the readings in this event to the component record"
    )

    @field_validator("event_type")
    @classmethod
    def _check_event_type(cls, value: str) -> str:
        if value not in ServiceEventType.values():
            raise ValueError(
                f"Invalid event_type '{value}'. Expected one of: "
                + ", ".join(ServiceEventType.values())
            )
        return value

    @field_validator("event_date")
    @classmethod
    def _check_date(cls, value):
        return v.validate_event_date(value)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "event_type": "INSPECTION",
                "event_date": "2026-06-18",
                "technician": "R. Karthik",
                "description": "Annual statutory inspection. Minor sheave groove wear noted.",
                "operating_hours": 19850,
                "vibration": 4.1,
                "temperature": 55,
                "inspection_score": 78,
                "sensor_metadata": {"current_draw_amps": 4.2, "acoustic_emission_db": 61},
                "update_component": True,
            }
        }
    )


class ServiceEventRead(BaseModel):
    """A stored lifecycle event."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    component_id: int
    event_type: str
    event_date: date
    technician: Optional[str] = None
    description: Optional[str] = None
    operating_hours: Optional[float] = None
    vibration: Optional[float] = None
    temperature: Optional[float] = None
    inspection_score: Optional[float] = None
    sensor_metadata: Optional[Dict[str, Union[str, float, int, bool]]] = None
    created_at: datetime


class ServiceEventList(BaseModel):
    """Service history for one component."""

    component_id: str
    total: int
    items: List[ServiceEventRead]
