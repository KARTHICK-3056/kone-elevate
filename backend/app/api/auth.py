"""Login, identity and account provisioning."""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.core.config import settings
from app.core.database import get_db
from app.core.rate_limit import login_rate_limit, signup_rate_limit
from app.core.security import create_access_token
from app.models.user import User
from app.schemas.auth import (
    ResendCodeRequest,
    SignupRequest,
    SignupResponse,
    Token,
    UserCreate,
    UserRead,
    VerifyEmailRequest,
)
from app.services import auth_service, signup_service
from app.services.auth_service import DuplicateUserError, UnverifiedEmailError
from app.services.email_service import EmailDeliveryError
from app.services.signup_service import (
    CodeExpiredError,
    EmailAlreadyRegisteredError,
    InvalidCodeError,
    ResendTooSoonError,
    TooManyAttemptsError,
    VerificationNotFoundError,
)
from app.utils.enums import Role

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/login",
    response_model=Token,
    summary="Sign in",
    description=(
        "Exchanges an email and password for a signed bearer token. Send the "
        "token as `Authorization: Bearer <token>` on every subsequent "
        "request.\n\n"
        "Uses the OAuth2 password-form shape, so Swagger's own **Authorize** "
        "button works against it directly.\n\n"
        "**This is local authentication against the platform's own user "
        "table, not single sign-on.** The production target is OIDC against "
        "Microsoft Entra ID, which requires a company tenant this build has "
        "no access to. Only how the token is obtained and validated would "
        "change; no endpoint that consumes an identity would."
    ),
    responses={401: {"description": "Invalid credentials or inactive account"}},
)
def login(
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
    _rate_limit: None = Depends(login_rate_limit),
) -> Token:
    # OAuth2's form field is named `username`; this deployment uses email.
    try:
        user = auth_service.authenticate(db, form.username, form.password)
    except UnverifiedEmailError as exc:
        # Only reachable with a correct password, so this tells an attacker
        # nothing they did not already know - and without it, someone who
        # abandoned signup gets "incorrect password" for a correct one.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "This email has not been verified yet. Enter the code that was "
                "sent to it, or request a new one."
            ),
        ) from exc

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = create_access_token(subject=user.email, role=user.role)
    return Token(
        access_token=token,
        expires_in_minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES,
        user=UserRead.model_validate(user),
    )


@router.get(
    "/me",
    response_model=UserRead,
    summary="Who am I",
    description="The signed-in account behind the supplied bearer token.",
)
def me(user: User = Depends(get_current_user)) -> UserRead:
    return UserRead.model_validate(user)


# --------------------------------------------------------------------------
# Self-service signup
# --------------------------------------------------------------------------
def _issue_token(user: User) -> Token:
    return Token(
        access_token=create_access_token(subject=user.email, role=user.role),
        expires_in_minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES,
        user=UserRead.model_validate(user),
    )


def _delivery_message(delivery) -> str:
    if delivery.delivered_externally:
        return f"A {signup_service.CODE_LENGTH}-digit code has been emailed to you."
    return (
        f"No mail server is configured, so the {signup_service.CODE_LENGTH}-digit "
        "code was written to the backend log and to data/outbox/ instead of "
        "being emailed. Check the server console."
    )


@router.get(
    "/signup/policy",
    summary="What signing up does",
    description=(
        "The rules the signup flow enforces, so the UI can state them rather "
        "than hard-coding its own copy of them."
    ),
)
def signup_policy() -> dict:
    return signup_service.signup_policy()


@router.post(
    "/signup",
    response_model=SignupResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Create an account",
    description=(
        "Creates an unverified account and emails it a one-time code. The "
        "account cannot sign in until that code is entered.\n\n"
        "**The request has no role field, deliberately.** A self-registered "
        "account always receives the lowest-privilege role. Proving you can "
        "read an inbox proves you own the address - it says nothing about "
        "what you should be allowed to do, so anything above that role is "
        "granted by a supervisor.\n\n"
        "202, not 201: the account exists but is not yet usable."
    ),
    responses={
        409: {"description": "Email already has a verified account"},
        502: {"description": "A mail server is configured but could not be reached"},
    },
)
def signup(
    payload: SignupRequest,
    db: Session = Depends(get_db),
    _rate_limit: None = Depends(signup_rate_limit),
) -> SignupResponse:
    try:
        user, delivery = signup_service.start_signup(
            db,
            email=payload.email,
            password=payload.password,
            display_name=payload.display_name,
        )
    except EmailAlreadyRegisteredError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except EmailDeliveryError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    return SignupResponse(
        email=user.email,
        display_name=user.display_name,
        role=Role(user.role),
        delivery_mode=delivery.mode,
        message=_delivery_message(delivery),
        code_expires_in_minutes=settings.OTP_TTL_MINUTES,
    )


