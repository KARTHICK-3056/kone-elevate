"""Component ORM model - the core entity behind every digital passport."""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Date, DateTime, Float, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.utils.enums import LifecycleStatus
from app.utils.helpers import days_since, utcnow, years_between

if TYPE_CHECKING:  # pragma: no cover - import cycle guard for type checkers
    from app.models.prediction import Prediction
    from app.models.service_event import ServiceEvent
    from app.models.simulation import SimulationScenario
    from app.models.telemetry import TelemetryReading


class Component(Base):
    """A single replaceable elevator component tracked through its lifecycle."""

    __tablename__ = "components"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # --- identity ---------------------------------------------------------
    component_id: Mapped[str] = mapped_column(String(48), unique=True, index=True, nullable=False)
    serial_number: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    component_type: Mapped[str] = mapped_column(String(48), index=True, nullable=False)
    material: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    manufacturer: Mapped[Optional[str]] = mapped_column(String(96))
    origin: Mapped[Optional[str]] = mapped_column(String(96), index=True)
    installation_date: Mapped[Optional[date]] = mapped_column(Date, index=True)
    #: Weighed mass of this individual unit. Null means no one has weighed it,
    #: and the material-flow ledger falls back to the illustrative per-type
    #: estimate in configuration - recording that it did so, because an ESRS
    #: assurance provider will ask which kilograms were measured.
    mass_kg: Mapped[Optional[float]] = mapped_column(Float)
    #: Specific material grade (e.g. ``ductile_iron`` for a sheave), a key of
    #: ``app.ml.life_model.MATERIAL_GRADES``. ``material`` says what a part is
    #: mostly made of; the grade says which variant, and that is what moves
    #: its life - a sintered brake lining outlasts a polymer one. Null means
    #: "not recorded" and the life model assumes the default for the material,
    #: saying so on the passport.
    material_grade: Mapped[Optional[str]] = mapped_column(String(48))

    # --- operating history ------------------------------------------------
    operating_hours: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    load_cycles: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    average_load: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    vibration: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    temperature: Mapped[float] = mapped_column(Float, default=25.0, nullable=False)

    # --- service history --------------------------------------------------
    service_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    repair_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failure_history: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    inspection_score: Mapped[float] = mapped_column(Float, default=100.0, nullable=False)
    last_service_date: Mapped[Optional[date]] = mapped_column(Date)

    # --- derived / lifecycle ---------------------------------------------
    health_score: Mapped[Optional[float]] = mapped_column(Float, index=True)
    #: Cached from the most recent Prediction row, the same way health_score
    #: already is (see prediction_service.assess_component). Without this,
    #: "what is the current recommendation" - the single most common
    #: dashboard question - means a MAX(id) GROUP BY scan over the entire,
    #: forever-growing predictions table on every request. Measured at
    #: 200k components / 600k+ predictions (scripts/load_test.py): dropping
    #: that subquery in favour of reading this column took
    #: GET /dashboard/summary from a p95 of 1.75s to single-digit
    #: milliseconds. Predictions themselves stay append-only and untouched;
    #: this is a read-optimisation cache, not a second source of truth.
    latest_recommendation: Mapped[Optional[str]] = mapped_column(String(24), index=True)
    latest_confidence: Mapped[Optional[float]] = mapped_column(Float)
    current_status: Mapped[str] = mapped_column(
        String(32), default=LifecycleStatus.ACTIVE.value, index=True, nullable=False
    )
    location: Mapped[Optional[str]] = mapped_column(String(96), index=True)
    qr_token: Mapped[str] = mapped_column(String(48), unique=True, index=True, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(String(512))

    #: How many times this physical component has been put into service.
    #: 1 for a part installed new. A removed component is never put back into
    #: service (see ``app.utils.lifecycle``), so values above 1 only exist on
    #: records written before whole-component refits were withdrawn.
    #: This is the number a circular economy is actually judged on - how
    #: many times material goes round before it leaves - and without it a
    #: part in its second life is indistinguishable from a part in its
    #: first. Note it counts *lives*, not loops: a component removed and
    #: still sitting in the exchange has had one life, not one and a half.
    life_cycle_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # --- tenant scope (P4 multi-tenancy) -----------------------------------
    #: Hard row-level boundary - see ``app.core.tenancy``. Denormalised onto
    #: the component (rather than derived from ``location`` free text) so
    #: scoping is an indexed equality check, not a string parse.
    country: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    #: Soft default only - see ``app.core.tenancy``.
    frontline_unit: Mapped[Optional[str]] = mapped_column(String(96), index=True)

    # --- digital product passport (CPR (EU) 2024/3110) ---------------------
    #: Persistent DPP identifier. Null means "derive the default from
    #: component_id"; an explicit value lets an identifier issued by another
    #: system be adopted without rewriting the component id.
    dpp_id: Mapped[Optional[str]] = mapped_column(String(128), unique=True, index=True)
    #: The economic operator a market-surveillance authority contacts about
    #: this product. Required by CPR before a passport may be placed on the
    #: market; null falls back to the deployment-wide default.
    economic_operator: Mapped[Optional[str]] = mapped_column(String(160))
    economic_operator_id: Mapped[Optional[str]] = mapped_column(String(64))

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    # --- relationships ----------------------------------------------------
    service_events: Mapped[List["ServiceEvent"]] = relationship(
        "ServiceEvent",
        back_populates="component",
        cascade="all, delete-orphan",
        order_by="ServiceEvent.event_date.desc()",
    )
    predictions: Mapped[List["Prediction"]] = relationship(
        "Prediction",
        back_populates="component",
        cascade="all, delete-orphan",
        order_by="Prediction.predicted_at.desc()",
    )
    #: Simulated what-ifs attached to this part (never fleet data).
    scenarios: Mapped[List["SimulationScenario"]] = relationship(
        "SimulationScenario",
        back_populates="component",
        cascade="all, delete-orphan",
        order_by="SimulationScenario.created_at.desc()",
    )
    #: Readings pushed by sensors or controller exports.
    telemetry: Mapped[List["TelemetryReading"]] = relationship(
        "TelemetryReading",
        back_populates="component",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )

    __table_args__ = (
        Index("ix_components_type_status", "component_type", "current_status"),
        Index("ix_components_status_health", "current_status", "health_score"),
        Index("ix_components_country_unit", "country", "frontline_unit"),
    )

    # --- convenience ------------------------------------------------------
    @property
    def component_age(self) -> float:
        """Age in years derived from the installation date."""
        return years_between(self.installation_date)

    @property
    def days_since_last_service(self) -> int:
        """Days since the most recent service event (falls back to install date)."""
        return days_since(self.last_service_date or self.installation_date)

    @property
    def latest_prediction(self) -> Optional["Prediction"]:
        """Most recent NON-SHADOW AI assessment **of the current life**, if any.

        ``predictions`` is ordered newest-first (see the relationship's
        ``order_by`` above); a shadow-mode assessment (P6 - see
        ``app.services.prediction_service.assess_component_shadow``) is
        skipped here even when it is the chronologically newest row, because
        this property backs every technician-facing "current recommendation"
        view (the passport, component detail, component list) - the same
        place ``Component.latest_recommendation`` is cached from. Without
        this filter, a shadow assessment would stay out of the *cached*
        columns but still leak into any view built from this property
        instead, defeating the entire point of shadow mode.

        Assessments from an earlier life are skipped for the same reason.
        An assessment of an earlier life describes a different physical
        condition to the current one; carrying the old verdict forward would
        put a stale category on the passport and count the part in the
        recovery backlog of a life it is no longer in.
        """
        for prediction in self.predictions:
            if prediction.shadow:
                continue
            if prediction.life_cycle_number != self.life_cycle_number:
                continue
            return prediction
        return None

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Component {self.component_id} {self.component_type} {self.current_status}>"
