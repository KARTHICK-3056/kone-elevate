"""Security response headers and login/signup rate limiting (P4)."""

from __future__ import annotations

from app.core import rate_limit


def test_security_headers_present_on_a_json_response(anonymous_client):
    response = anonymous_client.get("/api/v1/health")
    assert response.headers.get("X-Content-Type-Options") == "nosniff"
    assert response.headers.get("X-Frame-Options") == "DENY"
    assert response.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
    assert "Content-Security-Policy" in response.headers
    assert "Strict-Transport-Security" in response.headers


def test_docs_route_has_no_content_security_policy(anonymous_client):
    response = anonymous_client.get("/docs")
    assert response.status_code == 200
    assert "Content-Security-Policy" not in response.headers
    # The rest still apply even on the docs route.
    assert response.headers.get("X-Frame-Options") == "DENY"


def test_login_is_rate_limited(anonymous_client, monkeypatch):
    monkeypatch.setattr(rate_limit.settings, "RATE_LIMIT_LOGIN_MAX", 3)
    rate_limit._windows.clear()

    for _ in range(3):
        response = anonymous_client.post(
            "/api/v1/auth/login",
            data={"username": "nobody@pytest.local", "password": "wrong-password-value"},
        )
        assert response.status_code == 401

    limited = anonymous_client.post(
        "/api/v1/auth/login",
        data={"username": "nobody@pytest.local", "password": "wrong-password-value"},
    )
    assert limited.status_code == 429
    assert "Retry-After" in limited.headers
    rate_limit._windows.clear()


def test_signup_is_rate_limited(anonymous_client, monkeypatch):
    monkeypatch.setattr(rate_limit.settings, "RATE_LIMIT_SIGNUP_MAX", 2)
    rate_limit._windows.clear()

    for index in range(2):
        response = anonymous_client.post(
            "/api/v1/auth/signup",
            json={
                "email": f"ratelimit{index}@pytest.local",
                "display_name": "Rate Limited",
                "password": "a-long-enough-password",
            },
        )
        assert response.status_code == 202

    limited = anonymous_client.post(
        "/api/v1/auth/signup",
        json={
            "email": "ratelimit-overflow@pytest.local",
            "display_name": "Rate Limited",
            "password": "a-long-enough-password",
        },
    )
    assert limited.status_code == 429
    rate_limit._windows.clear()
