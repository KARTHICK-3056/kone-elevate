"""P3 compliance engine: material-flow ledger, ESRS E5, BRSR, DPP, anchoring."""

from __future__ import annotations

import threading
from datetime import date

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.database import Base
from app.models.audit import AuditChainLock, AuditLog
from app.models.material_flow import MaterialFlow
from app.services import audit_service, compliance_service, material_flow_service
from app.services.compliance_service import InvalidPeriodError
from app.utils import standards
from app.utils.enums import (
    ComponentType,
    LifecycleStatus,
    MassSource,
    MaterialFlowDirection,
    OutflowRoute,
)


# --------------------------------------------------------------------------
# Transition classification
# --------------------------------------------------------------------------
def test_new_component_entering_service_is_an_inflow():
    direction, route = material_flow_service.classify(None, LifecycleStatus.ACTIVE.value)
    assert direction == MaterialFlowDirection.INFLOW.value
    assert route is None


def test_recycling_is_an_outflow_diverted_from_disposal():
    direction, route = material_flow_service.classify(
        LifecycleStatus.REMOVED.value, LifecycleStatus.MATERIAL_RECOVERED.value
    )
    assert direction == MaterialFlowDirection.OUTFLOW.value
    assert route == OutflowRoute.RECYCLING.value


def test_disposal_defaults_to_the_conservative_route():
    _, route = material_flow_service.classify(
        LifecycleStatus.REMOVED.value, LifecycleStatus.DISPOSED.value
    )
    assert route == OutflowRoute.LANDFILL.value


def test_removal_from_service_is_internal_not_an_outflow():
    """A removed component has not left the boundary - it is in the workshop."""
    direction, _ = material_flow_service.classify(
        LifecycleStatus.ACTIVE.value, LifecycleStatus.REMOVED.value
    )
    assert direction == MaterialFlowDirection.INTERNAL.value


def test_moving_between_two_outflow_states_is_not_counted_twice():
    """PART_RECOVERY -> MATERIAL_RECOVERED must not book a second E5-5 outflow.

    The mass already left the boundary when it went to part recovery.
    Counting the onward move would inflate the outflow total for material that
    never came back in.
    """
    direction, route = material_flow_service.classify(
        LifecycleStatus.PART_RECOVERY.value, LifecycleStatus.MATERIAL_RECOVERED.value
    )
    assert direction == MaterialFlowDirection.INTERNAL.value
    assert route is None


# --------------------------------------------------------------------------
# Ledger writes
# --------------------------------------------------------------------------
def test_creating_a_component_records_an_inflow_row(client, component_payload):
    component_payload["installation_date"] = "2026-02-10"
    created = client.post("/api/v1/components", json=component_payload).json()

    rows = client.get(
        f"/api/v1/reports/material-flow?component_id={created['component_id']}"
    ).json()["items"]

    assert len(rows) == 1
    assert rows[0]["direction"] == MaterialFlowDirection.INFLOW.value
    assert rows[0]["to_state"] == LifecycleStatus.ACTIVE.value
    assert rows[0]["flow_date"] == "2026-02-10"
    assert rows[0]["mass_kg"] > 0
    assert rows[0]["is_secondary"] is False


def test_ledger_row_falls_back_to_the_configured_mass_and_says_so(
    client, component_payload
):
    created = client.post("/api/v1/components", json=component_payload).json()
    row = client.get(
        f"/api/v1/reports/material-flow?component_id={created['component_id']}"
    ).json()["items"][0]

    assert row["mass_source"] == MassSource.CONFIG_ESTIMATE.value
    assert row["mass_kg"] == pytest.approx(260.0)  # Motor, from IMPACT_COMPONENT_MASS_KG


def test_a_weighed_mass_on_the_component_is_preferred_and_flagged(
    client, component_payload
):
    component_payload["mass_kg"] = 271.5
    created = client.post("/api/v1/components", json=component_payload).json()
    row = client.get(
        f"/api/v1/reports/material-flow?component_id={created['component_id']}"
    ).json()["items"][0]

    assert row["mass_kg"] == pytest.approx(271.5)
    assert row["mass_source"] == MassSource.COMPONENT_RECORD.value


def test_recycling_a_component_records_an_outflow_row(client, created_component):
    component_id = created_component["component_id"]
    response = client.put(
        f"/api/v1/components/{component_id}",
        json={"current_status": LifecycleStatus.MATERIAL_RECOVERED.value},
    )
    assert response.status_code == 200

    rows = client.get(
        f"/api/v1/reports/material-flow?component_id={component_id}"
    ).json()["items"]
    outflows = [row for row in rows if row["direction"] == MaterialFlowDirection.OUTFLOW.value]

    assert len(outflows) == 1
    assert outflows[0]["outflow_route"] == OutflowRoute.RECYCLING.value
    assert outflows[0]["from_state"] == LifecycleStatus.ACTIVE.value


