"""Component CRUD, validation, service history and QR passport tests."""

from __future__ import annotations


def test_create_component_allocates_id_and_qr_token(client, component_payload):
    response = client.post("/api/v1/components", json=component_payload)
    assert response.status_code == 201, response.text

    body = response.json()
    assert body["component_id"].startswith("KE-MOT-")
    assert body["serial_number"]
    assert len(body["qr_token"]) >= 16
    assert body["current_status"] == "ACTIVE"
    assert body["component_age"] > 0
    assert body["is_safety_critical"] is False
    # run_initial_prediction defaults to true, so an assessment must exist.
    assert body["latest_prediction"]["recommendation"] in {
        "CONTINUE_USING",
        "COMPONENT_RECOVERY",
        "MATERIAL_RECOVERY",
        "DISPOSE",
    }
    assert body["health_score"] is not None


def test_get_component_by_id_serial_and_qr_token(client, created_component):
    for key in ("component_id", "serial_number", "qr_token"):
        response = client.get(f"/api/v1/components/{created_component[key]}")
        assert response.status_code == 200
        assert response.json()["component_id"] == created_component["component_id"]


def test_get_missing_component_returns_404(client):
    response = client.get("/api/v1/components/KE-DOES-NOT-EXIST")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_list_components_supports_search_filter_and_pagination(client, created_component):
    listing = client.get("/api/v1/components", params={"page": 1, "page_size": 5})
    assert listing.status_code == 200
    body = listing.json()
    assert body["total"] >= 1
    assert body["page"] == 1
    assert len(body["items"]) <= 5

    searched = client.get(
        "/api/v1/components", params={"search": created_component["component_id"]}
    )
    assert searched.json()["total"] == 1

    filtered = client.get("/api/v1/components", params={"component_type": ["Motor"]})
    assert filtered.json()["total"] >= 1

    empty = client.get("/api/v1/components", params={"component_type": ["Governor"]})
    assert empty.json()["total"] == 0


