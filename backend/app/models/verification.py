"""One-time codes emailed to prove someone owns an address.

Only the *hash* of a code is stored. A database dump therefore does not hand
an attacker a list of live sign-up codes, for the same reason the ``users``
table stores password hashes rather than passwords.

Codes are short-lived and attempt-capped: six digits is a million
combinations, which is a trivial number to brute-force if a code never
expires and guesses are unlimited.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.utils.helpers import utcnow


class EmailVerification(Base):
    """A pending email-ownership challenge for one account."""

    __tablename__ = "email_verifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    #: SHA-256 of the emailed code. Never the code itself.
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    purpose: Mapped[str] = mapped_column(String(32), default="signup", nullable=False)

    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    consumed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    __table_args__ = (Index("ix_email_verifications_user_purpose", "user_id", "purpose"),)

    @property
    def is_consumed(self) -> bool:
        return self.consumed_at is not None

    def is_expired(self, now: Optional[datetime] = None) -> bool:
        return (now or utcnow()) >= self.expires_at

    @property
    def is_usable(self) -> bool:
        return not self.is_consumed and not self.is_expired()

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<EmailVerification user={self.user_id} {self.purpose} used={self.is_consumed}>"
