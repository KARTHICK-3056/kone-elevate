"""Request and response models for authentication."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.utils.enums import Role


def _normalise_email(value: str) -> str:
    """Lowercase, trim, and check the address is shaped like one.

    Deliberately not full RFC 5322 validation: that needs a dependency this
    project does not carry, and for a corporate deployment the authoritative
    check is the identity provider, not this field. For self-service signup
    the real check is whether a code sent to the address comes back.
    """
    candidate = (value or "").strip().lower()
    local, separator, domain = candidate.partition("@")
    if not separator or not local or "." not in domain or domain.endswith("."):
        raise ValueError("Enter a valid email address, e.g. name@example.com")
    return candidate


class Token(BaseModel):
    """A successful login response."""

    access_token: str
    token_type: str = "bearer"
    expires_in_minutes: int
    user: "UserRead"


class UserRead(BaseModel):
    """An account as returned by the API. Never carries the password hash."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    display_name: str
    role: Role
    is_active: bool
    email_verified: bool
    country: Optional[str] = None
    frontline_unit: Optional[str] = None
    created_at: datetime


class UserCreate(BaseModel):
    """Provisioning payload. Supervisor-only - there is no public signup."""

    email: str = Field(..., min_length=3, max_length=160)
    display_name: str = Field(..., min_length=1, max_length=96)
    password: str = Field(
        ...,
        min_length=12,
        max_length=128,
        description="Minimum 12 characters. Stored PBKDF2-hashed, never in plain text.",
    )
    role: Role
    country: Optional[str] = Field(
        None,
        max_length=64,
        description="Tenant boundary. Required for every role except the two global ones.",
    )
    frontline_unit: Optional[str] = Field(None, max_length=96, description="Home branch/site.")

    _validate_email = field_validator("email")(_normalise_email)


class SignupRequest(BaseModel):
    """Self-service signup.

    There is deliberately no ``role`` field. A self-registered account always
    receives the lowest-privilege role; anything above that is granted by a
    supervisor. See :mod:`app.services.signup_service`.
    """

    email: str = Field(..., min_length=3, max_length=160)
    display_name: str = Field(..., min_length=1, max_length=96)
    password: str = Field(
        ...,
        min_length=12,
        max_length=128,
        description="Minimum 12 characters. Stored PBKDF2-hashed, never in plain text.",
    )

    _validate_email = field_validator("email")(_normalise_email)


class VerifyEmailRequest(BaseModel):
    """The emailed code, plus the address it was sent to."""

    email: str = Field(..., min_length=3, max_length=160)
    code: str = Field(..., min_length=4, max_length=12)

    _validate_email = field_validator("email")(_normalise_email)

    @field_validator("code")
    @classmethod
    def _strip_code(cls, value: str) -> str:
        # People paste codes with spaces in them.
        return value.strip().replace(" ", "").replace("-", "")


class ResendCodeRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=160)

    _validate_email = field_validator("email")(_normalise_email)


class SignupResponse(BaseModel):
    """What happened, and crucially *where the code actually went*."""

    email: str
    display_name: str
    role: Role
    verification_required: bool = True
    #: "smtp" when a real email was sent, "outbox" when no mail server is
    #: configured and the code was written to the log instead. The UI shows
    #: the difference rather than telling someone to check an inbox that will
    #: never receive anything.
    delivery_mode: str
    message: str
    code_expires_in_minutes: int


Token.model_rebuild()