def test_update_component_persists_changes(client, created_component):
    response = client.put(
        f"/api/v1/components/{created_component['component_id']}",
        json={"vibration": 6.4, "current_status": "UNDER_INSPECTION", "notes": "Follow-up needed"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["vibration"] == 6.4
    assert body["current_status"] == "UNDER_INSPECTION"
    assert body["notes"] == "Follow-up needed"


def test_update_component_date_field_is_audit_safe(client, created_component):
    """A raw ``date`` in the audit trail's JSON snapshot is not serialisable -
    this must not reach that column, whatever the field's type."""
    response = client.put(
        f"/api/v1/components/{created_component['component_id']}",
        json={"last_service_date": "2026-07-14"},
    )
    assert response.status_code == 200
    assert response.json()["last_service_date"] == "2026-07-14"


def test_create_component_rejects_invalid_values(client, component_payload):
    invalid_type = {**component_payload, "component_type": "Rocket Engine"}
    assert client.post("/api/v1/components", json=invalid_type).status_code == 422

    negative_hours = {**component_payload, "operating_hours": -50}
    response = client.post("/api/v1/components", json=negative_hours)
    assert response.status_code == 422
    assert response.json()["error"] == "validation_error"

    negative_cycles = {**component_payload, "load_cycles": -1}
    assert client.post("/api/v1/components", json=negative_cycles).status_code == 422

    bad_inspection = {**component_payload, "inspection_score": 140}
    assert client.post("/api/v1/components", json=bad_inspection).status_code == 422

    future_install = {**component_payload, "installation_date": "2099-01-01"}
    assert client.post("/api/v1/components", json=future_install).status_code == 422


def test_service_event_updates_component_and_history(client, created_component):
    component_id = created_component["component_id"]
    before = client.get(f"/api/v1/components/{component_id}").json()

    response = client.post(
        f"/api/v1/components/{component_id}/service-events",
        json={
            "event_type": "INSPECTION",
            "event_date": "2026-06-18",
            "technician": "R. Karthik",
            "description": "Annual statutory inspection.",
            "operating_hours": 19850,
            "vibration": 4.1,
            "temperature": 55,
            "inspection_score": 78,
            "update_component": True,
        },
    )
    assert response.status_code == 201
    assert response.json()["event_type"] == "INSPECTION"

    after = client.get(f"/api/v1/components/{component_id}").json()
    assert after["operating_hours"] == 19850
    assert after["inspection_score"] == 78
    assert after["service_count"] == before["service_count"] + 1
    assert after["last_service_date"] == "2026-06-18"

    history = client.get(f"/api/v1/components/{component_id}/service-events").json()
    assert history["total"] >= 2  # INSTALLATION + INSPECTION
    assert history["items"][0]["event_type"] in {"INSPECTION", "INSTALLATION"}


def test_service_event_stores_variable_sensor_metadata(client, created_component):
    """sensor_metadata is a flat JSONB bag for readings the fixed columns
    don't have a place for - it must round-trip through create and history,
    and land in the audit snapshot the same event writes."""
    component_id = created_component["component_id"]

    response = client.post(
        f"/api/v1/components/{component_id}/service-events",
        json={
            "event_type": "INSPECTION",
            "event_date": "2026-06-18",
            "sensor_metadata": {"current_draw_amps": 4.2, "acoustic_emission_db": 61, "door_ok": True},
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["sensor_metadata"] == {
        "current_draw_amps": 4.2,
        "acoustic_emission_db": 61,
        "door_ok": True,
    }

    history = client.get(f"/api/v1/components/{component_id}/service-events").json()
    stored = next(item for item in history["items"] if item["event_type"] == "INSPECTION")
    assert stored["sensor_metadata"]["current_draw_amps"] == 4.2

    trail = client.get(f"/api/v1/audit/component/{component_id}").json()
    snapshot = next(
        entry["data_snapshot"]
        for entry in trail
        if entry["action"] == "SERVICE_EVENT" and entry["data_snapshot"]["service_event_id"] == stored["id"]
    )
    assert snapshot["readings"]["sensor_metadata"]["acoustic_emission_db"] == 61


def test_service_event_rejects_oversized_sensor_metadata(client, created_component):
    too_many_keys = {f"reading_{i}": i for i in range(25)}
    response = client.post(
        f"/api/v1/components/{created_component['component_id']}/service-events",
        json={"event_type": "INSPECTION", "sensor_metadata": too_many_keys},
    )
    assert response.status_code == 422


def test_service_event_rejects_future_dates(client, created_component):
    response = client.post(
        f"/api/v1/components/{created_component['component_id']}/service-events",
        json={"event_type": "MAINTENANCE", "event_date": "2099-01-01"},
    )
    assert response.status_code == 422


def test_removal_event_moves_component_to_removed(client, component_payload):
    created = client.post(
        "/api/v1/components", json={**component_payload, "component_type": "Door Operator"}
    ).json()
    client.post(
        f"/api/v1/components/{created['component_id']}/service-events",
        json={"event_type": "REMOVAL", "event_date": "2026-07-01"},
    )
    refreshed = client.get(f"/api/v1/components/{created['component_id']}").json()
    assert refreshed["current_status"] == "REMOVED"


def test_qr_code_endpoint_returns_png(client, created_component):
    response = client.get(f"/api/v1/passports/{created_component['component_id']}/qr")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content[:8] == b"\x89PNG\r\n\x1a\n"
    assert len(response.content) > 200


def test_qr_info_encodes_the_public_passport_url(client, created_component):
    component_id = created_component["component_id"]
    response = client.get(f"/api/v1/passports/{component_id}/qr/info")
    assert response.status_code == 200
    body = response.json()
    assert body["passport_url"].endswith(f"/passport/{component_id}")
    assert body["qr_image_url"] == f"/api/v1/passports/{component_id}/qr"


def test_passport_contains_the_full_lifecycle_record(client, created_component):
    response = client.get(f"/api/v1/passports/{created_component['component_id']}")
    assert response.status_code == 200
    body = response.json()

    assert body["component"]["component_id"] == created_component["component_id"]
    assert body["qr_data_uri"].startswith("data:image/png;base64,")
    assert isinstance(body["service_events"], list)
    assert len(body["predictions"]) >= 1
    assert len(body["audit_trail"]) >= 1
    assert body["impact"]["estimate_basis"] == "Prototype estimate"
    assert "synthetic" in body["data_notice"].lower()


def test_passport_resolve_handles_urls_and_ids(client, created_component):
    component_id = created_component["component_id"]

    resolved = client.get(
        "/api/v1/passports/lookup/resolve",
        params={"value": f"http://localhost:5173/passport/{component_id}"},
    ).json()
    assert resolved["found"] is True
    assert resolved["component_id"] == component_id

    missing = client.get(
        "/api/v1/passports/lookup/resolve", params={"value": "KE-NOPE-000000"}
    ).json()
    assert missing["found"] is False


def test_safety_critical_component_is_flagged_end_to_end(client, component_payload):
    rope = client.post(
        "/api/v1/components",
        json={**component_payload, "component_type": "Steel Rope", "material": "Steel"},
    ).json()

    assert rope["is_safety_critical"] is True
    assert rope["latest_prediction"]["safety_flag"] is True
    assert rope["latest_prediction"]["safety_message"] == "MANDATORY HUMAN INSPECTION"

    passport = client.get(f"/api/v1/passports/{rope['component_id']}").json()
    assert passport["safety_flag"] is True
    assert passport["safety_message"] == "MANDATORY HUMAN INSPECTION"


def test_component_csv_export(client, created_component):
    response = client.get("/api/v1/components/export")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "component_id" in response.text
    assert created_component["component_id"] in response.text


def test_delete_component_removes_it_but_keeps_the_audit_trail(client, component_payload):
    created = client.post(
        "/api/v1/components", json={**component_payload, "component_type": "Governor", "material": "Steel"}
    ).json()
    component_id = created["component_id"]

    deleted = client.delete(f"/api/v1/components/{component_id}")
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True
    assert client.get(f"/api/v1/components/{component_id}").status_code == 404

    trail = client.get(f"/api/v1/audit/component/{component_id}").json()
    actions = {entry["action"] for entry in trail}
    assert "DELETE" in actions
    assert "CREATE" in actions
    assert client.get("/api/v1/audit/verify").json()["valid"] is True
