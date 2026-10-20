"""Audit chain API: history, verification and export."""

from __future__ import annotations

import csv
import io
from typing import Optional

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.metrics import record_chain_verification
from app.schemas.audit import AuditPage, AuditRecordRead, AuditStats, AuditVerification
from app.services import audit_service

router = APIRouter(prefix="/audit", tags=["Audit"])


@router.get(
    "/verify",
    response_model=AuditVerification,
    summary="Verify audit-chain integrity",
    description=(
        "Recomputes every SHA-256 hash in the chain from its stored content "
        "and its predecessor. Returns `{valid: true, records_checked: n}` when "
        "the chain is intact, or identifies the first tampered record.\n\n"
        "This proves tamper *evidence*, not distributed consensus - it is not "
        "a blockchain."
    ),
    responses={
        200: {
            "content": {
                "application/json": {
                    "examples": {
                        "valid": {"value": {"valid": True, "records_checked": 25}},
                        "tampered": {
                            "value": {
                                "valid": False,
                                "records_checked": 12,
                                "invalid_record": 12,
                                "reason": "snapshot_modified",
                            }
                        },
                    }
                }
            }
        }
    },
)
def verify(db: Session = Depends(get_db)) -> AuditVerification:
    result = audit_service.verify_chain(db)
    record_chain_verification(bool(result["valid"]))
    return AuditVerification.model_validate(result)


@router.get(
    "/stats",
    response_model=AuditStats,
    summary="Audit chain statistics",
)
def stats(db: Session = Depends(get_db)) -> AuditStats:
    return AuditStats.model_validate(audit_service.chain_stats(db))


@router.get(
    "",
    response_model=AuditPage,
    summary="Browse the audit chain",
    description="Paginated, newest-first view of every recorded action.",
)
def list_audit(
    db: Session = Depends(get_db),
    entity_type: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> AuditPage:
    rows, total = audit_service.list_all(
        db,
        limit=page_size,
        offset=(page - 1) * page_size,
        entity_type=entity_type,
        action=action,
    )
    return AuditPage(
        items=[AuditRecordRead.model_validate(row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
        pages=(total + page_size - 1) // page_size if page_size else 0,
    )


@router.get(
    "/export",
    summary="Export the audit chain as CSV",
    response_class=Response,
)
def export_audit(db: Session = Depends(get_db)) -> Response:
    rows, _ = audit_service.list_all(db, limit=100000, offset=0)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        ["id", "timestamp", "entity_type", "entity_id", "action", "actor", "previous_hash", "current_hash"]
    )
    for row in reversed(rows):
        writer.writerow(
            [
                row.id, row.timestamp.isoformat(), row.entity_type, row.entity_id,
                row.action, row.actor, row.previous_hash, row.current_hash,
            ]
        )
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=kone_elevate_audit_chain.csv"},
    )


@router.get(
    "/{entity_type}/{entity_id}",
    response_model=list[AuditRecordRead],
    summary="Audit history for one entity",
    description=(
        "All chain entries for a single entity, newest first. "
        "Example: `/api/v1/audit/component/KE-MOT-000012`."
    ),
)
def entity_audit(
    entity_type: str,
    entity_id: str,
    db: Session = Depends(get_db),
    limit: int = Query(200, ge=1, le=500),
) -> list[AuditRecordRead]:
    rows = audit_service.list_for_entity(db, entity_type, entity_id, limit=limit)
    return [AuditRecordRead.model_validate(row) for row in rows]