@router.post(
    "/signup/verify",
    response_model=Token,
    summary="Verify an emailed code",
    description=(
        "Confirms ownership of the address and activates the account, "
        "returning a token so the user is signed in immediately.\n\n"
        "Codes are single-use, expire, and are capped at a fixed number of "
        "wrong guesses - six digits is a million combinations, which is "
        "nothing without an attempt limit."
    ),
    responses={
        400: {"description": "Wrong, expired, or exhausted code"},
        404: {"description": "Nothing awaiting verification for that address"},
    },
)
def verify_email(payload: VerifyEmailRequest, db: Session = Depends(get_db)) -> Token:
    try:
        user = signup_service.verify_code(db, email=payload.email, code=payload.code)
    except VerificationNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (InvalidCodeError, CodeExpiredError, TooManyAttemptsError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return _issue_token(user)


@router.post(
    "/signup/resend",
    response_model=SignupResponse,
    summary="Send a new code",
    description=(
        "Invalidates any outstanding code and issues a fresh one. Rate "
        "limited, so this cannot be used to flood an address."
    ),
    responses={
        404: {"description": "Nothing awaiting verification for that address"},
        429: {"description": "Asked again inside the cooldown window"},
        502: {"description": "A mail server is configured but could not be reached"},
    },
)
def resend_code(payload: ResendCodeRequest, db: Session = Depends(get_db)) -> SignupResponse:
    try:
        user, delivery = signup_service.resend_code(db, email=payload.email)
    except VerificationNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ResendTooSoonError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(exc),
            headers={"Retry-After": str(exc.seconds_remaining)},
        ) from exc
    except EmailDeliveryError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    return SignupResponse(
        email=user.email,
        display_name=user.display_name,
        role=Role(user.role),
        delivery_mode=delivery.mode,
        message=_delivery_message(delivery),
        code_expires_in_minutes=settings.OTP_TTL_MINUTES,
    )


@router.get(
    "/users",
    response_model=List[UserRead],
    summary="List accounts",
    description="Every provisioned account. Supervisor only.",
)
def list_users(
    _: User = Depends(require_roles(Role.SUPERVISOR)),
    db: Session = Depends(get_db),
) -> List[UserRead]:
    return [UserRead.model_validate(user) for user in auth_service.list_users(db)]


@router.post(
    "/users",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Provision an account",
    description=(
        "Creates an account with an assigned role. **Supervisor only** - "
        "there is deliberately no public sign-up, because an endpoint that "
        "lets a caller choose their own role is a privilege-escalation hole "
        "wearing a registration form. The first accounts are created out of "
        "band by `scripts/seed_users.py`, the same way demo components are "
        "seeded."
    ),
    responses={
        403: {"description": "Caller is not a supervisor"},
        409: {"description": "Email already registered"},
    },
)
def create_user(
    payload: UserCreate,
    _: User = Depends(require_roles(Role.SUPERVISOR)),
    db: Session = Depends(get_db),
) -> UserRead:
    from app.core.tenancy import GLOBAL_ROLES

    if payload.role.value not in GLOBAL_ROLES and not payload.country:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"'{payload.role.value}' is a tenant-scoped role and needs a country - "
                "only sustainability_controller and read_only_auditor may be global."
            ),
        )
    try:
        user = auth_service.create_user(
            db,
            email=payload.email,
            password=payload.password,
            display_name=payload.display_name,
            role=payload.role.value,
            country=payload.country,
            frontline_unit=payload.frontline_unit,
        )
    except DuplicateUserError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return UserRead.model_validate(user)
