"""Append-only, tamper-evident audit log backed by a SHA-256 hash chain."""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import JSON, Date, DateTime, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.utils.helpers import utcnow


class AuditLog(Base):
    """One immutable entry in the global audit chain.

    Every row stores the hash of the previous row, so altering any historical
    snapshot invalidates every hash that follows it. This is a lightweight,
    database-native alternative to a blockchain: it proves *tamper evidence*,
    not distributed consensus.
    """

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    entity_type: Mapped[str] = mapped_column(String(48), index=True, nullable=False)
    entity_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    action: Mapped[str] = mapped_column(String(32), index=True, nullable=False)

    #: JSON snapshot of the record at the moment the action happened.
    data_snapshot: Mapped[Optional[dict]] = mapped_column(JSON)

    previous_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    current_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)

    timestamp: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, index=True, nullable=False
    )
    actor: Mapped[str] = mapped_column(String(96), default="system", nullable=False)

    __table_args__ = (Index("ix_audit_entity", "entity_type", "entity_id"),)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<AuditLog {self.id} {self.entity_type}:{self.entity_id} {self.action}>"


class AuditChainLock(Base):
    """Single-row table used purely to serialise audit-chain appends.

    ``audit_service.record`` reads the current chain head and then inserts a
    row that references it - a classic read-then-write race: two concurrent
    requests can both read the same head, both compute a hash chained to it,
    and both insert, forking the chain. ``verify_chain`` then reports a false
    ``broken_link`` on a database nobody tampered with.

    Every append first issues an ``UPDATE`` against this table's one row. An
    ``UPDATE`` always takes a real write lock immediately, on SQLite and
    PostgreSQL alike, so the second of two concurrent transactions blocks
    here until the first commits or rolls back - which is exactly the
    ordering guarantee the hash chain needs. A dedicated table (rather than
    locking the audit_logs head row itself) keeps the lock uncontended by
    ordinary reads of the chain.
    """

    __tablename__ = "audit_chain_lock"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class ChainAnchor(Base):
    """A published commitment to the chain head as it stood on one day.

    The hash chain proves nobody edited a record *in place*. It does not stop
    an administrator with full write access from rebuilding the entire chain
    from some point forward - every hash would recompute correctly, and the
    forgery would be undetectable from inside the database.

    Anchoring closes that gap by putting the head hash somewhere the database
    administrator does not control. Once a day's head hash is published
    externally, rewriting history before that day produces a chain whose head
    no longer matches what was published, and the discrepancy is visible to
    anyone holding the external copy.

    ``published_to`` is null when the anchor exists only locally, which does
    **not** survive a database administrator. That distinction is reported
    rather than hidden: an anchor nobody else holds is a reminder, not
    evidence.
    """

    __tablename__ = "chain_anchors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    anchor_date: Mapped[date] = mapped_column(Date, unique=True, index=True, nullable=False)
    head_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    record_count: Mapped[int] = mapped_column(Integer, nullable=False)
    #: Where the head hash was published. Null means local-only.
    published_to: Mapped[Optional[str]] = mapped_column(String(256))
    #: Whatever the external store returned as proof of receipt.
    external_receipt: Mapped[Optional[str]] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ChainAnchor {self.anchor_date} {self.head_hash[:12]} n={self.record_count}>"
