"""Append-only, tamper-evident audit chain (SHA-256).

Design
------
Every state change in the platform appends one row to ``audit_logs``. Each row
stores the hash of the row before it, so the log forms a chain:

    record 1 -> hash 1
    record 2 + hash 1 -> hash 2
    record 3 + hash 2 -> hash 3

Recomputing the chain detects any retroactive edit: changing an old snapshot
changes its hash, which no longer matches the ``previous_hash`` recorded by the
next row. Verification therefore reports the *first* row at which the chain
breaks.

This is tamper **evidence**, not a blockchain: there is no distributed
consensus, no proof of work, and an attacker with full write access to the
database could in principle rebuild the entire chain. It raises the cost of
silent tampering and gives auditors a reproducible integrity check.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import GENESIS_HASH, chain_hash
from app.models.audit import AuditChainLock, AuditLog
from app.utils.helpers import utcnow


def _acquire_chain_lock(db: Session) -> None:
    """Block until this transaction holds the exclusive audit-chain lock.

    See :class:`app.models.audit.AuditChainLock` for why an ``UPDATE`` (not a
    Python-level lock) is the mechanism: it is a real row-level write lock
    that the database itself enforces across concurrent connections, and it
    is released automatically when this transaction commits or rolls back -
    i.e. exactly when the row this call's caller is about to insert becomes
    visible as the new chain head to everyone else.
    """
    db.execute(
        update(AuditChainLock).where(AuditChainLock.id == 1).values(version=AuditChainLock.version + 1)
    )


def _hash_payload(entry: AuditLog) -> Dict[str, Any]:
    """The canonical, hashed subset of an audit row.

    ``id`` is excluded so the hash is independent of database sequence values;
    everything an auditor cares about is included.
    """
    return {
        "entity_type": entry.entity_type,
        "entity_id": entry.entity_id,
        "action": entry.action,
        "data_snapshot": entry.data_snapshot,
        "timestamp": entry.timestamp.isoformat(),
        "actor": entry.actor,
    }


def latest_hash(db: Session) -> str:
    """Return the head hash of the chain (genesis hash when empty)."""
    row = db.execute(
        select(AuditLog.current_hash).order_by(AuditLog.id.desc()).limit(1)
    ).scalar_one_or_none()
    return row or GENESIS_HASH


def record(
    db: Session,
    entity_type: str,
    entity_id: str | int,
    action: str,
    data_snapshot: Optional[Dict[str, Any]] = None,
    actor: Optional[str] = None,
    commit: bool = False,
) -> AuditLog:
    """Append one entry to the audit chain.

    The row is flushed (so it receives an id and participates in the caller
    transaction) but only committed when ``commit=True``. Callers that are
    already inside a request-scoped transaction should leave ``commit`` False
    so the audit entry and the business change succeed or fail together.

    Concurrency: this function takes the audit-chain lock (see
    :func:`_acquire_chain_lock`) before reading the head, so two concurrent
    callers can never compute a hash against the same ``previous_hash`` - the
    second blocks until the first's transaction ends.
    """
    _acquire_chain_lock(db)
    previous = latest_hash(db)
    entry = AuditLog(
        entity_type=str(entity_type),
        entity_id=str(entity_id),
        action=str(action),
        data_snapshot=data_snapshot or {},
        previous_hash=previous,
        timestamp=utcnow(),
        actor=actor or settings.AUDIT_ACTOR_DEFAULT,
    )
    entry.current_hash = chain_hash(previous, _hash_payload(entry))
    db.add(entry)
    db.flush()
    if commit:
        db.commit()
        db.refresh(entry)
    return entry


def list_for_entity(
    db: Session, entity_type: str, entity_id: str | int, limit: int = 200
) -> List[AuditLog]:
    """Return the audit history for one entity, newest first."""
    statement = (
        select(AuditLog)
        .where(AuditLog.entity_type == str(entity_type))
        .where(AuditLog.entity_id == str(entity_id))
        .order_by(AuditLog.id.desc())
        .limit(limit)
    )
    return list(db.execute(statement).scalars().all())


def list_all(
    db: Session,
    limit: int = 100,
    offset: int = 0,
    entity_type: Optional[str] = None,
    action: Optional[str] = None,
) -> tuple[List[AuditLog], int]:
    """Paginated view of the whole chain, newest first, with a total count."""
    statement = select(AuditLog)
    count_statement = select(func.count(AuditLog.id))
    if entity_type:
        statement = statement.where(AuditLog.entity_type == entity_type)
        count_statement = count_statement.where(AuditLog.entity_type == entity_type)
    if action:
        statement = statement.where(AuditLog.action == action)
        count_statement = count_statement.where(AuditLog.action == action)

    total = int(db.execute(count_statement).scalar_one())
    rows = list(
        db.execute(statement.order_by(AuditLog.id.desc()).offset(offset).limit(limit))
        .scalars()
        .all()
    )
    return rows, total


def verify_chain(db: Session) -> Dict[str, Any]:
    """Recompute the entire chain and report its integrity.

    Returns
    -------
    ``{"valid": True, "records_checked": n}`` when intact, otherwise
    ``{"valid": False, "invalid_record": id, ...}`` describing the first break.
    """
    entries = list(db.execute(select(AuditLog).order_by(AuditLog.id.asc())).scalars().all())

    if not entries:
        return {
            "valid": True,
            "records_checked": 0,
            "head_hash": GENESIS_HASH,
            "message": "Audit chain is empty - nothing to verify.",
        }

    expected_previous = GENESIS_HASH
    for position, entry in enumerate(entries, start=1):
        if entry.previous_hash != expected_previous:
            return {
                "valid": False,
                "records_checked": position,
                "invalid_record": entry.id,
                "invalid_position": position,
                "reason": "broken_link",
                "message": (
                    f"Audit record {entry.id} does not link to the previous record. "
                    "A record was inserted, removed or reordered."
                ),
                "expected_previous_hash": expected_previous,
                "stored_previous_hash": entry.previous_hash,
            }

        recomputed = chain_hash(entry.previous_hash, _hash_payload(entry))
        if recomputed != entry.current_hash:
            return {
                "valid": False,
                "records_checked": position,
                "invalid_record": entry.id,
                "invalid_position": position,
                "reason": "snapshot_modified",
                "message": (
                    f"Audit record {entry.id} has been modified after it was written. "
                    "The stored hash does not match its content."
                ),
                "expected_hash": recomputed,
                "stored_hash": entry.current_hash,
            }
        expected_previous = entry.current_hash

    return {
        "valid": True,
        "records_checked": len(entries),
        "head_hash": expected_previous,
        "first_record_at": entries[0].timestamp.isoformat(),
        "last_record_at": entries[-1].timestamp.isoformat(),
        "message": "AUDIT CHAIN VALID - every record hash recomputed successfully.",
    }


def chain_stats(db: Session) -> Dict[str, Any]:
    """Aggregate counts used by the audit dashboard."""
    total = int(db.execute(select(func.count(AuditLog.id))).scalar_one())
    by_action = {
        str(action): int(count)
        for action, count in db.execute(
            select(AuditLog.action, func.count(AuditLog.id)).group_by(AuditLog.action)
        ).all()
    }
    by_entity = {
        str(entity): int(count)
        for entity, count in db.execute(
            select(AuditLog.entity_type, func.count(AuditLog.id)).group_by(AuditLog.entity_type)
        ).all()
    }
    return {
        "total_records": total,
        "by_action": by_action,
        "by_entity_type": by_entity,
        "head_hash": latest_hash(db),
    }
