"""SQLAlchemy engine, session factory and declarative base.

The application supports both PostgreSQL (production / Docker Compose) and
SQLite (zero-setup local development). The correct connect arguments are
selected automatically from the DATABASE_URL setting.
"""

from __future__ import annotations

from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings

_is_sqlite = settings.DATABASE_URL.startswith("sqlite")

engine: Engine = create_engine(
    settings.DATABASE_URL,
    echo=settings.SQL_ECHO,
    future=True,
    pool_pre_ping=not _is_sqlite,
    connect_args={"check_same_thread": False} if _is_sqlite else {},
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    """Declarative base shared by every ORM model."""


if _is_sqlite:

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _connection_record):  # pragma: no cover
        """Enable foreign-key enforcement on SQLite (off by default)."""
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a scoped database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_all() -> None:
    """Create every table declared on the Base metadata.

    Alembic is the supported migration path for production; this helper keeps
    the prototype runnable with a single command.
    """
    from app import models  # noqa: F401  (registers all mappers)

    Base.metadata.create_all(bind=engine)
    _ensure_chain_lock_row()


def _ensure_chain_lock_row() -> None:
    """Seed the single row audit_service serialises appends against.

    Idempotent: safe to call on every startup and every test-suite run.
    """
    from app.models.audit import AuditChainLock

    with SessionLocal() as session:
        if session.get(AuditChainLock, 1) is None:
            session.merge(AuditChainLock(id=1, version=0))
            session.commit()


def drop_all() -> None:
    """Drop every table - used by the seed script --reset flag."""
    from app import models  # noqa: F401

    Base.metadata.drop_all(bind=engine)
