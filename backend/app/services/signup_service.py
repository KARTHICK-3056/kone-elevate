"""Self-service signup, gated by an emailed one-time code.

The security shape of this, stated plainly
-------------------------------------------
Verifying that someone can read an inbox proves exactly one thing: they own
that inbox. It says nothing about what they should be allowed to do. So a
self-registered account always lands on ``SIGNUP_DEFAULT_ROLE`` - the lowest
privilege level - and only a supervisor can raise it. The signup endpoint
never reads a role from the request; there is no field for one.

Code handling follows the same rules as password handling:

* only the SHA-256 of a code is stored, so a database dump yields no live codes
* comparison is constant-time
* codes expire (``OTP_TTL_MINUTES``) and are single-use
* wrong guesses are capped (``OTP_MAX_ATTEMPTS``) and burn the code
* resends are rate-limited (``OTP_RESEND_COOLDOWN_SECONDS``)

Without the attempt cap, six digits is a million guesses - a few minutes of
scripted requests.
"""

from __future__ import annotations

import hmac
import secrets
from datetime import timedelta
from typing import Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import sha256_hex
from app.models.user import User
from app.models.verification import EmailVerification
from app.services import auth_service, email_service
from app.services.email_service import DeliveryResult
from app.utils.enums import Role
from app.utils.helpers import utcnow

CODE_LENGTH = 6
PURPOSE_SIGNUP = "signup"


class SignupError(RuntimeError):
    """Base class for signup problems that are the caller's to fix."""


class EmailAlreadyRegisteredError(SignupError):
    """The address already has a usable account."""


class VerificationNotFoundError(SignupError):
    """No pending verification for this address."""


class CodeExpiredError(SignupError):
    """The code timed out."""


class TooManyAttemptsError(SignupError):
    """The code was burned by repeated wrong guesses."""


class InvalidCodeError(SignupError):
    """Wrong code, with attempts remaining."""


class ResendTooSoonError(SignupError):
    """A code was requested again inside the cooldown window."""

    def __init__(self, seconds_remaining: int) -> None:
        super().__init__(
            f"A code was just sent. Wait {seconds_remaining}s before requesting another."
        )
        self.seconds_remaining = seconds_remaining


def generate_code() -> str:
    """A cryptographically random numeric code, zero-padded."""
    return f"{secrets.randbelow(10 ** CODE_LENGTH):0{CODE_LENGTH}d}"


def _hash_code(code: str) -> str:
    return sha256_hex(code.strip())


def _active_challenge(db: Session, user: User) -> Optional[EmailVerification]:
    """The most recent unconsumed challenge for a user, if any."""
    return db.execute(
        select(EmailVerification)
        .where(EmailVerification.user_id == user.id)
        .where(EmailVerification.purpose == PURPOSE_SIGNUP)
        .where(EmailVerification.consumed_at.is_(None))
        .order_by(EmailVerification.id.desc())
        .limit(1)
    ).scalar_one_or_none()


def _issue_code(db: Session, user: User) -> Tuple[str, EmailVerification]:
    """Invalidate any outstanding challenge and mint a fresh one."""
    now = utcnow()
    for stale in db.execute(
        select(EmailVerification)
        .where(EmailVerification.user_id == user.id)
        .where(EmailVerification.purpose == PURPOSE_SIGNUP)
        .where(EmailVerification.consumed_at.is_(None))
    ).scalars().all():
        stale.consumed_at = now

    code = generate_code()
    challenge = EmailVerification(
        user_id=user.id,
        code_hash=_hash_code(code),
        purpose=PURPOSE_SIGNUP,
        expires_at=now + timedelta(minutes=settings.OTP_TTL_MINUTES),
    )
    db.add(challenge)
    db.flush()
    return code, challenge


def start_signup(
    db: Session, email: str, password: str, display_name: str, commit: bool = True
) -> Tuple[User, DeliveryResult]:
    """Create an unverified account and email it a code.

    The account exists immediately but cannot sign in: ``email_verified`` is
    false and :func:`auth_service.authenticate` refuses it. Re-signing up for
    an address that never finished verifying is allowed, and replaces the
    password and pending code - otherwise a typo'd address would lock that
    address out permanently.
    """
    email = auth_service.normalise_email(email)
    existing = auth_service.get_by_email(db, email)

    if existing is not None:
        if existing.email_verified:
            # Note: this confirms to an anonymous caller that an address is
            # registered. The privacy-preserving alternative (always claim
            # success, email the real owner a "someone tried to sign up"
            # notice) costs a confusing dead end for every user who simply
            # forgot they had an account. For a prototype whose accounts are
            # demo accounts, the clearer error is the better trade - but it
            # is a trade, not an oversight.
            raise EmailAlreadyRegisteredError(
                "That email already has an account. Sign in instead."
            )
        # An abandoned, never-verified signup: take it over.
        existing.display_name = display_name.strip()
        existing.password_hash = auth_service.hash_password(password)
        user = existing
    else:
        user = auth_service.create_user(
            db,
            email=email,
            password=password,
            display_name=display_name,
            role=settings.SIGNUP_DEFAULT_ROLE,
            commit=False,
        )
        user.email_verified = False

    code, _ = _issue_code(db, user)
    if commit:
        db.commit()
        db.refresh(user)

    delivery = email_service.send_verification_code(user.email, user.display_name, code)
    return user, delivery


