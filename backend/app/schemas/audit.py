"""Pydantic schemas for the audit chain API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class AuditRecordRead(BaseModel):
    """One entry in the append-only chain."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    entity_type: str
    entity_id: str
    action: str
    data_snapshot: Optional[Dict[str, Any]] = None
    previous_hash: str
    current_hash: str
    timestamp: datetime
    actor: str


class AuditPage(BaseModel):
    """Paginated audit listing."""

    items: List[AuditRecordRead]
    total: int
    page: int
    page_size: int
    pages: int


class AuditVerification(BaseModel):
    """Result of recomputing the whole chain.

    ``valid=True`` returns ``records_checked``; ``valid=False`` additionally
    identifies the first record at which the chain breaks.
    """

    valid: bool
    records_checked: int
    message: Optional[str] = None
    head_hash: Optional[str] = None
    first_record_at: Optional[str] = None
    last_record_at: Optional[str] = None

    invalid_record: Optional[int] = None
    invalid_position: Optional[int] = None
    reason: Optional[str] = None
    expected_hash: Optional[str] = None
    stored_hash: Optional[str] = None
    expected_previous_hash: Optional[str] = None
    stored_previous_hash: Optional[str] = None

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"valid": True, "records_checked": 25},
                {"valid": False, "records_checked": 12, "invalid_record": 12},
            ]
        }
    )


class AuditStats(BaseModel):
    """Aggregate counters for the audit dashboard."""

    total_records: int
    by_action: Dict[str, int] = Field(default_factory=dict)
    by_entity_type: Dict[str, int] = Field(default_factory=dict)
    head_hash: str
