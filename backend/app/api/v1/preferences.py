"""`/api/v1/preferences` router — F001.

The actual data work happens in `app.services.preferences`. This module just
maps HTTP → service calls and service → Pydantic response.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.agents.state import UserPreferencesDict
from app.core.db import get_db
from app.core.user_id import get_current_user_id
from app.schemas.preferences import PreferencesRead, PreferencesUpdate
from app.services import preferences as preferences_service

router = APIRouter()


def _to_read_model(prefs: UserPreferencesDict) -> PreferencesRead:
    """Service-layer TypedDict → Pydantic response model."""
    return PreferencesRead(**prefs)


@router.get("", response_model=PreferencesRead)
def get_preferences(
    user_id: str = Depends(get_current_user_id),
    session: Session = Depends(get_db),
) -> PreferencesRead:
    """Return current preferences; auto-creates defaults if absent (F001 §2)."""
    return _to_read_model(preferences_service.load_preferences(session, user_id))


@router.put("", response_model=PreferencesRead)
def put_preferences(
    payload: PreferencesUpdate,
    user_id: str = Depends(get_current_user_id),
    session: Session = Depends(get_db),
) -> PreferencesRead:
    """Full overwrite of preferences (F001 §2)."""
    return _to_read_model(
        preferences_service.upsert_preferences(session, user_id, payload)
    )


# Marker so `app.api.v1.__init__` can detect this module loaded cleanly.
__all__ = ["router", "status"]
