"""Material-flow ledger - the kilogram record behind every ESRS E5 disclosure.

Why this table exists
---------------------
Before it, component mass was a configuration lookup applied at read time. A
reporting controller could render a number on a screen but could not answer
"how many tonnes of steel left the fleet last quarter?", because nothing was
ever *recorded*. ESRS E5-4 and E5-5 are mass-flow disclosures in tonnes; they
cannot be derived from a table that stores no mass.

Each row is an immutable statement that a given mass of a given material
crossed (or did not cross) the reporting boundary on a given date. The
identifying attributes are denormalised on purpose: the ledger must keep
saying the same thing after the component row is edited or deleted, which is
the whole point of a ledger.

``audit_hash`` pins each row to the audit-chain entry that recorded the same
transition, so an assurance provider can walk from a line in an E5 table back
to a tamper-evident hash.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.utils.helpers import utcnow


class MaterialFlow(Base):
    """One recorded movement of material across the reporting boundary."""

    __tablename__ = "material_flow"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # --- what moved (denormalised: a ledger must outlive the component row) --
    component_pk: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("components.id", ondelete="SET NULL"), index=True
    )
    component_id: Mapped[str] = mapped_column(String(48), index=True, nullable=False)
    component_type: Mapped[str] = mapped_column(String(48), index=True, nullable=False)
    material: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    mass_kg: Mapped[float] = mapped_column(Float, nullable=False)
    mass_source: Mapped[str] = mapped_column(String(24), nullable=False)

    # --- how it moved ------------------------------------------------------
    from_state: Mapped[Optional[str]] = mapped_column(String(32))
    to_state: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    direction: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    #: ESRS E5-5 treatment route. Only set on OUTFLOW rows.
    outflow_route: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    #: True when an inflow is secondary (recovered parts or material) rather than virgin
    #: material - the numerator of the E5-4 secondary-share metric.
    is_secondary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # --- when, who, and what proves it -------------------------------------
    flow_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    actor: Mapped[str] = mapped_column(String(96), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    audit_hash: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    notes: Mapped[Optional[str]] = mapped_column(String(256))

    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    __table_args__ = (
        Index("ix_material_flow_period", "flow_date", "direction"),
        Index("ix_material_flow_material_period", "material", "flow_date"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return (
            f"<MaterialFlow {self.component_id} {self.from_state}->{self.to_state} "
            f"{self.mass_kg}kg {self.material} {self.direction}>"
        )
