"""Account provisioning and credential verification.

Scope, honestly stated
----------------------
This authenticates against the platform's own ``users`` table using PBKDF2
password hashing. It is **not** single sign-on. The realistic production
target named in ``plan.md`` is OIDC against Microsoft Entra ID, which needs a
company tenant this build has no access to.

What that swap would touch is deliberately small: the login endpoint hands
back a token, and :func:`app.api.deps.get_current_user` turns a token back
into a :class:`User`. Replacing local credentials with Entra means changing
how the token is *obtained and validated* - not how any of the ~40 endpoints
that depend on an identity behave.
"""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.models.user import User
from app.utils.enums import Role


class DuplicateUserError(ValueError):
    """Raised when an email is already registered."""


def normalise_email(email: str) -> str:
    """Emails are matched case-insensitively and stored lowercased."""
    return (email or "").strip().lower()


def get_by_email(db: Session, email: str) -> Optional[User]:
    return db.execute(
        select(User).where(User.email == normalise_email(email))
    ).scalar_one_or_none()


def create_user(
    db: Session,
    email: str,
    password: str,
    display_name: str,
    role: str,
    is_active: bool = True,
    email_verified: bool = True,
    country: Optional[str] = None,
    frontline_unit: Optional[str] = None,
    commit: bool = True,
) -> User:
    """Provision an account.

    ``email_verified`` defaults to True because this path is how a supervisor
    (or the seed script) creates an account for someone: the address has been
    vouched for out of band, so there is nothing to prove by email. Only
    :mod:`app.services.signup_service` creates unverified accounts.

    Raises :class:`DuplicateUserError` on a repeat email and ``ValueError``
    on an unknown role - the role is validated here rather than trusted,
    because an invalid role string would otherwise fail open at the
    permission check.
    """
    email = normalise_email(email)
    if role not in Role.values():
        raise ValueError(f"Unknown role '{role}'. Valid roles: {', '.join(Role.values())}")
    if get_by_email(db, email) is not None:
        raise DuplicateUserError(f"An account for '{email}' already exists.")

    user = User(
        email=email,
        display_name=display_name.strip(),
        password_hash=hash_password(password),
        role=role,
        is_active=is_active,
        email_verified=email_verified,
        country=country,
        frontline_unit=frontline_unit,
    )
    db.add(user)
    db.flush()
    if commit:
        db.commit()
        db.refresh(user)
    return user


class UnverifiedEmailError(RuntimeError):
    """Correct credentials, but the address was never confirmed."""


def authenticate(db: Session, email: str, password: str) -> Optional[User]:
    """Return the user when the credentials are valid, otherwise ``None``.

    Deliberately returns the same ``None`` for "no such account", "wrong
    password" and "account deactivated" so the caller cannot use the failure
    to enumerate which emails exist.

    The one distinguishable outcome is :class:`UnverifiedEmailError`, raised
    only *after* the password has been checked. That leaks nothing to someone
    who does not already know the password, and without it a user who never
    finished signing up gets "incorrect email or password" for credentials
    that are, in fact, correct - and has no way to guess that the fix is to
    enter a code.
    """
    user = get_by_email(db, email)
    if user is None:
        # Spend roughly the same time as a real verification so a missing
        # account is not distinguishable by response latency.
        verify_password(password, hash_password("timing-equalisation"))
        return None
    if not verify_password(password, user.password_hash):
        return None
    if not user.email_verified:
        raise UnverifiedEmailError(user.email)
    if not user.is_active:
        return None
    return user


def list_users(db: Session) -> List[User]:
    return list(db.execute(select(User).order_by(User.email.asc())).scalars().all())
