"""Authentication, roles, and the closing of two identity-spoofing holes.

Before this layer existed, the audit chain was cryptographically sound and
evidentially worthless: it proved that an *unauthenticated claim* had not
been edited afterwards. The ``X-Actor`` header let a caller name themselves;
it is tested here as closed, because "we removed it" is a claim and a
failing-without-the-fix test is evidence. (The other path, an ``actor``
field in the Recovery Exchange match-decision body, went with the exchange.)
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.core.security import create_access_token
from app.models.audit import AuditLog
from app.services import auth_service
from app.utils.enums import Role

from .conftest import TEST_PASSWORD, _ensure_user

LOGIN_URL = "/api/v1/auth/login"


def _login(client, email: str, password: str = TEST_PASSWORD):
    """Sign in through the real endpoint, as a browser would."""
    return client.post(LOGIN_URL, data={"username": email, "password": password})


# --------------------------------------------------------------------------
# Signing in
# --------------------------------------------------------------------------
def test_login_returns_a_token_and_the_account(anonymous_client, session_factory):
    email = _ensure_user(session_factory, Role.TECHNICIAN.value)
    response = _login(anonymous_client, email)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["user"]["email"] == email
    assert body["user"]["role"] == Role.TECHNICIAN.value
    assert "password" not in body["user"]
    assert "password_hash" not in body["user"]


def test_login_rejects_a_wrong_password(anonymous_client, session_factory):
    email = _ensure_user(session_factory, Role.TECHNICIAN.value)
    assert _login(anonymous_client, email, "not-the-password").status_code == 401


def test_login_rejects_an_unknown_account(anonymous_client):
    assert _login(anonymous_client, "nobody@pytest.local").status_code == 401


def test_login_failures_do_not_reveal_whether_an_account_exists(
    anonymous_client, session_factory
):
    """Wrong password and unknown email must be indistinguishable."""
    email = _ensure_user(session_factory, Role.TECHNICIAN.value)
    known = _login(anonymous_client, email, "wrong-password-entirely")
    unknown = _login(anonymous_client, "ghost@pytest.local", "wrong-password-entirely")

    assert known.status_code == unknown.status_code == 401
    assert known.json()["detail"] == unknown.json()["detail"]


def test_login_rejects_a_deactivated_account(anonymous_client, session_factory, db):
    user = auth_service.create_user(
        db,
        email="deactivated@pytest.local",
        password=TEST_PASSWORD,
        display_name="Deactivated",
        role=Role.TECHNICIAN.value,
    )
    user.is_active = False
    db.commit()

    assert _login(anonymous_client, "deactivated@pytest.local").status_code == 401


def test_email_matching_is_case_insensitive(anonymous_client, session_factory):
    email = _ensure_user(session_factory, Role.TECHNICIAN.value)
    assert _login(anonymous_client, email.upper()).status_code == 200


def test_me_returns_the_signed_in_account(client_as):
    signed_in = client_as(Role.SUSTAINABILITY_CONTROLLER)
    response = signed_in.get("/api/v1/auth/me")

    assert response.status_code == 200
    assert response.json()["role"] == Role.SUSTAINABILITY_CONTROLLER.value


# --------------------------------------------------------------------------
# Protected endpoints reject anonymous and invalid callers
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/api/v1/components"),
        ("get", "/api/v1/dashboard/summary"),
        ("get", "/api/v1/audit/verify"),
        ("get", "/api/v1/reports/ledger-summary"),
        ("get", "/api/v1/auth/me"),
    ],
)
def test_protected_endpoints_require_a_token(anonymous_client, method, path):
    assert getattr(anonymous_client, method)(path).status_code == 401


def test_a_forged_token_is_rejected(anonymous_client):
    anonymous_client.headers.update({"Authorization": "Bearer not.a.real.token"})
    assert anonymous_client.get("/api/v1/components").status_code == 401


def test_a_token_signed_with_the_wrong_key_is_rejected(anonymous_client):
    """A token whose signature does not verify must not be trusted."""
    forged = create_access_token(subject="attacker@pytest.local", role=Role.SUPERVISOR.value)
    body, _signature = forged.split(".")
    anonymous_client.headers.update({"Authorization": f"Bearer {body}.deadbeef"})
    assert anonymous_client.get("/api/v1/components").status_code == 401


def test_an_expired_token_is_rejected(anonymous_client, session_factory):
    email = _ensure_user(session_factory, Role.SUPERVISOR.value)
    expired = create_access_token(subject=email, role=Role.SUPERVISOR.value, expires_minutes=-1)
    anonymous_client.headers.update({"Authorization": f"Bearer {expired}"})
    assert anonymous_client.get("/api/v1/components").status_code == 401


def test_a_validly_signed_token_for_a_nonexistent_account_is_rejected(anonymous_client):
    """Signature validity is not identity. The subject must still exist."""
    orphan = create_access_token(subject="never-provisioned@pytest.local", role=Role.SUPERVISOR.value)
    anonymous_client.headers.update({"Authorization": f"Bearer {orphan}"})
    assert anonymous_client.get("/api/v1/components").status_code == 401


def test_a_token_for_a_deactivated_account_stops_working(
    anonymous_client, session_factory, db
):
    user = auth_service.create_user(
        db,
        email="revoked@pytest.local",
        password=TEST_PASSWORD,
        display_name="Revoked",
        role=Role.SUPERVISOR.value,
    )
    token = create_access_token(subject=user.email, role=user.role)
    anonymous_client.headers.update({"Authorization": f"Bearer {token}"})
    assert anonymous_client.get("/api/v1/components").status_code == 200

    user.is_active = False
    db.commit()
    assert anonymous_client.get("/api/v1/components").status_code == 401


# --------------------------------------------------------------------------
# The public QR path stays public
# --------------------------------------------------------------------------
def test_the_passport_is_readable_without_signing_in(
    anonymous_client, client, component_payload
):
    """A technician scanning a label in a basement has no login. By design."""
    created = client.post("/api/v1/components", json=component_payload).json()
    component_id = created["component_id"]

    anonymous_client.headers.pop("Authorization", None)
    for path in (
        f"/api/v1/passports/{component_id}",
        f"/api/v1/passports/{component_id}/qr",
        f"/api/v1/passports/{component_id}/qr/info",
        f"/api/v1/passports/{component_id}/dpp",
        "/api/v1/health",
    ):
        assert anonymous_client.get(path).status_code == 200, path


# --------------------------------------------------------------------------
# Roles
# --------------------------------------------------------------------------
def test_a_read_only_auditor_can_read_everything(client_as):
    auditor = client_as(Role.READ_ONLY_AUDITOR)
    for path in (
        "/api/v1/components",
        "/api/v1/dashboard/summary",
        "/api/v1/audit/verify",
        "/api/v1/reports/ledger-summary",
    ):
        assert auditor.get(path).status_code == 200, path


def test_a_read_only_auditor_cannot_change_anything(client_as, component_payload):
    auditor = client_as(Role.READ_ONLY_AUDITOR)
    response = auditor.post("/api/v1/components", json=component_payload)

    assert response.status_code == 403
    assert "read-only" in response.json()["detail"].lower()


def test_a_read_only_auditor_cannot_run_an_assessment(client, client_as, component_payload):
    created = client.post("/api/v1/components", json=component_payload).json()
    auditor = client_as(Role.READ_ONLY_AUDITOR)

    assert auditor.post(f"/api/v1/components/{created['component_id']}/predict").status_code == 403


def test_anchoring_the_chain_is_restricted_to_named_roles(client_as, client, component_payload):
    client.post("/api/v1/components", json=component_payload)

    assert client_as(Role.TECHNICIAN).post("/api/v1/reports/anchors").status_code == 403
    assert client_as(Role.SUSTAINABILITY_CONTROLLER).post("/api/v1/reports/anchors").status_code in (
        201,
        409,
    )


def test_provisioning_an_account_requires_a_supervisor(client_as):
    payload = {
        "email": "newcomer@pytest.local",
        "display_name": "Newcomer",
        "password": "a-long-enough-password",
        "role": Role.TECHNICIAN.value,
        "country": "India",
    }
    assert client_as(Role.TECHNICIAN).post("/api/v1/auth/users", json=payload).status_code == 403

    response = client_as(Role.SUPERVISOR).post("/api/v1/auth/users", json=payload)
    assert response.status_code == 201, response.text
    assert response.json()["role"] == Role.TECHNICIAN.value


def test_a_provisioned_account_can_then_sign_in(client_as, anonymous_client):
    payload = {
        "email": "onboarded@pytest.local",
        "display_name": "Onboarded",
        "password": "another-long-password",
        "role": Role.RECOVERY_PLANNER.value,
        "country": "India",
    }
    assert client_as(Role.SUPERVISOR).post("/api/v1/auth/users", json=payload).status_code == 201

    anonymous_client.headers.pop("Authorization", None)
    response = _login(anonymous_client, "onboarded@pytest.local", "another-long-password")
    assert response.status_code == 200
    assert response.json()["user"]["role"] == Role.RECOVERY_PLANNER.value


def test_a_duplicate_email_is_rejected(client_as, session_factory):
    existing = _ensure_user(session_factory, Role.TECHNICIAN.value)
    response = client_as(Role.SUPERVISOR).post(
        "/api/v1/auth/users",
        json={
            "email": existing,
            "display_name": "Impostor",
            "password": "a-long-enough-password",
            "role": Role.SUPERVISOR.value,
            "country": "India",
        },
    )
    assert response.status_code == 409


def test_a_short_password_is_rejected(client_as):
    response = client_as(Role.SUPERVISOR).post(
        "/api/v1/auth/users",
        json={
            "email": "weak@pytest.local",
            "display_name": "Weak",
            "password": "short",
            "role": Role.TECHNICIAN.value,
        },
    )
    assert response.status_code == 422


def test_an_unknown_role_cannot_be_assigned(client_as):
    response = client_as(Role.SUPERVISOR).post(
        "/api/v1/auth/users",
        json={
            "email": "sneaky@pytest.local",
            "display_name": "Sneaky",
            "password": "a-long-enough-password",
            "role": "root",
        },
    )
    assert response.status_code == 422


# --------------------------------------------------------------------------
# The two spoofing holes, proven closed
# --------------------------------------------------------------------------
def test_a_forged_x_actor_header_is_ignored(client, db, component_payload, session_factory):
    """The header that used to name the actor now does nothing.

    This is the headline fix: previously ``X-Actor`` *was* the identity, so
    the audit chain recorded whatever the caller typed.
    """
    supervisor_email = _ensure_user(session_factory, Role.SUPERVISOR.value)

    response = client.post(
        "/api/v1/components",
        json=component_payload,
        headers={"X-Actor": "ceo@kone.com"},
    )
    assert response.status_code == 201
    component_id = response.json()["component_id"]

    entry = db.execute(
        select(AuditLog)
        .where(AuditLog.entity_id == component_id)
        .where(AuditLog.action == "CREATE")
    ).scalars().first()

    assert entry is not None
    assert entry.actor == supervisor_email
    assert entry.actor != "ceo@kone.com"


def test_every_audit_entry_names_a_real_account(client, db, component_payload):
    """No entry written through the API may carry an unverifiable actor."""
    client.post("/api/v1/components", json=component_payload)

    actors = {
        row for row in db.execute(select(AuditLog.actor)).scalars().all() if row
    }
    api_written = {actor for actor in actors if "@pytest.local" in actor}

    assert api_written, "expected at least one API-written audit entry"
    for actor in api_written:
        assert auth_service.get_by_email(db, actor) is not None, actor


# --------------------------------------------------------------------------
# Password storage
# --------------------------------------------------------------------------
def test_passwords_are_never_stored_in_plain_text(db, session_factory):
    email = _ensure_user(session_factory, Role.TECHNICIAN.value)
    user = auth_service.get_by_email(db, email)

    assert TEST_PASSWORD not in user.password_hash
    assert user.password_hash.startswith("pbkdf2$")


def test_the_shipped_work_factor_is_high_enough():
    """The suite runs at a token work factor; the shipped default must not.

    Asserted against the field's declared default rather than the live
    settings object, because this suite overrides ``PBKDF2_ROUNDS`` via the
    environment - and rather than by timing, which would be flaky on a loaded
    machine. OWASP's 2023 guidance for PBKDF2-HMAC-SHA256 is 600,000;
    210,000 is the older NIST-era floor and the minimum this project ships.
    """
    from app.core.config import Settings

    assert Settings.model_fields["PBKDF2_ROUNDS"].default >= 210_000


def test_raising_the_work_factor_does_not_invalidate_existing_passwords():
    """Each hash records the rounds it was made with, so it stays verifiable."""
    from app.core.security import hash_password, verify_password

    weak = hash_password("portable-password", rounds=1_000)
    strong = hash_password("portable-password", rounds=50_000)

    assert weak.split("$")[1] == "1000"
    assert strong.split("$")[1] == "50000"
    assert verify_password("portable-password", weak) is True
    assert verify_password("portable-password", strong) is True
    assert verify_password("wrong", weak) is False
