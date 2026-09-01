"""Shared pytest fixtures for the backend test suite.

Test database strategy (per M1 plan §6):
- **session-scoped**: `test_engine` connects to MySQL without schema, drops &
  recreates `food_order_test` with utf8mb4, then runs `alembic upgrade head`
  to bring the schema to the spec'd shape. This is the only MySQL setup.
- **function-scoped**: `db_session` opens a connection, starts a transaction,
  and binds a Session to it. After the test the outer transaction is rolled
  back, so each test starts from a clean state — fast, no TRUNCATE cost.
- `client` fixture yields a FastAPI `TestClient` whose `get_db` is overridden
  to hand out the session-scoped savepoint session.
"""
from __future__ import annotations

import asyncio
import uuid
from collections.abc import Generator

import pytest
import sqlalchemy as sa
from app.core.config import get_settings
from app.core.db import get_db
from app.main import create_app
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

# ---------------------------------------------------------------------------
# asyncio loop (session-scoped — respx / httpx share this loop)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ---------------------------------------------------------------------------
# Test database — created once per session
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def test_engine() -> Generator[Engine, None, None]:
    """Create the `food_order_test` schema and run alembic migrations once."""
    settings = get_settings()

    # Drop + create the test schema via a server-level (no database) connection.
    admin_engine = create_engine(
        settings.admin_database_url,
        isolation_level="AUTOCOMMIT",
        future=True,
    )
    with admin_engine.connect() as conn:
        conn.execute(text(f"DROP DATABASE IF EXISTS {settings.db_name_test}"))
        conn.execute(
            text(
                f"CREATE DATABASE {settings.db_name_test} "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci"
            )
        )
    admin_engine.dispose()

    # Build a real engine bound to the test schema, then upgrade.
    engine = create_engine(settings.test_database_url, pool_pre_ping=True, future=True)
    from alembic import command
    from alembic.config import Config as AlembicConfig

    cfg = AlembicConfig()
    cfg.set_main_option("script_location", "migrations")
    cfg.set_main_option("sqlalchemy.url", settings.test_database_url)
    command.upgrade(cfg, "head")

    yield engine

    engine.dispose()


# ---------------------------------------------------------------------------
# Per-test session with SAVEPOINT rollback
# ---------------------------------------------------------------------------


@pytest.fixture
def db_session(test_engine: Engine) -> Generator[Session, None, None]:
    """Open a transaction + nested SAVEPOINT; rollback after the test."""
    connection = test_engine.connect()
    transaction = connection.begin()
    SessionLocal = sessionmaker(bind=connection, expire_on_commit=False)
    session = SessionLocal()

    nested = connection.begin_nested()

    @sa.event.listens_for(session, "after_transaction_end")
    def _restart_savepoint(_sess: Session, _trans: sa.orm.SessionTransaction) -> None:
        nonlocal nested
        if not nested.is_active:
            nested = connection.begin_nested()

    try:
        yield session
    finally:
        session.close()
        if transaction.is_active:
            transaction.rollback()
        connection.close()


# ---------------------------------------------------------------------------
# FastAPI client (with get_db overridden)
# ---------------------------------------------------------------------------


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    """TestClient with `get_db` overridden to yield the per-test session."""
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def random_user_id() -> str:
    """A fresh UUID — for tests that want an explicit X-User-Id header."""
    return str(uuid.uuid4())