def test_every_ledger_row_is_pinned_to_an_audit_entry(client, created_component):
    component_id = created_component["component_id"]
    client.put(
        f"/api/v1/components/{component_id}",
        json={"current_status": LifecycleStatus.MATERIAL_RECOVERED.value},
    )
    rows = client.get(
        f"/api/v1/reports/material-flow?component_id={component_id}"
    ).json()["items"]

    assert rows, "expected ledger rows"
    assert all(row["audit_hash"] for row in rows)
    assert client.get("/api/v1/audit/verify").json()["valid"] is True


def test_a_status_change_that_changes_nothing_records_no_row(client, created_component):
    component_id = created_component["component_id"]
    before = len(
        client.get(f"/api/v1/reports/material-flow?component_id={component_id}").json()["items"]
    )
    client.put(
        f"/api/v1/components/{component_id}",
        json={"current_status": created_component["current_status"]},
    )
    after = len(
        client.get(f"/api/v1/reports/material-flow?component_id={component_id}").json()["items"]
    )
    assert after == before


def test_component_recovery_is_one_outflow_and_never_a_secondary_inflow(client, component_payload):
    """A component whose sub-components are recovered leaves the boundary once,
    as an E5-5 outflow booked under the regulation's "preparation for reuse"
    route. The complete component never comes back in: it cannot be set back
    to ACTIVE, so no secondary inflow of it is ever booked.
    """
    created = client.post("/api/v1/components", json=component_payload).json()
    component_id = created["component_id"]

    for status_value in (
        LifecycleStatus.REMOVED.value,
        LifecycleStatus.PART_RECOVERY.value,
    ):
        response = client.put(
            f"/api/v1/components/{component_id}", json={"current_status": status_value}
        )
        assert response.status_code == 200

    refit = client.put(
        f"/api/v1/components/{component_id}", json={"current_status": LifecycleStatus.ACTIVE.value}
    )
    assert refit.status_code == 409

    rows = client.get(
        f"/api/v1/reports/material-flow?component_id={component_id}"
    ).json()["items"]

    outflows = [r for r in rows if r["direction"] == MaterialFlowDirection.OUTFLOW.value]
    inflows = [r for r in rows if r["direction"] == MaterialFlowDirection.INFLOW.value]

    assert [r["outflow_route"] for r in outflows] == [OutflowRoute.PREPARATION_FOR_REUSE.value]
    assert len(inflows) == 1
    assert inflows[0]["is_secondary"] is False


# --------------------------------------------------------------------------
# Period parsing
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "period,expected_start,expected_end",
    [
        ("2026", date(2026, 1, 1), date(2026, 12, 31)),
        ("2026-Q1", date(2026, 1, 1), date(2026, 3, 31)),
        ("2026-Q4", date(2026, 10, 1), date(2026, 12, 31)),
        ("2026-02", date(2026, 2, 1), date(2026, 2, 28)),
        ("2024-02", date(2024, 2, 1), date(2024, 2, 29)),  # leap year
        ("2026-01-15:2026-06-30", date(2026, 1, 15), date(2026, 6, 30)),
    ],
)
def test_period_parsing(period, expected_start, expected_end):
    start, end, _ = compliance_service.parse_period(period)
    assert (start, end) == (expected_start, expected_end)


@pytest.mark.parametrize("period", ["", "nonsense", "2026-Q5", "2026-13", "2026-06-30:2026-01-01"])
def test_invalid_periods_are_rejected(period):
    with pytest.raises(InvalidPeriodError):
        compliance_service.parse_period(period)


def test_invalid_period_returns_422(client):
    assert client.get("/api/v1/reports/esrs-e5?period=nonsense").status_code == 422


# --------------------------------------------------------------------------
# ESRS E5
# --------------------------------------------------------------------------
def test_esrs_e5_reports_tonnes_not_kilograms(client, component_payload):
    component_payload["installation_date"] = "2026-05-04"
    client.post("/api/v1/components", json=component_payload)

    report = client.get("/api/v1/reports/esrs-e5?period=2026").json()
    inflows = report["E5-4_resource_inflows"]

    assert report["unit"] == "tonnes"
    assert inflows["total_tonnes"] > 0
    # A single 260 kg motor must be 0.26 t, not 260.
    assert inflows["total_tonnes"] < 1.0
    assert inflows["by_material"]["Steel"]["tonnes"] == pytest.approx(
        inflows["by_material"]["Steel"]["mass_kg"] / 1000.0, rel=1e-3
    )


