"""Self-service signup and emailed one-time code verification.

The security properties worth testing here are not "does the happy path
work" - they are the ones that stop signup becoming a way in: a caller
cannot choose their own role, an unverified account cannot sign in, and a
six-digit code cannot be brute-forced.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models.verification import EmailVerification
from app.services import auth_service, signup_service
from app.utils.enums import Role
from app.utils.helpers import utcnow

SIGNUP_URL = "/api/v1/auth/signup"
VERIFY_URL = "/api/v1/auth/signup/verify"
RESEND_URL = "/api/v1/auth/signup/resend"
LOGIN_URL = "/api/v1/auth/login"

PASSWORD = "a-long-enough-password"


def _signup(client, email: str, name: str = "New Starter"):
    return client.post(
        SIGNUP_URL, json={"email": email, "display_name": name, "password": PASSWORD}
    )


def _code_for(db, email: str) -> str:
    """Read the outstanding challenge and brute-force its hash.

    The service only ever stores a hash, so a test cannot simply read the
    code back - which is the point. Six digits is small enough to search
    here, and that is exactly why the attempt cap below matters.
    """
    user = auth_service.get_by_email(db, email)
    challenge = db.execute(
        select(EmailVerification)
        .where(EmailVerification.user_id == user.id)
        .where(EmailVerification.consumed_at.is_(None))
        .order_by(EmailVerification.id.desc())
        .limit(1)
    ).scalar_one()

    from app.core.security import sha256_hex

    for candidate in range(1_000_000):
        code = f"{candidate:06d}"
        if sha256_hex(code) == challenge.code_hash:
            return code
    raise AssertionError("no code matched the stored hash")


# --------------------------------------------------------------------------
# The happy path
# --------------------------------------------------------------------------
def test_signup_creates_an_unverified_account_and_sends_a_code(anonymous_client, db):
    response = _signup(anonymous_client, "newstarter@pytest.local")

    assert response.status_code == 202, response.text
    body = response.json()
    assert body["verification_required"] is True
    assert body["code_expires_in_minutes"] == settings.OTP_TTL_MINUTES

    user = auth_service.get_by_email(db, "newstarter@pytest.local")
    assert user is not None
    assert user.email_verified is False


def test_verifying_the_code_activates_the_account_and_signs_the_user_in(
    anonymous_client, db
):
    email = "verifyme@pytest.local"
    _signup(anonymous_client, email)
    code = _code_for(db, email)

    response = anonymous_client.post(VERIFY_URL, json={"email": email, "code": code})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["access_token"]
    assert body["user"]["email_verified"] is True

    db.expire_all()
    assert auth_service.get_by_email(db, email).email_verified is True


def test_a_verified_account_can_then_sign_in_normally(anonymous_client, db):
    email = "cansignin@pytest.local"
    _signup(anonymous_client, email)
    anonymous_client.post(VERIFY_URL, json={"email": email, "code": _code_for(db, email)})

    response = anonymous_client.post(
        LOGIN_URL, data={"username": email, "password": PASSWORD}
    )
    assert response.status_code == 200, response.text


def test_a_code_is_accepted_with_spaces_or_dashes(anonymous_client, db):
    email = "messycode@pytest.local"
    _signup(anonymous_client, email)
    code = _code_for(db, email)
    spaced = f"{code[:3]} - {code[3:]}"

    assert anonymous_client.post(
        VERIFY_URL, json={"email": email, "code": spaced}
    ).status_code == 200


# --------------------------------------------------------------------------
# The rule that makes self-signup safe
# --------------------------------------------------------------------------
def test_a_self_registered_account_gets_the_lowest_privilege_role(anonymous_client, db):
    email = "roleless@pytest.local"
    response = _signup(anonymous_client, email)

    assert response.json()["role"] == settings.SIGNUP_DEFAULT_ROLE
    assert settings.SIGNUP_DEFAULT_ROLE == Role.TECHNICIAN.value
    assert auth_service.get_by_email(db, email).role == Role.TECHNICIAN.value


def test_a_caller_cannot_choose_their_own_role(anonymous_client, db):
    """The whole reason signup was withheld until now.

    Even asking for a role explicitly must not grant it - the field does not
    exist, and a request carrying one is ignored rather than honoured.
    """
    email = "ambitious@pytest.local"
    response = anonymous_client.post(
        SIGNUP_URL,
        json={
            "email": email,
            "display_name": "Ambitious",
            "password": PASSWORD,
            "role": Role.SUPERVISOR.value,
            "is_active": True,
            "email_verified": True,
        },
    )

    assert response.status_code == 202, response.text
    user = auth_service.get_by_email(db, email)
    assert user.role == Role.TECHNICIAN.value
    assert user.email_verified is False


def test_a_new_signup_cannot_reach_a_supervisor_only_endpoint(anonymous_client, db):
    email = "notasupervisor@pytest.local"
    _signup(anonymous_client, email)
    token = anonymous_client.post(
        VERIFY_URL, json={"email": email, "code": _code_for(db, email)}
    ).json()["access_token"]

    anonymous_client.headers.update({"Authorization": f"Bearer {token}"})
    assert anonymous_client.get("/api/v1/auth/users").status_code == 403


# --------------------------------------------------------------------------
# An unverified account is not an account
# --------------------------------------------------------------------------
def test_an_unverified_account_cannot_sign_in(anonymous_client):
    email = "unverified@pytest.local"
    _signup(anonymous_client, email)

    response = anonymous_client.post(
        LOGIN_URL, data={"username": email, "password": PASSWORD}
    )
    assert response.status_code == 403
    assert "not been verified" in response.json()["detail"]


def test_an_unverified_account_with_a_wrong_password_still_says_nothing(anonymous_client):
    """The unverified hint must only appear once the password is correct."""
    email = "unverified2@pytest.local"
    _signup(anonymous_client, email)

    response = anonymous_client.post(
        LOGIN_URL, data={"username": email, "password": "completely-wrong"}
    )
    assert response.status_code == 401
    assert "Incorrect email or password" in response.json()["detail"]


# --------------------------------------------------------------------------
# Code handling
# --------------------------------------------------------------------------
def test_only_a_hash_of_the_code_is_stored(anonymous_client, db):
    email = "hashed@pytest.local"
    _signup(anonymous_client, email)
    code = _code_for(db, email)

    user = auth_service.get_by_email(db, email)
    challenge = db.execute(
        select(EmailVerification).where(EmailVerification.user_id == user.id)
    ).scalars().first()

    assert challenge.code_hash != code
    assert len(challenge.code_hash) == 64


def test_a_wrong_code_is_rejected_and_counts_against_the_limit(anonymous_client, db):
    email = "wrongcode@pytest.local"
    _signup(anonymous_client, email)

    response = anonymous_client.post(VERIFY_URL, json={"email": email, "code": "000000"})
    assert response.status_code == 400

    user = auth_service.get_by_email(db, email)
    db.expire_all()
    challenge = db.execute(
        select(EmailVerification)
        .where(EmailVerification.user_id == user.id)
        .order_by(EmailVerification.id.desc())
    ).scalars().first()
    assert challenge.attempts >= 1


def test_a_six_digit_code_cannot_be_brute_forced(anonymous_client, db):
    """Without an attempt cap, a million guesses is minutes of scripting."""
    email = "bruteforce@pytest.local"
    _signup(anonymous_client, email)
    real_code = _code_for(db, email)

    wrong = "000000" if real_code != "000000" else "111111"
    for _ in range(settings.OTP_MAX_ATTEMPTS):
        anonymous_client.post(VERIFY_URL, json={"email": email, "code": wrong})

    # Even the correct code no longer works: the challenge is burned.
    response = anonymous_client.post(VERIFY_URL, json={"email": email, "code": real_code})
    assert response.status_code == 400
    assert "no longer valid" in response.json()["detail"].lower()
    assert auth_service.get_by_email(db, email).email_verified is False


def test_an_expired_code_is_rejected(anonymous_client, db):
    email = "expired@pytest.local"
    _signup(anonymous_client, email)
    code = _code_for(db, email)

    user = auth_service.get_by_email(db, email)
    challenge = db.execute(
        select(EmailVerification)
        .where(EmailVerification.user_id == user.id)
        .where(EmailVerification.consumed_at.is_(None))
        .order_by(EmailVerification.id.desc())
    ).scalars().first()
    challenge.expires_at = utcnow() - timedelta(seconds=1)
    db.commit()

    response = anonymous_client.post(VERIFY_URL, json={"email": email, "code": code})
    assert response.status_code == 400
    assert "expired" in response.json()["detail"].lower()


def test_a_code_cannot_be_reused(anonymous_client, db):
    email = "replay@pytest.local"
    _signup(anonymous_client, email)
    code = _code_for(db, email)

    assert anonymous_client.post(VERIFY_URL, json={"email": email, "code": code}).status_code == 200
    replay = anonymous_client.post(VERIFY_URL, json={"email": email, "code": code})
    assert replay.status_code == 404


def test_resending_invalidates_the_previous_code(anonymous_client, db, monkeypatch):
    monkeypatch.setattr(settings, "OTP_RESEND_COOLDOWN_SECONDS", 0)
    email = "resend@pytest.local"
    _signup(anonymous_client, email)
    first_code = _code_for(db, email)

    assert anonymous_client.post(RESEND_URL, json={"email": email}).status_code == 200
    db.expire_all()
    second_code = _code_for(db, email)
    assert first_code != second_code

    assert anonymous_client.post(
        VERIFY_URL, json={"email": email, "code": first_code}
    ).status_code == 400
    assert anonymous_client.post(
        VERIFY_URL, json={"email": email, "code": second_code}
    ).status_code == 200


def test_resending_is_rate_limited(anonymous_client, monkeypatch):
    monkeypatch.setattr(settings, "OTP_RESEND_COOLDOWN_SECONDS", 300)
    email = "floodme@pytest.local"
    _signup(anonymous_client, email)

    response = anonymous_client.post(RESEND_URL, json={"email": email})
    assert response.status_code == 429
    assert "Retry-After" in response.headers


def test_resending_for_an_unknown_address_is_a_404(anonymous_client):
    assert anonymous_client.post(
        RESEND_URL, json={"email": "ghost@pytest.local"}
    ).status_code == 404


# --------------------------------------------------------------------------
# Duplicate and abandoned signups
# --------------------------------------------------------------------------
def test_signing_up_with_an_already_verified_email_is_refused(anonymous_client, db):
    email = "taken@pytest.local"
    _signup(anonymous_client, email)
    anonymous_client.post(VERIFY_URL, json={"email": email, "code": _code_for(db, email)})

    response = _signup(anonymous_client, email)
    assert response.status_code == 409


def test_an_abandoned_signup_can_be_restarted(anonymous_client, db):
    """A typo'd address must not be locked out permanently."""
    email = "abandoned@pytest.local"
    _signup(anonymous_client, email, name="First Try")
    assert _signup(anonymous_client, email, name="Second Try").status_code == 202

    db.expire_all()
    user = auth_service.get_by_email(db, email)
    assert user.display_name == "Second Try"
    assert user.email_verified is False

    # Only the newest code works.
    assert anonymous_client.post(
        VERIFY_URL, json={"email": email, "code": _code_for(db, email)}
    ).status_code == 200


