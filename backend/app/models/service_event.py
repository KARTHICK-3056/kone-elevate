"""Service, inspection, repair and removal events recorded per component."""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import JSON, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.utils.helpers import utcnow

if TYPE_CHECKING:  # pragma: no cover
    from app.models.component import Component


class ServiceEvent(Base):
    """One dated entry in the lifecycle history of a component."""

    __tablename__ = "service_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    component_id: Mapped[int] = mapped_column(
        ForeignKey("components.id", ondelete="CASCADE"), index=True, nullable=False
    )

    event_type: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    event_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    technician: Mapped[Optional[str]] = mapped_column(String(96))
    description: Mapped[Optional[str]] = mapped_column(Text)

    # Sensor / condition readings captured at the time of the event.
    operating_hours: Mapped[Optional[float]] = mapped_column(Float)
    vibration: Mapped[Optional[float]] = mapped_column(Float)
    temperature: Mapped[Optional[float]] = mapped_column(Float)
    inspection_score: Mapped[Optional[float]] = mapped_column(Float)

    #: Vendor/sensor-specific readings that do not fit the four fixed columns
    #: above (e.g. current draw, acoustic emission, door-cycle count). Real
    #: JSONB on PostgreSQL - unlike the other JSON columns in this codebase,
    #: which stay on the generic ``JSON`` type - because the whole point of
    #: this column is a schema that genuinely varies per sensor vendor and
    #: component type, which is exactly what JSONB's indexable, queryable
    #: variable-shape storage is for. On SQLite (tests/dev) this degrades to
    #: the portable ``JSON`` type transparently.
    sensor_metadata: Mapped[Optional[dict]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql")
    )

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    component: Mapped["Component"] = relationship("Component", back_populates="service_events")

    __table_args__ = (Index("ix_service_events_component_date", "component_id", "event_date"),)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ServiceEvent {self.event_type} {self.event_date}>"