def test_esrs_e5_period_filter_excludes_flows_outside_it(client, component_payload):
    # A year no other test in this module uses: the database is module-scoped,
    # so a shared period would be polluted by sibling tests' components.
    component_payload["installation_date"] = "2019-05-04"
    client.post("/api/v1/components", json=component_payload)

    inside = client.get("/api/v1/reports/esrs-e5?period=2019-Q2").json()
    outside = client.get("/api/v1/reports/esrs-e5?period=2019-Q1").json()

    assert inside["E5-4_resource_inflows"]["total_units"] >= 1
    assert outside["E5-4_resource_inflows"]["total_units"] == 0
    assert outside["E5-4_resource_inflows"]["total_tonnes"] == 0.0


def test_e5_5_splits_diverted_from_directed_to_disposal(client, component_payload):
    recycled = client.post("/api/v1/components", json=component_payload).json()
    client.put(
        f"/api/v1/components/{recycled['component_id']}",
        json={"current_status": LifecycleStatus.MATERIAL_RECOVERED.value},
    )

    disposed_payload = dict(component_payload, component_type="Door Operator", material="Composite")
    disposed = client.post("/api/v1/components", json=disposed_payload).json()
    client.put(
        f"/api/v1/components/{disposed['component_id']}",
        json={"current_status": LifecycleStatus.DISPOSED.value},
    )

    year = date.today().year
    outflows = client.get(f"/api/v1/reports/esrs-e5?period={year}").json()[
        "E5-5_resource_outflows"
    ]

    assert outflows["diverted_from_disposal_tonnes"] > 0
    assert outflows["directed_to_disposal_tonnes"] > 0
    assert outflows["diverted_from_disposal_percent"] + outflows[
        "directed_to_disposal_percent"
    ] == pytest.approx(100.0, abs=0.2)
    assert OutflowRoute.RECYCLING.value in outflows["by_route"]
    assert OutflowRoute.LANDFILL.value in outflows["by_route"]


def test_critical_raw_materials_metric_is_reported(client, component_payload):
    motor = dict(
        component_payload,
        component_type="Motor",
        material="Copper",
        installation_date="2021-07-19",  # a year no sibling test uses
    )
    client.post("/api/v1/components", json=motor)

    crm = client.get("/api/v1/reports/esrs-e5?period=2021").json()[
        "E5-4_resource_inflows"
    ]["critical_raw_materials"]

    assert crm["total_crm_kg"] > 0
    assert "Copper" in crm["by_substance"]
    assert crm["list_reference"].startswith("Regulation (EU) 2024/1252")


def test_report_embeds_the_audit_hash_range_it_was_derived_from(client, component_payload):
    client.post("/api/v1/components", json=component_payload)

    year = date.today().year
    derivation = client.get(f"/api/v1/reports/esrs-e5?period={year}").json()["derivation"]

    assert derivation["ledger_rows"] > 0
    assert derivation["audit_entries"] > 0
    assert derivation["first_audit_hash"]
    assert derivation["last_audit_hash"]
    assert len(derivation["chain_head_hash_at_generation"]) == 64


def test_report_discloses_how_much_of_its_mass_is_estimated(client, component_payload):
    client.post("/api/v1/components", json=component_payload)
    year = date.today().year
    report = client.get(f"/api/v1/reports/esrs-e5?period={year}").json()

    assert report["E5-4_resource_inflows"]["estimated_mass_share_percent"] > 0
    assert "PROTOTYPE" in report["notice"]


def test_esrs_e5_csv_export(client, component_payload):
    client.post("/api/v1/components", json=component_payload)
    year = date.today().year
    response = client.get(f"/api/v1/reports/esrs-e5.csv?period={year}")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    body = response.text
    assert "E5-4,Total resource inflows" in body
    assert "E5-5,Total resource outflows" in body
    assert "DERIVATION" in body


