"""`/api/v1/agent/chat` SSE endpoint — F004 §4 + `spec/api.md` M1 §POST.

The endpoint:
1. Resolves user_id via F001's `UserIdMiddleware` (header / cookie / generated UUID).
2. Pre-loads preferences from F001's `load_preferences` service (DB-backed).
3. Runs the LangGraph workflow (`build_graph(checkpointer=True)`) and
   translates each Node's lifecycle event into an SSE frame per spec §4.
4. On graph completion, emits a final `done` frame; on any Node error,
   emits an `error` frame.

The mapping is centralized in `_state_event_for_node` so other endpoints
(F040 telemetry, F050 frontend) can re-use it.

Phase 1 caveat: F030 / F031 / F040 are placeholders (see
`app/agents/nodes/{search_restaurants,fetch_weather,summarize}.py`).
The endpoint still emits the `restaurant_found` / `weather` /
`recommendation` frames but with empty payloads. Once each upstream spec
ships its implementation, no API change is needed.
"""
from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.agents.graph import GRAPH_NODE_NAMES, build_graph
from app.agents.state import AgentState
from app.core.db import get_db
from app.core.user_id import get_current_user_id
from app.services import preferences as preferences_service

_logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Request / response models — Pydantic v2 per project tech-stack table
# ---------------------------------------------------------------------------


class ChatRequest(BaseModel):
    """`POST /api/v1/agent/chat` request body — `spec/api.md` §M1."""

    message: str
    session_id: str | None = None
    location_override: str | None = None


# Mapping: LangGraph Node name → SSE event name (spec §4).
# `load_preferences` and `stream_output` are silent (no SSE frame).
_NODE_TO_SSE_EVENT: dict[str, str] = {
    "route_cuisines": "cuisine_selected",
    "cuisine_fanout": "cuisine_result",
    "search_restaurants": "restaurant_found",
    "fetch_weather": "weather",
    "summarize": "recommendation",
}


# ---------------------------------------------------------------------------
# Streaming entry point
# ---------------------------------------------------------------------------


@router.post("/chat")
async def post_chat(
    payload: ChatRequest,
    request: Request,
    user_id: str = Depends(get_current_user_id),
    session: Session = Depends(get_db),
) -> StreamingResponse:
    """SSE stream from user message → final recommendation.

    The response body is the SSE wire format:

        event: <name>
        data: <json>

        \\n

    Each frame is `event:` + `data:` + blank line. The terminal frame is
    always `event: done\\ndata: {}\\n\\n`. Errors mid-stream use
    `event: error\\ndata: {"code": "...", "message": "..."}\\n\\n`.
    """
    preferences = preferences_service.load_preferences(session, user_id)
    initial_state: AgentState = {
        "user_id": user_id,
        "user_message": payload.message,
        "session_id": payload.session_id,
        "location_override": payload.location_override,
        "user_preferences": preferences,
        # LangGraph fills the rest from Node returns.
    }

    thread_id = payload.session_id or user_id
    config: dict[str, Any] = {"configurable": {"thread_id": thread_id}}

    async def event_source() -> AsyncIterator[bytes]:
        # The compiled graph is shared across requests in M1 (no per-request
        # state). MemorySaver is process-global; thread_id is the only
        # partitioning key. M2 swaps to PostgresSaver where this becomes
        # connection-scoped.
        compiled = build_graph(checkpointer=True)
        try:
            async for event in compiled.astream_events(  # type: ignore[attr-defined]
                initial_state,
                config=config,
                version="v2",
            ):
                # Stop emitting once the client disconnects.
                if await request.is_disconnected():
                    _logger.info("client disconnected mid-stream user_id=%s", user_id)
                    return
                frame = _frame_from_event(event)
                if frame is not None:
                    yield frame
            yield _sse_frame("done", {})
        except Exception as e:
            _logger.exception("agent chat failed user_id=%s", user_id)
            yield _sse_frame(
                "error",
                {
                    "code": "AGENT_GRAPH_ERROR",
                    "message": f"{type(e).__name__}: {e}",
                },
            )

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # disable proxy buffering
        },
    )


# ---------------------------------------------------------------------------
# Helpers — pure functions, easy to unit-test
# ---------------------------------------------------------------------------


def _frame_from_event(event: dict[str, Any]) -> bytes | None:
    """Translate one LangGraph v2 event into an SSE frame (or None to skip).

    We respond to two lifecycle hooks per Node:
    - `on_chain_end` whose `name` matches a graph Node → emit the SSE
      event whose payload is the cumulative State at that point.
    - Errors → emit `event: error` with `data.code` / `data.message`.

    Everything else (`on_chain_start`, `on_chain_stream`, internal
    `__start__` / `_write` / `LangGraph`) is skipped — only end-of-Node
    frames carry the user-facing payload boundary.
    """
    if not isinstance(event, dict):
        return None
    name = str(event.get("name") or "")
    event_type = str(event.get("event") or "")
    if name not in GRAPH_NODE_NAMES:
        return None
    if event_type != "on_chain_end":
        # Stream events + start events have no use for SSE consumers — the
        # payload is incomplete until the Node finishes.
        return None

    sse_event = _NODE_TO_SSE_EVENT.get(name)
    if sse_event is None:
        # Silent Nodes: load_preferences, stream_output. Spec §4 has no row
        # for them.
        return None

    state_payload = _state_payload_for_event(name, event)
    if state_payload is None:
        return None
    return _sse_frame(sse_event, state_payload)


def _state_payload_for_event(
    name: str, event: dict[str, Any]
) -> dict[str, Any] | None:
    """Extract the user-facing payload from a LangGraph `on_chain_end` event.

    LangGraph stores the Node output under `event["data"]["output"]` (v2).
    Different Nodes contribute different slices of State:
    - `route_cuisines` → selected_cuisines + routing_reason
    - `cuisine_fanout` → cuisine_results (dict-keyed)
    - `search_restaurants` → restaurant_lists
    - `fetch_weather` → weather
    - `summarize` → recommendation

    If the slice is absent (e.g. F030 not yet built, returns empty mapping),
    we still emit the frame with the empty payload so the frontend's event
    timeline is uniform across specifications.
    """
    output = event.get("data", {}).get("output")
    if not isinstance(output, dict):
        return None
    if name == "route_cuisines":
        return {
            "cuisines": list(output.get("selected_cuisines") or []),
            "routing_reason": str(output.get("routing_reason") or ""),
        }
    if name == "cuisine_fanout":
        return {"results": dict(output.get("cuisine_results") or {})}
    if name == "search_restaurants":
        return {"restaurant_lists": dict(output.get("restaurant_lists") or {})}
    if name == "fetch_weather":
        return {"weather": output.get("weather")}
    if name == "summarize":
        return {"recommendation": output.get("recommendation")}
    return None


def _sse_frame(event: str, data: dict[str, Any]) -> bytes:
    """Serialize one SSE frame per spec §M1 wire format.

    Format:

        event: <event>
        data: <json>
        \\n

    The blank line terminator is required by the SSE spec; FastAPI's
    `StreamingResponse` flushes after each `yield`.
    """
    payload = json.dumps(data, ensure_ascii=False, default=str)
    return f"event: {event}\ndata: {payload}\n\n".encode()


__all__ = ["ChatRequest", "_frame_from_event", "_sse_frame", "router"]
