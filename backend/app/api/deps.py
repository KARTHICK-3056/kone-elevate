"""Shared FastAPI dependencies: identity, authorisation and lookup helpers."""

from __future__ import annotations

from typing import Callable, Optional

from fastapi import Depends, HTTPException, Path, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.core.database import get_db
from app.core.security import decode_access_token
from app.core.tenancy import TenantScope
from app.models.component import Component
from app.models.user import User
from app.utils.enums import Role

#: ``auto_error=False`` so a missing token reaches :func:`get_current_user`
#: and produces our own 401 with a useful message, rather than FastAPI's
#: bare "Not authenticated".
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_PREFIX}/auth/login", auto_error=False
)

_UNAUTHENTICATED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Sign in to use this endpoint.",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Resolve the caller from their bearer token, or reject the request.

    This is the only way the application learns who is calling. There is no
    header, query parameter or request-body field that can name an actor -
    see :func:`current_actor` for why that matters.
    """
    if not token:
        raise _UNAUTHENTICATED

    payload = decode_access_token(token)
    if not payload or not payload.get("sub"):
        raise _UNAUTHENTICATED

    user = db.execute(
        select(User).where(User.email == str(payload["sub"]).lower())
    ).scalar_one_or_none()
    if user is None or not user.is_active:
        raise _UNAUTHENTICATED
    return user


def require_roles(*roles: Role) -> Callable[[User], User]:
    """Dependency factory restricting an endpoint to specific roles."""
    allowed = {role.value for role in roles}

    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"This action requires one of: {', '.join(sorted(allowed))}. "
                    f"Your role is '{user.role}'."
                ),
            )
        return user

    return checker


def get_tenant_scope(user: User = Depends(get_current_user)) -> TenantScope:
    """The caller's resolved country/frontline-unit scope for this request."""
    return TenantScope.for_user(user)


def current_actor(user: User = Depends(get_current_user)) -> str:
    """The verified identity recorded against every change in the audit chain.

    Previously this read an ``X-Actor`` request header and fell back to a
    configured default, which meant the tamper-evident chain proved only that
    *an unauthenticated claim* was recorded without subsequent edit. The hash
    chain was cryptographically sound and evidentially worthless. The header
    is gone: the actor is the authenticated subject or the request fails.

    Depending on this also enforces the one authorisation rule that applies
    everywhere - a read-only auditor may see everything and change nothing -
    because every endpoint that writes something already depends on it to
    name the author.
    """
    if user.is_read_only:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Read-only auditors cannot make changes. This account has "
                "view access to every record, including the audit chain."
            ),
        )
    return user.email[:96]


def _resolve_component(component_id: str, db: Session) -> Optional[Component]:
    statement = (
        select(Component)
        .options(selectinload(Component.predictions))
        .where(
            or_(
                Component.component_id == component_id,
                Component.serial_number == component_id,
                Component.qr_token == component_id,
            )
        )
    )
    return db.execute(statement).scalars().first()


def get_component_public_or_404(
    component_id: str = Path(..., description="Business component id, serial number or QR token"),
    db: Session = Depends(get_db),
) -> Component:
    """Resolve a component with NO auth and NO tenant check - the QR path.

    Used only by ``app/api/passports.py``, which is deliberately public: a
    technician scanning a label in a machine room has no login, and that is
    the product, not an oversight (see ``app/main.py``). Do not use this for
    any endpoint behind the authenticated routers - use
    :func:`get_component_or_404` there, which enforces the tenant boundary.
    """
    component = _resolve_component(component_id, db)
    if component is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Component '{component_id}' was not found.",
        )
    return component


def get_component_or_404(
    component_id: str = Path(..., description="Business component id, serial number or QR token"),
    db: Session = Depends(get_db),
    scope: TenantScope = Depends(get_tenant_scope),
) -> Component:
    """Resolve a component by id, serial number or QR token, tenant-checked.

    Technicians scan labels that may encode any of the three, so the lookup is
    deliberately forgiving while remaining an exact match (no wildcards).

    A component scoped to a country the caller cannot see is reported the
    same way as one that does not exist at all - see
    ``app.core.tenancy`` for why that is deliberate, not an oversight. This
    requires an authenticated caller; the public QR path uses
    :func:`get_component_public_or_404` instead.
    """
    component = _resolve_component(component_id, db)
    not_found = HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Component '{component_id}' was not found.",
    )
    if component is None:
        raise not_found
    if not scope.owns_country(component.country):
        raise not_found
    return component
