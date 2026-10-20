"""Audit-chain tests, including the tamper-detection scenario."""

from __future__ import annotations

import threading

from app.core.security import GENESIS_HASH, canonical_json, chain_hash
from app.models.audit import AuditLog
from app.services import audit_service


# --------------------------------------------------------------------------
# Chain construction
# --------------------------------------------------------------------------
def test_first_record_links_to_the_genesis_hash(db):
    entry = audit_service.record(
        db, "component", "KE-TEST-000001", "CREATE", {"value": 1}, actor="tester", commit=True
    )
    assert entry.previous_hash == GENESIS_HASH
    assert len(entry.current_hash) == 64


def test_each_record_links_to_its_predecessor(db):
    first = audit_service.record(db, "component", "KE-CHAIN-1", "CREATE", {"n": 1}, commit=True)
    second = audit_service.record(db, "component", "KE-CHAIN-1", "UPDATE", {"n": 2}, commit=True)
    third = audit_service.record(db, "component", "KE-CHAIN-1", "PREDICT", {"n": 3}, commit=True)

    assert second.previous_hash == first.current_hash
    assert third.previous_hash == second.current_hash
    assert len({first.current_hash, second.current_hash, third.current_hash}) == 3


def test_canonical_json_is_order_independent():
    """Two logically identical payloads must hash identically."""
    left = {"b": 2, "a": 1, "nested": {"y": 2, "x": 1}}
    right = {"a": 1, "nested": {"x": 1, "y": 2}, "b": 2}
    assert canonical_json(left) == canonical_json(right)
    assert chain_hash(GENESIS_HASH, left) == chain_hash(GENESIS_HASH, right)


def test_verify_reports_a_valid_chain(db):
    for index in range(5):
        audit_service.record(db, "component", "KE-VERIFY-1", "UPDATE", {"i": index}, commit=True)

    result = audit_service.verify_chain(db)
    assert result["valid"] is True
    assert result["records_checked"] >= 5
    assert "AUDIT CHAIN VALID" in result["message"]


# --------------------------------------------------------------------------
# Tamper detection - the scenario required by the brief
# --------------------------------------------------------------------------
def test_tampering_with_an_old_snapshot_invalidates_the_chain(db):
    """1. write records, 2. verify, 3. tamper, 4. verify again -> invalid."""
    audit_service.record(db, "component", "KE-TAMPER-1", "CREATE", {"health": 90}, commit=True)
    second = audit_service.record(
        db, "component", "KE-TAMPER-1", "UPDATE", {"health": 72}, commit=True
    )
    audit_service.record(db, "component", "KE-TAMPER-1", "PREDICT", {"health": 68}, commit=True)

    assert audit_service.verify_chain(db)["valid"] is True

    # Retroactively rewrite a stored snapshot, exactly as an attacker would.
    tampered = db.get(AuditLog, second.id)
    tampered.data_snapshot = {"health": 99}
    db.commit()

    result = audit_service.verify_chain(db)
    assert result["valid"] is False
    assert result["invalid_record"] == second.id
    assert result["reason"] == "snapshot_modified"
    assert result["expected_hash"] != result["stored_hash"]

    # Restore so later tests in this module see a consistent chain.
    tampered.data_snapshot = {"health": 72}
    db.commit()
    assert audit_service.verify_chain(db)["valid"] is True


def test_deleting_a_record_breaks_the_chain_link(db):
    first = audit_service.record(db, "component", "KE-GAP-1", "CREATE", {"n": 1}, commit=True)
    middle = audit_service.record(db, "component", "KE-GAP-1", "UPDATE", {"n": 2}, commit=True)
    last = audit_service.record(db, "component", "KE-GAP-1", "UPDATE", {"n": 3}, commit=True)

    db.delete(db.get(AuditLog, middle.id))
    db.commit()

    result = audit_service.verify_chain(db)
    assert result["valid"] is False
    assert result["reason"] == "broken_link"
    assert result["invalid_record"] == last.id

    # Repair the chain by removing the orphaned tail.
    db.delete(db.get(AuditLog, last.id))
    db.commit()
    assert db.get(AuditLog, first.id) is not None
    assert audit_service.verify_chain(db)["valid"] is True