def test_provisioned_accounts_are_verified_without_a_code(client_as, anonymous_client):
    """A supervisor vouching for someone is the out-of-band proof."""
    payload = {
        "email": "vouchedfor@pytest.local",
        "display_name": "Vouched For",
        "password": PASSWORD,
        "role": Role.RECOVERY_PLANNER.value,
        "country": "India",
    }
    created = client_as(Role.SUPERVISOR).post("/api/v1/auth/users", json=payload)
    assert created.status_code == 201
    assert created.json()["email_verified"] is True

    anonymous_client.headers.pop("Authorization", None)
    assert anonymous_client.post(
        LOGIN_URL, data={"username": payload["email"], "password": PASSWORD}
    ).status_code == 200


# --------------------------------------------------------------------------
# Validation and policy
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "payload,reason",
    [
        ({"email": "not-an-email", "display_name": "X", "password": PASSWORD}, "email shape"),
        ({"email": "ok@pytest.local", "display_name": "X", "password": "short"}, "password length"),
        ({"email": "ok2@pytest.local", "display_name": "", "password": PASSWORD}, "empty name"),
    ],
)
def test_invalid_signups_are_rejected(anonymous_client, payload, reason):
    assert anonymous_client.post(SIGNUP_URL, json=payload).status_code == 422, reason


