"""`summarize` Node — F040 placeholder for F004 §3.2 row 6.

When F040 ships (spec/features/F040-summary-agent.md), this Node composes
the final `Recommendation` from `cuisine_results`, `restaurant_lists`,
`weather`, and `user_preferences`. Until then, we return
`recommendation=None` so the SSE layer emits a graceful `done` event
without a recommendation payload — per spec §3.4:
"summarize 异常 → 返回错误事件给前端，不写 recommendation".
"""
from __future__ import annotations

import logging

from app.agents.state import AgentState

_logger = logging.getLogger(__name__)

# Default "no recommendation" payload — keeps the SSE schema intact while
# F040 is being built. Real implementation should construct the full
# Recommendation object (F040 §3.2) keyed off the decision matrix.
_FALLBACK_RECOMMENDATION: dict[str, object] = {
    "headline": "今天没合适推荐，换个口味吧",
    "restaurant_id": "",
    "restaurant_name": "",
    "order_takeout": True,
    "reason": "推荐服务尚未就绪",
    "confidence": 0.0,
    "alternatives": [],
}


async def node_summarize(state: AgentState) -> dict[str, object]:
    """Stub: no real recommendation until F040 lands.

    Spec §3.4 错误处理: when summarize raises, return an error code and
    leave `recommendation` untouched. Phase 1 takes the safer fallback —
    a fixed message — so the graph always reaches END without raising.
    """
    cuisine_results = state.get("cuisine_results") or {}
    if not cuisine_results:
        # Spec §3.4 + F040 §7 — 全 0 candidates → degraded message.
        return {
            "recommendation": dict(_FALLBACK_RECOMMENDATION),
        }
    # Real F040 will replace this branch with the full decision matrix
    # (天气 × 距离 × 偏好加权). For Phase 1 we just emit a placeholder
    # so the SSE schema downstream has a stable payload to parse.
    return {
        "recommendation": dict(_FALLBACK_RECOMMENDATION),
    }


__all__ = ["node_summarize"]
