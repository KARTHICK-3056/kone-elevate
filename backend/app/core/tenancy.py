"""Row-level multi-tenancy scoping by frontline unit and country.

Two different filters, on purpose
----------------------------------
**Country** is the hard boundary. It maps onto the legal-entity / data-
residency line the build audit's GDPR finding was actually about, so it is
enforced everywhere a row carries one, with no opt-out short of a global
role: a technician in one country cannot read, list, or act on a row scoped
to another country. A mismatch on a direct lookup (``get_component_or_404``
and friends) returns a plain 404, not 403 - confirming that a specific
component exists in a country you cannot see would itself be a disclosure.

**Frontline unit** is a soft default. It decides what a caller sees without
asking, not what they are allowed to see: a technician's own branch is the
default view of the component portfolio and dashboard, overridable with
``?all_units=true`` (still bounded by country).

Global roles
------------
``SUSTAINABILITY_CONTROLLER`` and ``READ_ONLY_AUDITOR`` bypass both filters.
An ESRS/BRSR disclosure or an audit-chain verification that only sees one
country is not a company-wide disclosure or a real integrity check - both
roles exist specifically to see across the whole fleet.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import ColumnElement
from sqlalchemy.sql import Select

from app.models.user import User
from app.utils.enums import Role

#: Roles for which tenant scoping is bypassed entirely. See module docstring.
GLOBAL_ROLES = frozenset({Role.SUSTAINABILITY_CONTROLLER.value, Role.READ_ONLY_AUDITOR.value})

_NOT_FOUND = "not found"


@dataclass(frozen=True)
class TenantScope:
    """The caller's tenant, resolved once per request."""

    country: Optional[str]
    frontline_unit: Optional[str]
    is_global: bool

    @classmethod
    def for_user(cls, user: User) -> "TenantScope":
        return cls(
            country=user.country,
            frontline_unit=user.frontline_unit,
            is_global=user.role in GLOBAL_ROLES,
        )

    def owns_country(self, row_country: Optional[str]) -> bool:
        """True when this scope may see a row with the given country.

        A caller with no country of their own (mis-provisioned, or a global
        role with the field left null) can only see rows that likewise have
        no country - it never falls open to "sees everything".
        """
        return self.is_global or (self.country is not None and self.country == row_country)


def scope_by_country(statement: Select, country_column: ColumnElement, scope: TenantScope) -> Select:
    """Apply the hard country boundary to a SELECT. No-op for global roles."""
    if scope.is_global:
        return statement
    return statement.where(country_column == scope.country)


def scope_by_unit(
    statement: Select,
    unit_column: ColumnElement,
    scope: TenantScope,
    *,
    all_units: bool = False,
) -> Select:
    """Apply the soft frontline-unit default. No-op when global or overridden."""
    if scope.is_global or all_units:
        return statement
    return statement.where(unit_column == scope.frontline_unit)


def require_same_country(scope: TenantScope, row_country: Optional[str]) -> None:
    """Raise a 404 (never 403 - see module docstring) on a cross-country read."""
    if not scope.owns_country(row_country):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)
