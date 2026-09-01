"""Agent state TypedDicts — stable home shared by F002 (router), F003 (cuisine experts),
F004 (LangGraph workflow) and F040 (summary agent).

These are internal interface contracts (TypedDict). External HTTP layer uses
Pydantic schemas in `app/schemas/`. Per Python coding-style.md we keep state
immutable (frozen dataclass where concrete, TypedDict where dynamic keys).
"""
from __future__ import annotations

from decimal import Decimal
from typing import Literal, NotRequired, TypedDict

# ----- F001 §4 — user preferences (internal view) -----

UserPreferencesDict = TypedDict(
    "UserPreferencesDict",
    {
        "user_id": str,
        "cuisine_weights": dict[str, float],   # 14 keys, value in [0, 1]
        "allergies": list[str],                # 0-N elements
        "spice_tolerance": int,                # 0-3
        "temperature_preference": Literal["cold", "room", "hot"],
        "default_location": str | None,
        "budget_lunch_min": Decimal | None,
        "budget_lunch_max": Decimal | None,
    },
)


# ----- F003 §3.1 — cuisine expert input / output -----

class CuisineExpertInput(TypedDict):
    user_message: str
    user_preferences: UserPreferencesDict
    location: str | None
    spice_tolerance: int
    budget_min: float | None
    budget_max: float | None

CuisineExpertOutput = TypedDict(
    "CuisineExpertOutput",
    {
        "cuisine_id": str,
        "conclusion": str,
        "keywords": list[str],
        "matched_allergies": list[str],  # TODO(M2): see F003 §7 — field may be dropped
    },
)


# ----- F004 §6 — LangGraph workflow state (Phase 1 placeholder) -----
# Phase 4 (F004) fills in nodes / reducers / checkpoint strategy.
# Keep keys stable: any future addition must be backward compatible.

AgentState = TypedDict(
    "AgentState",
    {
        "user_id": str,
        "session_id": NotRequired[str],
        "user_message": str,
        "user_preferences": NotRequired[UserPreferencesDict],
        "location_override": NotRequired[str | None],
        "selected_cuisines": NotRequired[list[str]],
        "cuisine_results": NotRequired[dict[str, CuisineExpertOutput]],
        "weather": NotRequired[dict[str, object]],           # F031
        "restaurants": NotRequired[dict[str, list[dict[str, object]]]],  # F030 by cuisine
        "recommendation": NotRequired[dict[str, object]],    # F040 final
        "errors": NotRequired[list[dict[str, str]]],
    },
)
