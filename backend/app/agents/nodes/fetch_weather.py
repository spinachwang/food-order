"""`fetch_weather` Node — F031 placeholder for F004 §3.2 row 5.

When F031 ships (spec/features/F031-amap-weather.md), replace this Node's
body with a real AMAP call. Until then, returns `weather=None` so the
summary agent (F040) takes its 中庸 fallback path — per spec §3.4:
"fetch_weather 异常 → weather=None, summary 用默认决策".
"""
from __future__ import annotations

import logging

from app.agents.state import AgentState

_logger = logging.getLogger(__name__)


async def node_fetch_weather(state: AgentState) -> dict[str, object]:
    """Stub: no weather data until F031 lands."""
    return {"weather": None}


__all__ = ["node_fetch_weather"]