# --------------------------------------------------------------------------
# Concurrency - the race condition found in the build audit (plan.md P0)
# --------------------------------------------------------------------------
def test_concurrent_appends_do_not_fork_the_chain(session_factory):
    """10 threads x 10 writes, each on its own DB session/connection.

    Before the audit-chain lock (app.services.audit_service._acquire_chain_lock),
    two threads could both read the same chain head via latest_hash(), both
    compute a hash chained to it, and both insert - forking the chain and
    making verify_chain report a *false* tamper alarm on data nobody touched.
    This reproduces that race at the concurrency the build audit specified
    and asserts the chain is still valid afterwards.
    """
    thread_count, writes_per_thread = 10, 10
    errors: list[BaseException] = []

    def worker(thread_index: int) -> None:
        session = session_factory()
        try:
            for i in range(writes_per_thread):
                audit_service.record(
                    session,
                    "component",
                    f"KE-RACE-{thread_index}",
                    "UPDATE",
                    {"thread": thread_index, "i": i},
                    commit=True,
                )
        except BaseException as exc:  # noqa: BLE001 - surfaced via the assertion below
            errors.append(exc)
        finally:
            session.close()

    threads = [threading.Thread(target=worker, args=(index,)) for index in range(thread_count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)

    assert not errors, f"worker thread(s) raised: {errors}"

    verify_session = session_factory()
    try:
        result = audit_service.verify_chain(verify_session)
        assert result["valid"] is True, result
        assert result["records_checked"] >= thread_count * writes_per_thread
    finally:
        verify_session.close()


def test_history_is_scoped_to_one_entity(db):
    audit_service.record(db, "component", "KE-SCOPE-A", "CREATE", {}, commit=True)
    audit_service.record(db, "component", "KE-SCOPE-B", "CREATE", {}, commit=True)
    audit_service.record(db, "component", "KE-SCOPE-A", "UPDATE", {}, commit=True)

    entries = audit_service.list_for_entity(db, "component", "KE-SCOPE-A")
    assert len(entries) == 2
    assert {entry.entity_id for entry in entries} == {"KE-SCOPE-A"}


# --------------------------------------------------------------------------
# API surface
# --------------------------------------------------------------------------
def test_audit_api_records_every_component_action(client, component_payload):
    created = client.post("/api/v1/components", json=component_payload).json()
    component_id = created["component_id"]

    client.put(f"/api/v1/components/{component_id}", json={"vibration": 5.5})
    client.post(f"/api/v1/components/{component_id}/predict")

    trail = client.get(f"/api/v1/audit/component/{component_id}").json()
    actions = {entry["action"] for entry in trail}
    assert {"CREATE", "UPDATE", "PREDICT"} <= actions

    for entry in trail:
        assert len(entry["current_hash"]) == 64
        assert len(entry["previous_hash"]) == 64
        assert entry["actor"]


def test_audit_verify_endpoint(client, component_payload):
    client.post("/api/v1/components", json=component_payload)
    response = client.get("/api/v1/audit/verify")
    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is True
    assert body["records_checked"] >= 1


def test_audit_listing_is_paginated(client):
    response = client.get("/api/v1/audit", params={"page": 1, "page_size": 5})
    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) <= 5
    assert body["page"] == 1
    assert body["total"] >= len(body["items"])


def test_audit_stats_and_export(client):
    stats = client.get("/api/v1/audit/stats").json()
    assert stats["total_records"] >= 1
    assert len(stats["head_hash"]) == 64

    export = client.get("/api/v1/audit/export")
    assert export.status_code == 200
    assert "current_hash" in export.text
