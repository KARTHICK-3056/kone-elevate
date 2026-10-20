"""Health, metadata and OpenAPI documentation tests."""

from __future__ import annotations


def test_index_lists_documentation_urls(client):
    response = client.get("/")
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "KONE ELEVATE"
    assert body["docs"] == "/docs"
    assert "synthetic" in body["data_notice"].lower()


def test_health_reports_database_and_model(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] in {"ok", "degraded"}
    assert body["database"]["connected"] is True
    assert "model_available" in body["model"]


def test_readiness_probe(client):
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 200
    assert response.json()["ready"] is True


def test_enum_metadata_exposes_safety_vocabulary(client):
    response = client.get("/api/v1/meta/enums")
    assert response.status_code == 200
    body = response.json()

    assert "Motor" in body["component_types"]
    assert body["recommendations"] == [
        "CONTINUE_USING",
        "COMPONENT_RECOVERY",
        "MATERIAL_RECOVERY",
        "DISPOSE",
        "DEFER_TO_INSPECTION",
    ]
    assert set(body["safety_critical_types"]) == {"Steel Rope", "Brake", "Governor"}
    assert body["safety_gate_message"] == "MANDATORY HUMAN INSPECTION"


def test_openapi_schema_is_served(client):
    response = client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    for required in (
        "/api/v1/components",
        "/api/v1/predict",
        "/api/v1/audit/verify",
        "/api/v1/dashboard/summary",
    ):
        assert required in paths


def test_swagger_docs_available(client):
    assert client.get("/docs").status_code == 200
    assert client.get("/redoc").status_code == 200


def test_sensor_hook_is_explicitly_not_implemented(client):
    """The future IoT endpoint must never pretend to accept live telemetry."""
    response = client.post("/api/v1/sensors/KE-MOT-000001", json={"vibration": 2.0})
    assert response.status_code == 501
    assert response.json()["error"] == "not_implemented"