def resend_code(db: Session, email: str, commit: bool = True) -> Tuple[User, DeliveryResult]:
    """Issue a fresh code, subject to the cooldown."""
    user = auth_service.get_by_email(db, auth_service.normalise_email(email))
    if user is None or user.email_verified:
        raise VerificationNotFoundError(
            "No signup is waiting to be verified for that address."
        )

    latest = _active_challenge(db, user)
    if latest is not None:
        elapsed = (utcnow() - latest.created_at).total_seconds()
        remaining = settings.OTP_RESEND_COOLDOWN_SECONDS - elapsed
        if remaining > 0:
            raise ResendTooSoonError(int(remaining) + 1)

    code, _ = _issue_code(db, user)
    if commit:
        db.commit()

    delivery = email_service.send_verification_code(user.email, user.display_name, code)
    return user, delivery


def verify_code(db: Session, email: str, code: str, commit: bool = True) -> User:
    """Check a code and, on success, activate the account.

    Raises a specific :class:`SignupError` subclass for each failure so the
    API can tell the user whether to retry, wait, or request a new code.
    """
    user = auth_service.get_by_email(db, auth_service.normalise_email(email))
    if user is None:
        raise VerificationNotFoundError(
            "No signup is waiting to be verified for that address."
        )
    if user.email_verified:
        raise VerificationNotFoundError("That address is already verified. Sign in instead.")

    challenge = _active_challenge(db, user)
    if challenge is None:
        raise VerificationNotFoundError(
            "No code is outstanding for that address. Request a new one."
        )
    if challenge.is_expired():
        challenge.consumed_at = utcnow()
        if commit:
            db.commit()
        raise CodeExpiredError("That code has expired. Request a new one.")

    # Checked before comparing, so a burned challenge stops accepting even
    # the correct code. The row is deliberately left unconsumed: it is what
    # lets this keep answering "too many attempts, request a new one" instead
    # of the much more confusing "no code is outstanding".
    if challenge.attempts >= settings.OTP_MAX_ATTEMPTS:
        raise TooManyAttemptsError(
            "Too many incorrect attempts. That code is no longer valid - "
            "request a new one."
        )

    if not hmac.compare_digest(challenge.code_hash, _hash_code(code)):
        challenge.attempts += 1
        remaining = settings.OTP_MAX_ATTEMPTS - challenge.attempts
        if commit:
            db.commit()
        if remaining <= 0:
            raise TooManyAttemptsError(
                "Too many incorrect attempts. That code is no longer valid - "
                "request a new one."
            )
        raise InvalidCodeError(
            f"Incorrect code. {remaining} attempt{'s' if remaining != 1 else ''} remaining."
        )

    challenge.consumed_at = utcnow()
    user.email_verified = True
    user.is_active = True
    if commit:
        db.commit()
        db.refresh(user)
    return user


def signup_policy() -> dict:
    """What the signup flow does, for the UI and the API docs to state."""
    return {
        "default_role": settings.SIGNUP_DEFAULT_ROLE,
        "role_is_caller_selectable": False,
        "code_length": CODE_LENGTH,
        "code_ttl_minutes": settings.OTP_TTL_MINUTES,
        "max_attempts": settings.OTP_MAX_ATTEMPTS,
        "resend_cooldown_seconds": settings.OTP_RESEND_COOLDOWN_SECONDS,
        "mail_configured": settings.smtp_configured,
        "note": (
            "Self-registration grants the lowest-privilege role only. Verifying "
            "an inbox proves ownership of an address, not entitlement to act - "
            f"anything above '{settings.SIGNUP_DEFAULT_ROLE}' is granted by a "
            "supervisor."
        ),
    }


#: Boot-time guard. A typo in SIGNUP_DEFAULT_ROLE should stop the application
#: starting, not surface as a confusing failure the first time a real person
#: tries to sign up.
DEFAULT_SIGNUP_ROLE = Role(settings.SIGNUP_DEFAULT_ROLE)
