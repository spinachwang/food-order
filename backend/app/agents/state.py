"""Agent state TypedDicts — stable home shared by F002 (router), F003 (cuisine experts),
F004 (LangGraph workflow) and F040 (summary agent).

These are internal interface contracts (TypedDict). External HTTP layer uses
Pydantic schemas in `app/schemas/`. Per Python coding-style.md we keep state
immutable (frozen dataclass where concrete, TypedDict where dynamic keys).

`AgentState` uses `total=False` so LangGraph 0.2.x can introspect the schema
into a Pydantic v2 model without choking on `NotRequired[...]` qualifiers.
The "required vs optional" contract is documented in `spec/features/F004-
langgraph-workflow.md §3.1` and enforced by the API layer (`api/v1/agent.py`),
which always populates `user_id` / `user_message` / `user_preferences`.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Literal

# `typing_extensions.TypedDict` is required (vs `typing.TypedDict`) because
# Pydantic v2 — used by LangGraph 0.2.x to introspect the schema — only
# supports the backport on Python <3.12. We are pinned to 3.11.
from typing_extensions import TypedDict

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


# ----- F004 §3.1 — LangGraph workflow state -----
# Phase 4 (F004) fills in nodes / reducers / checkpoint strategy.
# Keep keys stable: any future addition must be backward compatible.
#
# Required-by-convention (F004 §3.1): `user_id`, `user_message`,
# `user_preferences`. All other fields are populated by Nodes as the graph
# progresses. Always-quoted access (e.g. `state["user_id"]`) is a programmer
# error if the field is missing — the API layer + spec guarantee presence.

AgentState = TypedDict(
    "AgentState",
    {
        # Inputs from the API layer (always present).
        "user_id": str,
        "user_message": str,
        "user_preferences": UserPreferencesDict | None,
        # Optional inputs.
        "session_id": str | None,
        "location_override": str | None,
        # F002 router outputs.
        "selected_cuisines": list[str],
        "routing_reason": str,
        "routing_log": list["RoutingLogEntry"],
        # F003 cuisine experts write here, dict-keyed by cuisine_id.
        # F004 owns the resolution: spec §3.1 wrote `list[CuisineExpertOutput]`,
        # but dict-by-id is the natural shape for parallel-fanin merging and
        # what F003 §6 (`test_cuisine_parallel`) already exercises.
        "cuisine_results": dict[str, CuisineExpertOutput],
        # F030 — restaurant_lists[cuisine_id] = [Restaurant, ...].
        "restaurant_lists": dict[str, list[dict[str, object]]],
        # F031 — single weather snapshot or None on failure.
        "weather": dict[str, object] | None,
        # F040 — final Recommendation payload or None if no upstream data.
        "recommendation": dict[str, object] | None,
        # Global error sink — every Node contributes via this list.
        "errors": list[dict[str, str]],
    },
    total=False,
)


# ----- F002 — router observability & node return shape -----


class RoutingLogEntry(TypedDict):
    """One entry in `AgentState.routing_log`.

    `layer` is one of: "rule", "fuzzy", "llm", "allergy", "fallback".
    """

    ts: str               # ISO-8601 UTC, 便于前端排序与 grep
    layer: str            # 哪一层做了决策
    detail: str           # 人类可读的决策说明（如 "matched spicy" / "零候选：忌口"）
    elapsed_ms: int       # 该层耗时（毫秒），规则/模糊层断言 <100ms


class RouterOutput(TypedDict, total=False):
    """Partial state returned by the F002 router node.

    All fields are optional (NotRequired) so the node only writes what it
    actually decided — F004's graph reducer merges into `AgentState`.
    """

    selected_cuisines: list[str]
    routing_reason: str
    routing_log: list[RoutingLogEntry]
    errors: list[dict[str, str]]
