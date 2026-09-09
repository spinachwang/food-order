"""`/api/v1/preferences` router — F001.

The actual data work happens in `app.services.preferences`. This module just
maps HTTP → service calls and service → Pydantic response.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.agents.state import UserPreferencesDict
from app.core.db import get_db
from app.core.envelope import ok
from app.core.user_id import get_current_user_id
from app.schemas.preferences import PreferencesRead, PreferencesUpdate
from app.services import preferences as preferences_service

router = APIRouter()


def _to_read_model(prefs: UserPreferencesDict) -> PreferencesRead:
    """Service-layer TypedDict → Pydantic response model."""
    return PreferencesRead(**prefs)


@router.get("")
def get_preferences(
    user_id: str = Depends(get_current_user_id),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    """Return current preferences; auto-creates defaults if absent (F001 §2).

    Success response uses `spec/api.md §通用约定` envelope: `{"ok": true, "data": PreferencesRead}`.
    """
    payload = _to_read_model(preferences_service.load_preferences(session, user_id))
    return ok(payload)


@router.put("")
def put_preferences(
    payload_model: PreferencesUpdate,
    user_id: str = Depends(get_current_user_id),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    """Full overwrite of preferences (F001 §2).

    Success response uses `spec/api.md §通用约定` envelope: `{"ok": true, "data": PreferencesRead}`.
    """
    payload = _to_read_model(
        preferences_service.upsert_preferences(session, user_id, payload_model)
    )
    return ok(payload)


# Marker so `app.api.v1.__init__` can detect this module loaded cleanly.
__all__ = ["router", "status"]
