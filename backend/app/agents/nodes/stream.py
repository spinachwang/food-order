"""`stream_output` Node — F004 §3.2 row 7.

Spec describes this Node as "把 State 变化转为 SSE 事件". Mapping
LangGraph state changes onto SSE event names (spec §4) happens in the
SSE consumer layer (`app/api/v1/agent.py`), not in the graph — LangGraph's
`astream_events(version="v2")` already exposes Node lifecycle hooks that
the consumer turns into SSE frames.

This Node exists only as a terminal anchor:
- It runs after `summarize`, ensuring the graph has a single, named
  finalization step before `END` (rather than `summarize → END`).
- Future hooks (e.g. fire telemetry, set a `streamed_at` field on State)
  can land here without re-wiring edges.
"""
from __future__ import annotations

from typing import Any

from app.agents.state import AgentState


def node_stream_output(state: AgentState) -> dict[str, Any]:
    """No-op terminal Node. SSE work happens in the API layer."""
    return {}


__all__ = ["node_stream_output"]
