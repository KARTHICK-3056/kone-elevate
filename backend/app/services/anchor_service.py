"""Publishing the audit-chain head so tamper evidence survives a DBA.

The threat the hash chain does not address
------------------------------------------
``verify_chain`` recomputes every hash and detects any record edited in place.
It cannot detect a *rebuild*: an administrator with write access can delete a
record, re-hash every subsequent row, and produce a chain that verifies
perfectly. From inside the database the forgery is invisible, because the
database is the only witness.

Anchoring adds a witness outside it. Once the head hash for a given day is
published somewhere the administrator does not control, any later rewrite of
history before that day yields a head that no longer matches the published
value. The rewrite becomes detectable by anyone holding the external copy.

Honest status of this implementation
------------------------------------
The mechanism is complete; the external witness is not configured. With
``CHAIN_ANCHOR_WEBHOOK_URL`` unset, anchors are written to the database and to
a local append-only file - both of which a determined administrator can also
rewrite. Every anchor therefore records ``published_to``, and
:func:`anchor_status` reports how many anchors have a genuine external
witness. Right now that number is zero, and the API says so rather than
implying a protection that is not there.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import BACKEND_ROOT, settings
from app.models.audit import AuditLog, ChainAnchor
from app.services import audit_service
from app.utils.enums import AuditAction
from app.utils.helpers import utcnow

LOCAL_ONLY = "local-only (no external witness configured)"


def anchor_log_path() -> Path:
    """Absolute path of the local append-only anchor log."""
    raw = Path(settings.CHAIN_ANCHOR_LOG_PATH)
    return raw if raw.is_absolute() else (BACKEND_ROOT / raw)


def _head_at(db: Session, through: date) -> tuple[Optional[str], int]:
    """Chain head hash and record count as of the end of ``through``."""
    row = db.execute(
        select(AuditLog.current_hash)
        .where(func.date(AuditLog.timestamp) <= through.isoformat())
        .order_by(AuditLog.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    count = int(
        db.execute(
            select(func.count(AuditLog.id)).where(
                func.date(AuditLog.timestamp) <= through.isoformat()
            )
        ).scalar_one()
    )
    return row, count


def _append_local_log(payload: Dict[str, Any]) -> None:
    path = anchor_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def create_anchor(
    db: Session,
    anchor_date: Optional[date] = None,
    actor: str = "system",
    published_to: Optional[str] = None,
    external_receipt: Optional[str] = None,
    commit: bool = True,
) -> Optional[ChainAnchor]:
    """Record a commitment to the chain head as of ``anchor_date``.

    Idempotent per date: re-anchoring the same day returns the existing row
    rather than creating a second, contradictory commitment. Returns ``None``
    when the chain has no records on or before that date - there is nothing to
    commit to.
    """
    when = anchor_date or utcnow().date()

    existing = db.execute(
        select(ChainAnchor).where(ChainAnchor.anchor_date == when)
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    head_hash, record_count = _head_at(db, when)
    if head_hash is None:
        return None

    anchor = ChainAnchor(
        anchor_date=when,
        head_hash=head_hash,
        record_count=record_count,
        published_to=published_to,
        external_receipt=external_receipt,
    )
    db.add(anchor)
    db.flush()

    payload = {
        "anchor_date": when.isoformat(),
        "head_hash": head_hash,
        "record_count": record_count,
        "published_to": published_to or LOCAL_ONLY,
        "recorded_at": utcnow().isoformat(),
    }
    _append_local_log(payload)

    audit_service.record(
        db,
        entity_type="chain_anchor",
        entity_id=when.isoformat(),
        action=AuditAction.CHAIN_ANCHOR.value,
        data_snapshot=payload,
        actor=actor,
    )
    if commit:
        db.commit()
        db.refresh(anchor)
    return anchor


def list_anchors(db: Session, limit: int = 90) -> List[ChainAnchor]:
    """Most recent anchors, newest first."""
    return list(
        db.execute(
            select(ChainAnchor).order_by(ChainAnchor.anchor_date.desc()).limit(limit)
        )
        .scalars()
        .all()
    )


def anchor_to_dict(anchor: ChainAnchor) -> Dict[str, Any]:
    return {
        "anchor_date": anchor.anchor_date.isoformat(),
        "head_hash": anchor.head_hash,
        "record_count": anchor.record_count,
        "published_to": anchor.published_to,
        "externally_witnessed": bool(anchor.published_to),
        "external_receipt": anchor.external_receipt,
        "created_at": anchor.created_at.isoformat(),
    }


def anchor_status(db: Session) -> Dict[str, Any]:
    """How much of the chain is actually covered by an external witness."""
    anchors = list_anchors(db, limit=365)
    external = [anchor for anchor in anchors if anchor.published_to]
    latest_external = external[0] if external else None

    return {
        "total_anchors": len(anchors),
        "externally_witnessed_anchors": len(external),
        "latest_anchor": anchor_to_dict(anchors[0]) if anchors else None,
        "latest_external_anchor": (
            anchor_to_dict(latest_external) if latest_external else None
        ),
        "external_store_configured": bool(settings.CHAIN_ANCHOR_WEBHOOK_URL),
        "local_log_path": str(anchor_log_path()),
        "current_head_hash": audit_service.latest_hash(db),
        "protection": (
            "Chain rewrites before the latest externally witnessed anchor are "
            "detectable."
            if latest_external
            else (
                "NOT PROTECTED against a database administrator. No external "
                "witness is configured, so every anchor lives in the same "
                "database (and on the same host) as the chain it commits to. "
                "Set CHAIN_ANCHOR_WEBHOOK_URL to publish head hashes to an "
                "append-only store outside this system."
            )
        ),
    }
