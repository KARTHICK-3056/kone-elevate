"""User accounts backing real login and role-based access control.

Accounts are provisioned, not self-selected: there is no public
registration endpoint (see ``app/api/auth.py``), the same way a real
company's identity system doesn't let an employee pick their own access
level at signup. ``scripts/seed_users.py`` creates the initial accounts
directly against the database - the same bootstrapping pattern
``scripts/seed_database.py`` already uses for demo components.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.utils.enums import Role
from app.utils.helpers import utcnow


class User(Base):
    """An account able to log in and act within its assigned role."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(160), unique=True, index=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(96), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(160), nullable=False)
    role: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    #: Administrative state: an account a supervisor has switched off.
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    #: Whether the address has been proven by entering an emailed code.
    #: Kept separate from ``is_active`` on purpose - "never finished signing
    #: up" and "deactivated by a supervisor" are different states that happen
    #: to block sign-in the same way, and conflating them makes it impossible
    #: to tell which one you are looking at. Accounts provisioned by a
    #: supervisor are created already verified; self-registered ones are not.
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # --- tenant scope (P4 multi-tenancy) -----------------------------------
    #: ISO-3166 country code (or country name) this account's row-level scope
    #: is bound to. Null only for the two global roles - see
    #: ``app.core.tenancy.GLOBAL_ROLES`` - everyone else must have one, or
    #: they see nothing once scoping is applied.
    country: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    #: Home frontline unit (branch/site). Soft default only: it decides what a
    #: technician sees *without asking*, not what they are allowed to see -
    #: see ``app.core.tenancy``.
    frontline_unit: Mapped[Optional[str]] = mapped_column(String(96), index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<User {self.email} {self.role}>"

    @property
    def is_read_only(self) -> bool:
        return self.role == Role.READ_ONLY_AUDITOR.value

    @property
    def can_sign_in(self) -> bool:
        return bool(self.is_active and self.email_verified)