def test_email_is_normalised_to_lowercase(anonymous_client, db):
    _signup(anonymous_client, "MiXeDcAsE@Pytest.Local")
    assert auth_service.get_by_email(db, "mixedcase@pytest.local") is not None


def test_the_signup_policy_is_published(anonymous_client):
    policy = anonymous_client.get("/api/v1/auth/signup/policy").json()

    assert policy["role_is_caller_selectable"] is False
    assert policy["default_role"] == Role.TECHNICIAN.value
    assert policy["max_attempts"] == settings.OTP_MAX_ATTEMPTS


def test_signup_endpoints_need_no_authentication(anonymous_client):
    """Obvious, but worth pinning: the router gating must not catch these."""
    anonymous_client.headers.pop("Authorization", None)
    assert anonymous_client.get("/api/v1/auth/signup/policy").status_code == 200
    assert _signup(anonymous_client, "anonymous-signup@pytest.local").status_code == 202


# --------------------------------------------------------------------------
# Delivery honesty
# --------------------------------------------------------------------------
def test_the_response_says_where_the_code_actually_went(anonymous_client):
    """With no SMTP server configured, the API must not claim it emailed anyone."""
    assert settings.smtp_configured is False

    body = _signup(anonymous_client, "wherediditgo@pytest.local").json()
    assert body["delivery_mode"] == "outbox"
    assert "No mail server is configured" in body["message"]


