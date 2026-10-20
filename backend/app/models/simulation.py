"""Saved simulation scenarios - simulated futures attached to a real component.

Kept in their own table on purpose. A scenario is a *what-if*, never a
measurement: nothing that reports on the fleet (dashboard, forecast, recovery
exchange, ESRS/BRSR reports, the material-flow ledger) reads this table, and
saving one never changes the component it is attached to.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.utils.helpers import utcnow

if TYPE_CHECKING:  # pragma: no cover
    from app.models.component import Component


class SimulationScenario(Base):
    """One saved run of the lift simulation, started from a real component."""

    __tablename__ = "simulation_scenarios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    component_id: Mapped[int] = mapped_column(
        ForeignKey("components.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(96), nullable=False)
    load_kg: Mapped[float] = mapped_column(Float, nullable=False)
    historical_load_kg: Mapped[Optional[float]] = mapped_column(Float)
    months_simulated: Mapped[int] = mapped_column(Integer, nullable=False)
    #: What the simulation projected - see app.simulation.engine.scenario_summary.
    summary: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_by: Mapped[str] = mapped_column(String(96), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    component: Mapped["Component"] = relationship("Component", back_populates="scenarios")
