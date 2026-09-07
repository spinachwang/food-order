"""User preferences service (F001 §4 — Agent 视角接口).

`load_preferences` / `upsert_preferences` are the service-layer wrappers around
the SQLModel row. They take a `Session` explicitly (no FastAPI Depends) so that
agents and tests can call them without dragging in HTTP plumbing.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal, cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.state import UserPreferencesDict
from app.models.user_preference import UserPreference
from app.schemas.preferences import PreferencesUpdate, default_cuisine_weights

__all__ = ["load_preferences", "upsert_preferences"]


# Lookup the BIGINT `id` and the `user_id` columns once at import time; this
# avoids leaking SQLModel typing tricks into the service body.
_TABLE = UserPreference.__table__  # type: ignore[attr-defined]
_ID_COLUMN = _TABLE.c.id
_USER_ID_COLUMN = _TABLE.c.user_id


def load_preferences(session: Session, user_id: str) -> UserPreferencesDict:
    """Return existing preferences, or fresh defaults if no row exists.

    F001 §2 acceptance: GET returns defaults rather than 404.
    """
    row = session.get(UserPreference, _row_id_for_user(session, user_id))
    if row is None:
        return _default_preferences(user_id)

    return _row_to_dict(row)


def upsert_preferences(
    session: Session, user_id: str, payload: PreferencesUpdate
) -> UserPreferencesDict:
    """Full overwrite upsert (F001 §2 — PUT covers all fields)."""
    row_id = _row_id_for_user(session, user_id)
    row = session.get(UserPreference, row_id)
    if row is None:
        row = UserPreference(user_id=user_id)
        session.add(row)

    row.cuisine_weights = dict(payload.cuisine_weights)
    row.allergies = list(payload.allergies)
    row.spice_tolerance = payload.spice_tolerance
    row.temperature_preference = payload.temperature_preference
    row.default_location = payload.default_location
    row.budget_lunch_min = payload.budget_lunch_min
    row.budget_lunch_max = payload.budget_lunch_max
    # updated_at is bumped automatically by SQLModel on flush in many setups;
    # we set explicitly to keep behavior consistent across MySQL/Postgres.
    row.updated_at = datetime.utcnow()

    session.commit()
    session.refresh(row)
    return _row_to_dict(row)


# ----- helpers -----


def _row_id_for_user(session: Session, user_id: str) -> int | None:
    """Look up the primary key for a given user_id; returns None if absent."""
    stmt = select(_ID_COLUMN).where(user_id == _USER_ID_COLUMN)
    pk = session.execute(stmt).scalar_one_or_none()
    return int(pk) if pk is not None else None


def _row_to_dict(row: UserPreference) -> UserPreferencesDict:
    return {
        "user_id": row.user_id,
        "cuisine_weights": dict(row.cuisine_weights or {}),
        "allergies": list(row.allergies or []),
        "spice_tolerance": int(row.spice_tolerance),
        # The DB column is VARCHAR(8); we narrow to the Literal enum at the
        # boundary because the DB CHECK constraint guarantees membership.
        "temperature_preference": cast(
            Literal["cold", "room", "hot"], row.temperature_preference
        ),
        "default_location": row.default_location,
        "budget_lunch_min": _maybe_decimal(row.budget_lunch_min),
        "budget_lunch_max": _maybe_decimal(row.budget_lunch_max),
    }


def _maybe_decimal(v: Decimal | None) -> Decimal | None:
    return None if v is None else Decimal(v)


def _default_preferences(user_id: str) -> UserPreferencesDict:
    """Defaults for first-time visitors (F001 §3.3 + §3.4 + Phase 1 §3.4)."""
    return {
        "user_id": user_id,
        "cuisine_weights": default_cuisine_weights(),
        "allergies": [],
        "spice_tolerance": 0,
        "temperature_preference": "room",
        "default_location": None,
        "budget_lunch_min": None,
        "budget_lunch_max": None,
    }
