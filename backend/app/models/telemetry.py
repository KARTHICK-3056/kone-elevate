"""Readings pushed by any sensor or controller - no vendor account required.

The published KONE API is one way a lift's usage and condition could reach
this platform; it is not the only one, and this build has no access to it.
Buildings commonly have their own sources: a retrofit IoT kit (accelerometer
and temperature probe on the machine, a trip counter), a controller's event
log exported to CSV, or a third-party lift monitoring system. This table is
the vendor-neutral landing place for all of them.

Every row keeps its ``source`` so a figure derived from it can say where it
came from, and ``(component, recorded_at, source)`` is unique so a gateway
that retries a batch - which real gateways do - cannot double-count trips.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.utils.helpers import utcnow

if TYPE_CHECKING:  # pragma: no cover
    from app.models.component import Component


class TelemetryReading(Base):
    """One timestamped reading (or counter increment) for one component."""

    __tablename__ = "telemetry_readings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    component_id: Mapped[int] = mapped_column(
        ForeignKey("components.id", ondelete="CASCADE"), index=True, nullable=False
    )
    recorded_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    #: e.g. "iot-retrofit", "controller-export", "monitoring-system".
    source: Mapped[str] = mapped_column(String(48), nullable=False)

    #: Journeys since the previous reading from this source (a counter delta).
    trips: Mapped[Optional[int]] = mapped_column(Integer)
    #: Motor running seconds since the previous reading.
    run_seconds: Mapped[Optional[float]] = mapped_column(Float)
    #: Average car load over the interval, in kg or as % of rated load.
    load_kg: Mapped[Optional[float]] = mapped_column(Float)
    load_percent: Mapped[Optional[float]] = mapped_column(Float)
    vibration: Mapped[Optional[float]] = mapped_column(Float)
    temperature: Mapped[Optional[float]] = mapped_column(Float)

    received_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    received_by: Mapped[str] = mapped_column(String(96), nullable=False)

    component: Mapped["Component"] = relationship("Component", back_populates="telemetry")

    __table_args__ = (
        UniqueConstraint("component_id", "recorded_at", "source", name="uq_telemetry_reading"),
        Index("ix_telemetry_component_time", "component_id", "recorded_at"),
    )
