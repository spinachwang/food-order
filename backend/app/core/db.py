"""SQLAlchemy engine + session factory + FastAPI `get_db` dependency.

Phase 1 uses synchronous SQLAlchemy via PyMySQL for simplicity. Async migration
(per `alembic init -t async`) lands when we actually need async streaming reads
in F004 / F040.
"""
from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


def make_engine(url: str | None = None, *, echo: bool = False) -> Engine:
    """Create a SQLAlchemy engine. Defaults to the production settings URL."""
    settings = get_settings()
    return create_engine(
        url or settings.database_url,
        echo=echo,
        pool_pre_ping=True,
        future=True,
    )


_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    """Lazy singleton engine used by the running application."""
    global _engine, _SessionLocal
    if _engine is None:
        _engine = make_engine()
        _SessionLocal = sessionmaker(
            bind=_engine, autocommit=False, autoflush=False, expire_on_commit=False
        )
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    """Lazy singleton session factory."""
    get_engine()
    assert _SessionLocal is not None
    return _SessionLocal


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a session and ensures cleanup."""
    SessionLocal = get_session_factory()
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def reset_engine() -> None:
    """For tests that need to swap the engine (e.g. to the test schema)."""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None
