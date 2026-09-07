"""`fetch_weather` Node — F031 + F004 §3.2 row 5.

调 `amap_get_weather(location)`, 把结果写入 `state["weather"]`. 任何
`AmapError` 都降级为 `weather=None` —— 让 F040 summary agent 走中庸档
(决策矩阵默认 false); 异常本身写进 `errors` 列表便于前端 SSE 渲染.

输入位置 (与 `search_restaurants` 一致): `state["location_override"]` 优先,
否则 `state["user_preferences"]["default_location"]`, 都没值时用国贸默认.
"""
from __future__ import annotations

import logging
from typing import cast

from app.agents.state import AgentState
from app.core.exceptions import AmapError
from app.core.request_id import get_request_id
from app.mcp.amap.weather import WeatherInfo, amap_get_weather

_logger = logging.getLogger(__name__)

_DEFAULT_LOCATION = "116.433840,39.908740"  # 国贸 (与 dev_route 习惯一致)
_DEFAULT_LOCATION_LABEL = "国贸"


def _resolve_location(state: AgentState) -> str:
    """解析锚点: 显式 override > 用户偏好 default_location > 国贸兜底."""
    override = state.get("location_override")
    if isinstance(override, str) and override.strip():
        return override.strip()
    prefs = state.get("user_preferences")
    if prefs is not None:
        default_loc = prefs.get("default_location")
        if isinstance(default_loc, str) and default_loc.strip():
            return default_loc.strip()
    return _DEFAULT_LOCATION


async def node_fetch_weather(state: AgentState) -> dict[str, object]:
    """F031 主 Node —— 调高德天气, 写 `weather` + 失败时降级.

    Returns:
        - 成功 → `{"weather": <WeatherInfo as dict>}` (LangGraph state 字段)
        - 失败 (AmapError) → `{"weather": None, "errors": [...]}`
        - 总是返回 dict, 不让异常传到上层 (F004 §3.4).
    """
    location = _resolve_location(state)
    rid = get_request_id() or "-"

    try:
        info: WeatherInfo = await amap_get_weather(location=location, extensions="base")
    except AmapError as exc:
        # F031 §5 + F004 §3.4: 高德错误 → weather=None, summary 走中庸档
        _logger.warning(
            "fetch_weather failed rid=%s location=%s code=%s msg=%s",
            rid, location, exc.code, exc.message,
        )
        existing = list(state.get("errors") or [])
        return {
            "weather": None,
            "errors": [
                *existing,
                {
                    "node": "fetch_weather",
                    "code": exc.code,
                    "message": exc.message,
                    "location": location,
                },
            ],
        }
    except (ValueError, RuntimeError) as exc:
        # 入参非法 / 其他未预期错误 — 同样兜底
        _logger.exception("fetch_weather unexpected error rid=%s", rid)
        existing = list(state.get("errors") or [])
        return {
            "weather": None,
            "errors": [
                *existing,
                {
                    "node": "fetch_weather",
                    "code": "FETCH_WEATHER_UNEXPECTED",
                    "message": str(exc),
                    "location": location,
                },
            ],
        }

    _logger.info(
        "fetch_weather ok rid=%s location=%s temp=%s cond=%s",
        rid, location, info["temperature_celsius"], info["condition"],
    )
    # TypedDict 直接喂 LangGraph state 即可 (它会按字段名取)
    return {"weather": cast(dict[str, object], dict(info))}


__all__ = ["_DEFAULT_LOCATION_LABEL", "node_fetch_weather"]