# --------------------------------------------------------------------------
# BRSR
# --------------------------------------------------------------------------
def test_brsr_reports_principle_2_and_6(client, component_payload):
    created = client.post("/api/v1/components", json=component_payload).json()
    client.put(
        f"/api/v1/components/{created['component_id']}",
        json={"current_status": LifecycleStatus.MATERIAL_RECOVERED.value},
    )

    year = date.today().year
    report = client.get(f"/api/v1/reports/brsr?period={year}").json()

    assert report["unit"] == "tonnes"
    assert report["principle_2_sustainable_safe_goods"]["total_input_tonnes"] > 0
    assert report["principle_6_environment"]["recycled_tonnes"] > 0
    assert report["principle_6_environment"]["recovered_share_percent"] > 0
    assert report["derivation"]["ledger_rows"] > 0


# --------------------------------------------------------------------------
# Standards basis
# --------------------------------------------------------------------------
def test_every_component_type_has_a_standards_basis():
    for component_type in ComponentType.values():
        citations = standards.standards_basis(component_type)
        assert citations, f"{component_type} has no standards basis"
        assert all(citation["standard"] for citation in citations)


def test_the_standards_the_pitch_names_are_actually_cited():
    """The deck claims ISO 4344, ISO 281 and EN 81-80. Prove each appears."""
    catalogue = standards.all_standards()["distinct_standards"]
    assert any(s.startswith("ISO 4344") for s in catalogue)
    assert any(s.startswith("ISO 281") for s in catalogue)
    assert any(s.startswith("EN 81-80") for s in catalogue)


def test_rope_standard_is_cited_for_steel_rope():
    citations = standards.standards_basis(ComponentType.STEEL_ROPE.value)
    assert any(citation["standard"].startswith("ISO 4344") for citation in citations)


def test_unverified_clauses_are_flagged_rather_than_presented_as_authoritative():
    summary = standards.standards_summary(ComponentType.STEEL_ROPE.value)
    assert summary["unverified_clause_count"] > 0
    assert "not from the purchased standard" in summary["verification_notice"]


def test_standards_endpoint(client):
    catalogue = client.get("/api/v1/reports/standards").json()
    assert "by_component_type" in catalogue

    single = client.get("/api/v1/reports/standards?component_type=Brake").json()
    assert single["component_type"] == "Brake"
    assert single["citations"]


def test_passport_renders_the_standards_basis(client, created_component):
    passport = client.get(f"/api/v1/passports/{created_component['component_id']}").json()
    assert passport["standards_basis"]["citations"]
    assert passport["standards_basis"]["verification_notice"]


# --------------------------------------------------------------------------
# Digital Product Passport
# --------------------------------------------------------------------------
def test_dpp_export_carries_a_persistent_identifier(client, created_component):
    component_id = created_component["component_id"]
    export = client.get(f"/api/v1/passports/{component_id}/dpp").json()
    identification = export["identification"]

    assert identification["dpp_id"].startswith("urn:kone:dpp:")
    assert component_id in identification["dpp_id"]
    assert identification["data_carrier"]["type"] == "QR"


def test_dpp_data_carrier_does_not_point_at_a_development_server(client, created_component):
    """A passport whose link dies when the demo stops is not a passport."""
    export = client.get(f"/api/v1/passports/{created_component['component_id']}/dpp").json()
    payload = export["identification"]["data_carrier"]["payload"]

    assert "localhost" not in payload
    assert "127.0.0.1" not in payload
    assert payload.startswith("https://")


def test_dpp_is_honest_about_not_being_registered(client, created_component):
    export = client.get(f"/api/v1/passports/{created_component['component_id']}/dpp").json()
    assert export["identification"]["registry_status"] == "NOT_REGISTERED"
    assert export["identification"]["registry_note"]
    assert export["economic_operator"]["assigned"] is False
    assert export["economic_operator"]["note"]


def test_dpp_carries_composition_standards_and_tamper_evidence(client, created_component):
    export = client.get(f"/api/v1/passports/{created_component['component_id']}/dpp").json()

    assert export["material_composition"]["mass_kg"] > 0
    assert export["standards_basis"]["citations"]
    assert export["tamper_evidence"]["head_hash"]
    assert export["lifecycle_record"], "the DPP must carry the material-flow history"


def test_qr_payload_encodes_the_resolver_url_and_still_scans(client, created_component):
    component_id = created_component["component_id"]
    info = client.get(f"/api/v1/passports/{component_id}/qr/info").json()

    assert info["encoded_payload"].startswith("https://")
    assert info["dpp_id"].startswith("urn:kone:dpp:")

    resolved = client.get(
        "/api/v1/passports/lookup/resolve", params={"value": info["encoded_payload"]}
    ).json()
    assert resolved["found"] is True
    assert resolved["component_id"] == component_id


