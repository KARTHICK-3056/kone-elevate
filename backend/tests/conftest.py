"""Shared pytest fixtures.

Every test runs against an isolated, file-backed SQLite database created in a
temporary directory, so the suite never touches a developer database and each
module starts from a clean schema.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from typing import Dict, Generator, Optional

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Point the application at a throwaway database *before* the settings singleton
# is created, so importing the app can never touch a developer database.
_SCRATCH_DB = Path(tempfile.gettempdir()) / "kone_elevate_pytest_app.db"
_SCRATCH_DB.unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite:///{_SCRATCH_DB.as_posix()}"
# The test suite runs against the shipped placeholder SECRET_KEY on purpose;
# DEBUG=true is what tells main.py's startup guard that this is expected,
# same as any other local-development run.
os.environ.setdefault("DEBUG", "true")
# Password hashing is deliberately expensive in production (240,000 PBKDF2
# rounds, ~0.7s per hash on a modest machine). The suite creates and verifies
# many accounts, so run it at a token work factor: a test suite that spends
# most of its wall clock burning CPU on purpose is testing nothing. The round
# count is recorded inside each hash, so this changes nothing about how
# production hashes verify.
os.environ.setdefault("PBKDF2_ROUNDS", "1000")
# Settings.model_config loads a real developer .env (backend/.env or repo
# root .env) if one exists, same as production. Without pinning these, a
# developer with real SMTP credentials configured locally for manual testing
# gets a test suite that silently sends real email and asserts on
# `smtp_configured` differently than a clean checkout would - exactly the
# "never touches a developer database" isolation this fixture module already
# promises, just for SMTP instead of the database.
os.environ["SMTP_HOST"] = ""
os.environ["SMTP_USERNAME"] = ""
os.environ["SMTP_PASSWORD"] = ""

from app.core.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    """Every test starts with a clean rate-limit state.

    app.core.rate_limit keys its in-memory windows by client address, and
    every test in this suite calls through the same TestClient "testclient"
    address. Without this, whichever test runs first "uses up" the login/
    signup budget for every test that runs after it in the same session -
    found the hard way: adding rate limiting to /auth/signup turned nearly
    every unrelated test in test_signup.py into a 429.
    """
    from app.core import rate_limit

    rate_limit._windows.clear()
    yield
    rate_limit._windows.clear()


@pytest.fixture(scope="module")
def engine(tmp_path_factory):
    """Module-scoped SQLite engine backed by a temporary file."""
    directory = tmp_path_factory.mktemp("kone_elevate_db")
    database_url = f"sqlite:///{(directory / 'test.db').as_posix()}"
    test_engine = create_engine(
        database_url, connect_args={"check_same_thread": False}, future=True
    )
    Base.metadata.create_all(bind=test_engine)

    # Seed the audit-chain lock row the same way app.core.database.create_all
    # does in production, since this fixture creates the schema directly.
    from app.models.audit import AuditChainLock

    with Session(test_engine) as seed_session:
        seed_session.merge(AuditChainLock(id=1, version=0))
        seed_session.commit()

    yield test_engine
    Base.metadata.drop_all(bind=test_engine)
    test_engine.dispose()


@pytest.fixture(scope="module")
def session_factory(engine):
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


@pytest.fixture()
def db(session_factory) -> Generator[Session, None, None]:
    """A direct database session for service-level tests."""
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


#: Every test account shares this password. Long enough to satisfy the
#: 12-character minimum enforced by the provisioning schema.
TEST_PASSWORD = "pytest-password-2026"


#: Every non-global-role test account gets this tenant so existing tests
#: (written before P4 multi-tenancy) keep working without every fixture
#: having to know about country/frontline_unit. See app.core.tenancy for why
#: the two global roles get neither.
TEST_COUNTRY = "India"
TEST_FRONTLINE_UNIT = "Chennai"


def _ensure_user(session_factory, role: str) -> str:
    """Create (once) a test account for a role and return its email."""
    from app.core.tenancy import GLOBAL_ROLES
    from app.services import auth_service

    email = f"{role}@pytest.local"
    is_global = role in GLOBAL_ROLES
    with session_factory() as session:
        if auth_service.get_by_email(session, email) is None:
            auth_service.create_user(
                session,
                email=email,
                password=TEST_PASSWORD,
                display_name=f"Test {role}",
                role=role,
                country=None if is_global else TEST_COUNTRY,
                frontline_unit=None if is_global else TEST_FRONTLINE_UNIT,
            )
    return email


def _token_for(session_factory, role: str) -> str:
    from app.core.security import create_access_token

    return create_access_token(subject=_ensure_user(session_factory, role), role=role)


@pytest.fixture()
def anonymous_client(session_factory) -> Generator[TestClient, None, None]:
    """API client with no credentials at all.

    Used to prove that protected endpoints reject unauthenticated callers and
    that the public passport/QR path still works without signing in.
    """

    def override_get_db() -> Generator[Session, None, None]:
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def client(anonymous_client, session_factory) -> TestClient:
    """API client signed in as a supervisor.

    Supervisor is the broadest non-auditor role, so the rest of the suite
    exercises application behaviour rather than re-testing authorisation on
    every call. Tests that care about *who* is calling use
    :func:`client_as` or :func:`anonymous_client` instead.
    """
    from app.utils.enums import Role

    token = _token_for(session_factory, Role.SUPERVISOR.value)
    anonymous_client.headers.update({"Authorization": f"Bearer {token}"})
    return anonymous_client


@pytest.fixture()
def client_as(anonymous_client, session_factory):
    """Factory returning a client signed in as any given role."""

    def _build(role) -> TestClient:
        value = getattr(role, "value", role)
        token = _token_for(session_factory, value)
        anonymous_client.headers.update({"Authorization": f"Bearer {token}"})
        return anonymous_client

    return _build


@pytest.fixture()
def tenant_client(anonymous_client, session_factory):
    """Factory returning an INDEPENDENT client for an explicit (role, country, unit).

    ``client``/``client_as`` mutate and return the shared ``anonymous_client``
    object, which is fine when a test only ever acts as one identity at a
    time - the usual case. Multi-tenancy tests need two *simultaneously*
    authenticated identities in the same test (a technician in each of two
    countries), so this returns a fresh ``TestClient`` per call instead of
    overwriting a shared one's headers out from under an earlier caller.
    Depending on ``anonymous_client`` first ensures the ``get_db`` override
    is already installed on the app before any of these are built - that
    override lives on ``app.dependency_overrides`` and is shared by every
    ``TestClient`` wrapping the same ``app``, fresh instances included.
    """
    from app.core.security import create_access_token
    from app.services import auth_service

    def _build(
        role, country: Optional[str] = None, frontline_unit: Optional[str] = None, email: Optional[str] = None
    ) -> TestClient:
        value = getattr(role, "value", role)
        address = email or f"{value}-{country or 'global'}-{frontline_unit or 'x'}@pytest.local"
        with session_factory() as session:
            if auth_service.get_by_email(session, address) is None:
                auth_service.create_user(
                    session,
                    email=address,
                    password=TEST_PASSWORD,
                    display_name=f"Test {value} ({country or 'global'})",
                    role=value,
                    country=country,
                    frontline_unit=frontline_unit,
                )
        token = create_access_token(subject=address, role=value)
        scoped_client = TestClient(app)
        scoped_client.headers.update({"Authorization": f"Bearer {token}"})
        return scoped_client

    return _build


@pytest.fixture()
def component_payload() -> Dict[str, object]:
    """A valid component creation payload."""
    return {
        "component_type": "Motor",
        "material": "Steel",
        "manufacturer": "KONE MonoSpace",
        "origin": "Chennai Plant",
        "installation_date": "2018-04-12",
        "location": "Chennai, India",
        "operating_hours": 18000,
        "load_cycles": 140000,
        "average_load": 650,
        "vibration": 3.8,
        "temperature": 52,
        "service_count": 5,
        "repair_count": 1,
        "failure_history": 0,
        "inspection_score": 82,
        "run_initial_prediction": True,
    }


@pytest.fixture()
def prediction_payload() -> Dict[str, object]:
    """A valid ad-hoc prediction payload."""
    return {
        "component_type": "Motor",
        "material": "Steel",
        "component_age": 5.2,
        "operating_hours": 18000,
        "load_cycles": 140000,
        "average_load": 650,
        "vibration": 3.8,
        "temperature": 52,
        "service_count": 5,
        "repair_count": 1,
        "failure_history": 0,
        "inspection_score": 82,
        "days_since_last_service": 90,
    }


@pytest.fixture()
def created_component(client, component_payload) -> Dict[str, object]:
    """Create a component through the API and return its representation."""
    response = client.post("/api/v1/components", json=component_payload)
    assert response.status_code == 201, response.text
    return response.json()


#: Usage and condition the trained model assesses as Component Recovery -
#: worn past its current application but with serviceable sub-components.
PARTS_RECOVERY_CONDITION: Dict[str, object] = {
    "operating_hours": 47000,
    "load_cycles": 980000,
    "vibration": 4.6,
    "temperature": 63,
    "inspection_score": 63,
    "installation_date": "2013-03-01",
    "run_initial_prediction": True,
}


@pytest.fixture()
def parts_recovery_payload(component_payload) -> Dict[str, object]:
    """A component payload the model assesses as Component Recovery."""
    return {**component_payload, **PARTS_RECOVERY_CONDITION}
