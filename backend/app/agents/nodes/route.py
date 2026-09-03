"""`route_cuisines` Node — wraps F002's `route_cuisines` for the graph.

Spec §3.2 row 2: 解析用户消息 + 偏好 → 1-3 个菜系. F002 already exposes an
async node-shaped function with the right signature; this module is a thin
adapter so:
- the graph can pull it into StateGraph via `add_node`.
- test injection (provider / rng) reaches the underlying F002 function.
"""
from __future__ import annotations

from typing import Any

from app.agents.main_router import route_cuisines as f002_route_cuisines
from app.agents.state import AgentState


async def node_route_cuisines(
    state: AgentState, **kwargs: Any
) -> dict[str, object]:
    """Forward to F002's main router entry point.

    F002 returns a `RouterOutput` partial — `selected_cuisines`,
    `routing_reason`, `routing_log`, optional `errors`. The graph reducer
    merges these into `AgentState` automatically (LangGraph default is
    replace; we use partial dict semantics).
    """
    return await f002_route_cuisines(state, **kwargs)


__all__ = ["node_route_cuisines"]
