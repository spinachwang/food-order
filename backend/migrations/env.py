"""Alembic environment — see `spec/data-model.md` for the source of truth.

Configuration:
- `target_metadata` = SQLModel.metadata (every model with `table=True` is auto-discovered)
- `sqlalchemy.url` is overridden at runtime from `app.core.config.get_settings()`,
  so alembic.ini's hard-coded URL is irrelevant in practice.
- All model modules are imported eagerly so SQLModel.metadata is populated before
  autogenerate runs.
"""
from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import engine_from_config, pool
from sqlmodel import SQLModel

# Repo layout: backend/migrations/env.py → ../../ is the repo root holding .env.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_BACKEND_ROOT = _REPO_ROOT / "backend"

# 1. Force-load the repo-root .env (cwd-relative pydantic-settings would otherwise
#    look for backend/.env which doesn't exist).
load_dotenv(_REPO_ROOT / ".env")

# 2. Ensure `app.*` imports resolve when alembic is invoked from any cwd.
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

# Import every model so SQLModel.metadata is populated. Add new models here.
from app.models.user_preference import UserPreference  # noqa: E402, F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = SQLModel.metadata


def _resolve_url() -> str:
    """Pick the production URL from settings, unless alembic.ini overrides it."""
    explicit = config.get_main_option("sqlalchemy.url")
    if explicit and explicit != "driver://user:pass@localhost/dbname":
        return explicit
    # Default: read from app config (which reads .env).
    from app.core.config import get_settings

    return get_settings().database_url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode — emit SQL to stdout without a DB connection."""
    context.configure(
        url=_resolve_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode — connect to the DB and apply DDL."""
    cfg = config.get_section(config.config_ini_section, {})
    cfg["sqlalchemy.url"] = _resolve_url()

    connectable = engine_from_config(cfg, prefix="sqlalchemy.", poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            render_as_batch=False,  # MySQL doesn't need batch mode
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