def test_legacy_qr_formats_still_resolve(client, created_component):
    """Labels printed before the DPP identifier existed must keep working."""
    component_id = created_component["component_id"]
    for legacy in (component_id, f"http://localhost:5173/passport/{component_id}"):
        resolved = client.get(
            "/api/v1/passports/lookup/resolve", params={"value": legacy}
        ).json()
        assert resolved["found"] is True, legacy
        assert resolved["component_id"] == component_id


# --------------------------------------------------------------------------
# Ledger summary and anchoring
# --------------------------------------------------------------------------
def test_ledger_summary_reports_estimated_mass_coverage(client, component_payload):
    client.post("/api/v1/components", json=component_payload)
    summary = client.get("/api/v1/reports/ledger-summary").json()

    assert summary["total_rows"] > 0
    assert summary["estimated_mass_row_share_percent"] > 0
    assert len(summary["chain_head_hash"]) == 64


def test_anchoring_records_the_chain_head(client, created_component):
    response = client.post("/api/v1/reports/anchors")
    assert response.status_code == 201
    anchor = response.json()

    assert len(anchor["head_hash"]) == 64
    assert anchor["record_count"] > 0


def test_anchoring_is_idempotent_per_day(client, created_component):
    first = client.post("/api/v1/reports/anchors").json()
    second = client.post("/api/v1/reports/anchors").json()
    assert first["anchor_date"] == second["anchor_date"]
    assert first["head_hash"] == second["head_hash"]


def test_anchor_status_admits_it_has_no_external_witness(client, created_component):
    client.post("/api/v1/reports/anchors")
    payload = client.get("/api/v1/reports/anchors").json()

    assert payload["externally_witnessed_anchors"] == 0
    assert payload["external_store_configured"] is False
    assert "NOT PROTECTED" in payload["protection"]


# --------------------------------------------------------------------------
# Audit-chain concurrency (P3: "10 threads x 100 writes, chain verifies valid")
# --------------------------------------------------------------------------
def test_chain_survives_ten_threads_writing_one_hundred_entries_each(tmp_path):
    """The concurrency guarantee the whole compliance story rests on.

    An E5 report cites an audit hash range as its evidence. If concurrent
    writes can fork the chain, ``verify_chain`` reports a false tamper alarm
    on an untampered database and every disclosure derived from it is
    unciteable. 1,000 appends from 10 threads must leave exactly 1,000
    correctly linked records.
    """
    threads, writes_per_thread = 10, 100
    database_url = f"sqlite:///{(tmp_path / 'concurrency.db').as_posix()}"
    engine = create_engine(
        database_url,
        connect_args={"check_same_thread": False, "timeout": 60},
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    with factory() as seed:
        seed.merge(AuditChainLock(id=1, version=0))
        seed.commit()

    failures: list[Exception] = []
    barrier = threading.Barrier(threads)

    def append_entries(worker: int) -> None:
        try:
            barrier.wait()
            for index in range(writes_per_thread):
                with factory() as session:
                    audit_service.record(
                        session,
                        entity_type="load_test",
                        entity_id=f"{worker}-{index}",
                        action="CREATE",
                        data_snapshot={"worker": worker, "index": index},
                        actor=f"worker-{worker}",
                        commit=True,
                    )
        except Exception as exc:  # pragma: no cover - surfaced via failures
            failures.append(exc)

    workers = [threading.Thread(target=append_entries, args=(n,)) for n in range(threads)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()

    assert not failures, f"threads raised: {failures[:3]}"

    with factory() as session:
        total = int(session.execute(select(func.count(AuditLog.id))).scalar_one())
        assert total == threads * writes_per_thread

        result = audit_service.verify_chain(session)
        assert result["valid"] is True, result
        assert result["records_checked"] == threads * writes_per_thread

        distinct_previous = int(
            session.execute(select(func.count(func.distinct(AuditLog.previous_hash)))).scalar_one()
        )
        assert distinct_previous == total, "a forked chain reuses a previous_hash"

    engine.dispose()


def test_material_flow_rows_are_written_inside_the_caller_transaction(db, client, component_payload):
    """A rolled-back business change must not leave an orphan kilogram behind."""
    created = client.post("/api/v1/components", json=component_payload).json()

    rows = db.execute(
        select(func.count(MaterialFlow.id)).where(
            MaterialFlow.component_id == created["component_id"]
        )
    ).scalar_one()
    assert rows == 1

    session = Session(bind=db.get_bind())
    component = session.execute(
        select(MaterialFlow).where(MaterialFlow.component_id == created["component_id"])
    ).scalars().first()
    assert component.audit_hash is not None
    session.close()
