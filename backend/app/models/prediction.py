"""Stored AI assessments (advisory disposition recommendations)."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, List, Optional

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.utils.helpers import utcnow

if TYPE_CHECKING:  # pragma: no cover
    from app.models.component import Component


class Prediction(Base):
    """A single immutable AI assessment of a component.

    Predictions are never updated in place - each assessment appends a new row
    so that the passport carries the full decision history.
    """

    __tablename__ = "predictions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    component_id: Mapped[int] = mapped_column(
        ForeignKey("components.id", ondelete="CASCADE"), index=True, nullable=False
    )

    health_score: Mapped[float] = mapped_column(Float, nullable=False)
    #: CONTINUE_USING | COMPONENT_RECOVERY | MATERIAL_RECOVERY | DISPOSE |
    #: DEFER_TO_INSPECTION (abstention).
    recommendation: Mapped[str] = mapped_column(String(24), index=True, nullable=False)
    #: The model's own best guess, even when `recommendation` is DEFER_TO_INSPECTION.
    underlying_recommendation: Mapped[Optional[str]] = mapped_column(String(24))
    #: True when the abstention rule (app.ml.abstention) overrode the argmax class.
    abstained: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    model_version: Mapped[str] = mapped_column(String(48), nullable=False)

    #: List of {factor, impact, description, importance} dictionaries.
    key_factors: Mapped[Optional[List[Any]]] = mapped_column(JSON)
    #: Feature vector actually scored, retained for auditability.
    input_snapshot: Mapped[Optional[dict]] = mapped_column(JSON)
    #: Full class-probability distribution from the Random Forest.
    probabilities: Mapped[Optional[dict]] = mapped_column(JSON)

    safety_flag: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    safety_message: Mapped[Optional[str]] = mapped_column(String(128))

    #: P6 shadow mode: a shadow assessment is computed and stored for later
    #: agreement analysis against a real workshop outcome, but deliberately
    #: does NOT update Component.latest_recommendation/latest_confidence -
    #: the cached columns the dashboard and passport actually display. That
    #: omission (see prediction_service.assess_component_shadow) is the
    #: entire mechanism by which a shadow assessment stays hidden from a
    #: technician instead of a separate visibility flag the UI has to
    #: remember to check everywhere.
    shadow: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    #: Which of the component's lives this assessment describes (see
    #: ``Component.life_cycle_number``). An assessment of an earlier life
    #: does not describe the current one, so it is never shown as current or
    #: counted in the recovery backlog.
    life_cycle_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    #: P6 pilot metric: "technician trust score". 1-5, one-tap, optional -
    #: the one pilot metric that cannot be derived from data already
    #: recorded elsewhere and genuinely needs a person's input.
    technician_trust_rating: Mapped[Optional[int]] = mapped_column(Integer)

    predicted_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, index=True, nullable=False
    )

    component: Mapped["Component"] = relationship("Component", back_populates="predictions")

    __table_args__ = (
        Index("ix_predictions_component_time", "component_id", "predicted_at"),
        Index("ix_predictions_recommendation_time", "recommendation", "predicted_at"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Prediction {self.recommendation} {self.confidence:.2f}>"
