"""`fetch_weather` Node — F031 + F004 §3.2 row 5.

调 `amap_get_weather(location)`, 把结果写入 `state["weather"]`. 任何
`AmapError` 都降级为 `weather=None` —— 让 F040 summary agent 走中庸档
(决策矩阵默认 false); 异常本身写进 `errors` 列表便于前端 SSE 渲染.

输入位置 (与 `search_restaurants` 一致): `state["location_override"]` 优先,
否则 `state["user_preferences"]["default_location"]`, 都没值时用默认城市.

格式约束 (per F001 §3.5 + F031):
- 仅放行 6 位 adcode 或城市名 (Amap /v3/weather/weatherInfo 接受).
- 检测到 `lng,lat` 坐标 → fallback 到默认城市 + WARN log.
- 区级地标 / 完整地址 / 中英混合 → 不在 Node 层拦截, 透传给 Amap 让它
  自行判断 (Amap 不识别时仍会触发 AMAP_LOCATION_INVALID 走降级).
"""
from __future__ import annotations

import logging
import re
from typing import cast

from app.agents.state import AgentState
from app.core.exceptions import AmapError
from app.core.request_id import get_request_id
from app.mcp.amap.weather import WeatherInfo, amap_get_weather

_logger = logging.getLogger(__name__)

_DEFAULT_LOCATION = "110000"  # 北京 adcode (国贸所在城市)
_DEFAULT_LOCATION_LABEL = "国贸"

# 检测 `lng,lat` 坐标: 两个可选负号浮点数, 中间逗号. 例如 `116.43,39.91`
_COORD_PATTERN = re.compile(r"^-?\d+(\.\d+)?,-?\d+(\.\d+)?$")


def _looks_like_coord(value: str) -> bool:
    """是否 `lng,lat` 数字坐标. Amap weather API 不收坐标, 必须 fallback."""
    return bool(_COORD_PATTERN.match(value.strip()))


def _resolve_location(state: AgentState) -> str:
    """解析锚点: 显式 override > 用户偏好 default_location > 默认城市.

    F001 §3.5 格式约束: 仅放行 adcode / 城市名; 检测到坐标 → 跳过该值,
    fallback 并 WARN log. 区级地标等"近似城市名"的字符串不在 Node 层拦截
    (Amap 不识别时仍会触发 AMAP_LOCATION_INVALID 走正常降级路径).
    """
    rid = get_request_id() or "-"

    override = state.get("location_override")
    if isinstance(override, str) and override.strip():
        v = override.strip()
        if not _looks_like_coord(v):
            return v
        _logger.warning(
            "fetch_weather location_override 是坐标, fallback rid=%s override=%s",
            rid, v,
        )

    prefs = state.get("user_preferences")
    if prefs is not None:
        default_loc = prefs.get("default_location")
        if isinstance(default_loc, str) and default_loc.strip():
            v = default_loc.strip()
            if not _looks_like_coord(v):
                return v
            _logger.warning(
                "fetch_weather prefs.default_location 是坐标, fallback rid=%s location=%s",
                rid, v,
            )
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