def test_a_code_is_written_to_the_outbox_when_there_is_no_mail_server(
    anonymous_client, tmp_path, monkeypatch
):
    monkeypatch.setattr(settings, "MAIL_OUTBOX_PATH", str(tmp_path))
    _signup(anonymous_client, "outboxed@pytest.local")

    written = list(tmp_path.glob("*.txt"))
    assert written, "expected the message to be written to the outbox"
    assert "outboxed@pytest.local" in written[0].read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "host,username,password,expected,reason",
    [
        ("", "", "", False, "nothing configured"),
        ("smtp.gmail.com", "me@gmail.com", "", False, "host and user but no credential yet"),
        ("smtp.gmail.com", "me@gmail.com", "app-password", True, "fully configured"),
        ("localhost", "", "", True, "relay needing no authentication"),
    ],
)
def test_half_configured_smtp_falls_back_to_the_outbox(
    monkeypatch, host, username, password, expected, reason
):
    """Pasting the server address before the credential must not break signup.

    That gap is a real deployment state - someone fills in SMTP_HOST, restarts,
    and pastes the app password a minute later. Treating it as "configured"
    would make every signup in between fail authentication with a 502.
    """
    monkeypatch.setattr(settings, "SMTP_HOST", host)
    monkeypatch.setattr(settings, "SMTP_USERNAME", username)
    monkeypatch.setattr(settings, "SMTP_PASSWORD", password)

    assert settings.smtp_configured is expected, reason


def test_generated_codes_are_the_expected_shape():
    codes = {signup_service.generate_code() for _ in range(200)}

    assert all(len(code) == signup_service.CODE_LENGTH for code in codes)
    assert all(code.isdigit() for code in codes)
    # 200 draws from a million should essentially never collide down to a
    # handful of values; a constant generator would.
    assert len(codes) > 150


def test_users_never_expose_a_password_hash(client_as):
    users = client_as(Role.SUPERVISOR).get("/api/v1/auth/users").json()
    assert users
    for user in users:
        assert "password_hash" not in user
        assert "password" not in user
