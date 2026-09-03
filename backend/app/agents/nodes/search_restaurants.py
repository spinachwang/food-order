"""`search_restaurants` Node — F030 placeholder for F004 §3.2 row 4.

When F030 ships (spec/features/F030-amap-restaurant-search.md), replace this
Node's body with a real AMAP call. Until then, the Node returns an empty
`restaurant_lists` mapping so the rest of the graph keeps running — per
spec §3.4: "search_restaurants 异常 → 该 cuisine_id 餐厅列表为空，summary 跳过".
"""
from __future__ import annotations

import logging
from typing import cast

from app.agents.state import AgentState

_logger = logging.getLogger(__name__)


async def node_search_restaurants(state: AgentState) -> dict[str, object]:
    """Stub: no restaurant data until F030 lands.

    Real implementation will iterate `state["selected_cuisines"]` and call
    the AMAP `amap_search_restaurants` tool per cuisine, populating
    `state["restaurant_lists"][cuisine_id]`. For Phase 1 we set the field
    to an empty dict (a strict subset of the F030 contract).
    """
    selected = list(state.get("selected_cuisines") or [])
    cuisine_results = state.get("cuisine_results") or {}
    # Empty mapping — leaving `restaurant_lists` absent would also work,
    # but Materializing it makes downstream SSE handlers uniform.
    empty_map: dict[str, list[dict[str, object]]] = {
        cid: [] for cid in (*selected, *cast(list[str], list(cuisine_results.keys())))
    }
    return {"restaurant_lists": empty_map}


__all__ = ["node_search_restaurants"]
