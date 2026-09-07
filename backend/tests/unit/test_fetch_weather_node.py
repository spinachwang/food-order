"""F031 — `fetch_weather` Node 单测.

Node 在 `app/agents/nodes/fetch_weather.py`. 输入: `AgentState` (含
`location_override` / `user_preferences.default_location`). 输出: `weather`
字典或 `None` (失败时). 不直接测 MCP 层 (`amap_get_weather`) — 那个属于
`test_amap_weather.py`. 这里只断言 Node 的编排逻辑.

`fetch_weather.py` 用的是 `from app.mcp.amap.weather import amap_get_weather`,
所以 mock 必须指向**消费侧**: `app.agents.nodes.fetch_weather.amap_get_weather`
(import 已把名字绑到该 namespace, 改源模块属性不会影响已绑定的引用).
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, cast
from unittest.mock import patch

from app.agents.nodes.fetch_weather import _resolve_location, node_fetch_weather
from app.agents.state import AgentState, UserPreferencesDict
from app.core.constants import CUISINE_IDS
from app.core.exceptions import AmapLocationInvalidError, AmapNetworkError

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _prefs(**overrides: Any) -> UserPreferencesDict:
    prefs: UserPreferencesDict = {
        "user_id": "u-f031",
        "cuisine_weights": dict.fromkeys(CUISINE_IDS, 0.5),
        "allergies": [],
        "spice_tolerance": 1,
        "temperature_preference": "room",
        "default_location": "国贸",
        "budget_lunch_min": Decimal("30.00"),
        "budget_lunch_max": Decimal("80.00"),
    }
    prefs.update(cast(Any, overrides))
    return prefs


def _state(**overrides: Any) -> AgentState:
    state: AgentState = {
        "user_id": "u-f031",
        "user_message": "今天想吃辣的",
        "user_preferences": _prefs(),
    }
    state.update(cast(Any, overrides))
    return state


def _fake_weather() -> dict[str, Any]:
    return {
        "location": "116.43,39.91",
        "province": "北京市",
        "city": "北京市",
        "adcode": "110000",
        "temperature_celsius": 22.0,
        "condition": "sunny",
        "humidity_percent": 50,
        "wind_direction": "南",
        "wind_level": 2,
        "precipitation_probability": 0.05,
        "forecast_3h": [],
        "fetched_at": "2026-09-07T12:00:00Z",
    }


# ---------------------------------------------------------------------------
# _resolve_location
# ---------------------------------------------------------------------------


class TestResolveLocation:
    def test_override_takes_priority(self) -> None:
        state = _state(location_override="116.50,39.90", user_preferences=_prefs(default_location="上海"))
        assert _resolve_location(state).startswith("116.50")

    def test_prefs_default_when_no_override(self) -> None:
        state = _state(user_preferences=_prefs(default_location="上海陆家嘴"))
        assert "上海" in _resolve_location(state)

    def test_fallback_to_guomao(self) -> None:
        state = _state(user_preferences=_prefs(default_location=None))
        assert _resolve_location(state).startswith("116.433840")  # 国贸

    def test_empty_override_falls_through(self) -> None:
        state = _state(
            location_override="   ",
            user_preferences=_prefs(default_location="上海"),
        )
        assert "上海" in _resolve_location(state)


# ---------------------------------------------------------------------------
# node_fetch_weather — happy path
# ---------------------------------------------------------------------------


class TestFetchWeatherHappyPath:
    async def test_returns_weather_on_success(self) -> None:
        with patch(
            "app.agents.nodes.fetch_weather.amap_get_weather",
            return_value=_fake_weather(),
        ) as mock:
            out = await node_fetch_weather(_state())
        assert "weather" in out
        assert out["weather"]["temperature_celsius"] == 22.0  # type: ignore[index]
        assert out["weather"]["condition"] == "sunny"  # type: ignore[index]
        # 默认走 prefs.default_location="国贸"
        mock.assert_called_once()
        call_kwargs = mock.call_args.kwargs
        assert call_kwargs["location"] == "国贸"
        assert call_kwargs["extensions"] == "base"

    async def test_uses_override_location(self) -> None:
        with patch(
            "app.agents.nodes.fetch_weather.amap_get_weather",
            return_value=_fake_weather(),
        ) as mock:
            await node_fetch_weather(_state(location_override="116.50,39.90"))
        assert mock.call_args.kwargs["location"].startswith("116.50")


# ---------------------------------------------------------------------------
# node_fetch_weather — 失败降级 (F031 §5 + F004 §3.4)
# ---------------------------------------------------------------------------


class TestFetchWeatherFailure:
    async def test_amap_location_invalid_returns_none_with_error(self) -> None:
        with patch(
            "app.agents.nodes.fetch_weather.amap_get_weather",
            side_effect=AmapLocationInvalidError(
                "high地无法解析",
                details={"location": "???"},
            ),
        ):
            out = await node_fetch_weather(_state())
        assert out["weather"] is None
        assert out["errors"]  # type: ignore[arg-type]
        last_err = out["errors"][-1]  # type: ignore[index]
        assert last_err["code"] == "AMAP_LOCATION_INVALID"
        assert last_err["node"] == "fetch_weather"

    async def test_amap_network_error_returns_none_with_error(self) -> None:
        with patch(
            "app.agents.nodes.fetch_weather.amap_get_weather",
            side_effect=AmapNetworkError("网络超时", details={}),
        ):
            out = await node_fetch_weather(_state())
        assert out["weather"] is None
        assert any(e["code"] == "AMAP_NETWORK_ERROR" for e in out["errors"])  # type: ignore[union-attr]

    async def test_unexpected_exception_returns_none(self) -> None:
        with patch(
            "app.agents.nodes.fetch_weather.amap_get_weather",
            side_effect=RuntimeError("boom"),
        ):
            out = await node_fetch_weather(_state())
        assert out["weather"] is None
        assert any(e["code"] == "FETCH_WEATHER_UNEXPECTED" for e in out["errors"])  # type: ignore[union-attr]

    async def test_existing_errors_are_preserved(self) -> None:
        """降级时不应该覆盖已有的 errors 列表 (cuisine_fanout 等 Node 已写)."""
        prior = [{"node": "cuisine_fanout", "code": "X", "message": "y"}]
        with patch(
            "app.agents.nodes.fetch_weather.amap_get_weather",
            side_effect=AmapNetworkError("net", details={}),
        ):
            state = _state(errors=prior)
            out = await node_fetch_weather(state)
        # 原有 errors + 新 errors
        nodes = [e["node"] for e in out["errors"]]  # type: ignore[union-attr]
        assert "cuisine_fanout" in nodes
        assert "fetch_weather" in nodes
