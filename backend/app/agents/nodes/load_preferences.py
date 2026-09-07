"""`load_preferences` Node — F004 §3.2.

In Phase 1 the API endpoint (`POST /api/v1/agent/chat`) loads preferences
synchronously from F001's `load_preferences` service (which has a DB
session via FastAPI Depends) and writes them into `AgentState` before the
graph runs. So this Node is a passthrough that:

1. Validates `user_preferences` is present (or fills defaults from
   `AgentState`); this defensive default lets the workflow still run
   when a test/forgot-to-load caller hands us a `user_id` only.
2. Records the resolved preferences onto the State delta so downstream
   nodes (`route_cuisines`) read a single source of truth.

When M2 swaps in PostgresSaver, we'll route the Session in via the graph's
`RunnableConfig` and call `load_preferences(session, user_id)` for real.
"""
from __future__ import annotations

import logging
from typing import cast

from app.agents.state import AgentState, UserPreferencesDict
from app.core.constants import CUISINE_IDS, NEUTRAL_CUISINE_WEIGHT
from app.core.request_id import get_request_id

_logger = logging.getLogger(__name__)


def node_load_preferences(state: AgentState) -> dict[str, object]:
    """Return partial State with `user_preferences` populated.

    Spec §3.2 row 1: 按 user_id 从 DB 读偏好；不存在则初始化默认值。
    The DB read already happened in the API layer; here we defensively fill
    in defaults if the upstream forgot.
    """
    user_id = str(state.get("user_id", ""))
    if not user_id:
        _logger.warning(
            "load_preferences: missing user_id in state rid=%s",
            get_request_id() or "-",
        )
        return {
            "errors": [
                {"code": "USER_ID_REQUIRED", "message": "user_id 为空，无法加载偏好"}
            ]
        }

    existing = state.get("user_preferences")
    if existing is not None:
        return {}  # API layer already supplied; no-op.

    return {"user_preferences": _neutral_preferences(user_id)}


def _neutral_preferences(user_id: str) -> UserPreferencesDict:
    """Fallback to use when upstream forgot to load preferences.

    Matches `_neutral_preferences` in `main_router.py` so the router's
    neutral-weights branch keeps working consistently.
    """
    return cast(
        UserPreferencesDict,
        {
            "user_id": user_id,
            "cuisine_weights": dict.fromkeys(CUISINE_IDS, NEUTRAL_CUISINE_WEIGHT),
            "allergies": [],
            "spice_tolerance": 0,
            "temperature_preference": "room",
            "default_location": None,
            "budget_lunch_min": None,
            "budget_lunch_max": None,
        },
    )


# Pin Decimal import as used by mypy — defensive cast above remains.
__all__ = ["node_load_preferences"]
