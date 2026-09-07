"""F030 — `search_restaurants` Node 单测.

`_resolve_location` 必须返回 `lng,lat` 坐标 (高德 `place/around` 要求),
否则真实调用会触发 `infocode=20000 INVALID_PARAMS`. 这里只断言 Node 的
location 解析逻辑; 真实高德 HTTP 调用由 `test_amap_restaurant.py` 覆盖.

F001 §3.5 + F030 §6.1: adcode / 城市名 / 中文地标都视为非法, 必须 fallback
到默认坐标并 WARN log (silent fallback 是 2026-09-07 bug 的根源).
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, cast

import pytest
from app.agents.nodes.search_restaurants import _is_coord, _resolve_location
from app.agents.state import AgentState, UserPreferencesDict
from app.core.constants import CUISINE_IDS


def _prefs(**overrides: Any) -> UserPreferencesDict:
    prefs: UserPreferencesDict = {
        "user_id": "u",
        "cuisine_weights": dict.fromkeys(CUISINE_IDS, 0.5),
        "allergies": [],
        "spice_tolerance": 1,
        "temperature_preference": "room",
        "default_location": "国贸",  # 默认是中文地名, 真实调用会触发 INVALID_PARAMS
        "budget_lunch_min": Decimal("30.00"),
        "budget_lunch_max": Decimal("80.00"),
    }
    prefs.update(cast(Any, overrides))
    return prefs


def _state(**overrides: Any) -> AgentState:
    state: AgentState = {
        "user_id": "u",
        "user_message": "x",
        "user_preferences": _prefs(),
    }
    state.update(cast(Any, overrides))
    return state


class TestIsCoord:
    def test_standard_coord(self) -> None:
        assert _is_coord("116.433840,39.908740") is True

    def test_negative_coords(self) -> None:
        assert _is_coord("-122.4,37.7") is True

    def test_chinese_text_rejected(self) -> None:
        # 中文地名会让高德 place/around 返回 20000 INVALID_PARAMS
        assert _is_coord("国贸") is False
        assert _is_coord("上海陆家嘴") is False

    def test_empty_or_garbage_rejected(self) -> None:
        assert _is_coord("") is False
        assert _is_coord(",") is False
        assert _is_coord("abc,def") is False
        assert _is_coord("116.43,abc") is False


class TestResolveLocation:
    def test_chinese_default_falls_back_to_guomao_coord(self) -> None:
        """F030 bug fix (2026-09-07): prefs.default_location="国贸" 也不能直接
        传给 place/around, 必须回落到国贸坐标."""
        loc = _resolve_location(_state())
        assert loc.startswith("116.433840")
        # 反向验证: 必须是合法坐标
        assert _is_coord(loc)

    def test_override_coord_kept(self) -> None:
        loc = _resolve_location(_state(location_override="116.50,39.90"))
        assert loc == "116.50,39.90"

    def test_chinese_override_falls_back_to_guomao(self) -> None:
        """override 是中文也要回落 (避免 INVALID_PARAMS)."""
        loc = _resolve_location(_state(location_override="上海陆家嘴"))
        assert loc.startswith("116.433840")

    def test_adcode_override_falls_back_to_coord(self) -> None:
        """F001 §3.5 + F030 §6.1: adcode 不能直接喂给 place/around (要 lng,lat),
        Node 层统一 fallback 到默认坐标."""
        loc = _resolve_location(_state(location_override="110000"))
        assert loc.startswith("116.433840")

    def test_city_name_override_falls_back_to_coord(self) -> None:
        """F001 §3.5 + F030 §6.1: 城市名不能直接喂给 place/around → fallback."""
        loc = _resolve_location(_state(location_override="北京"))
        assert loc.startswith("116.433840")

    def test_adcode_prefs_falls_back_to_coord(self) -> None:
        """F001 §3.5: prefs 存 adcode (weather 友好) → restaurant 也必须 fallback."""
        loc = _resolve_location(_state(user_preferences=_prefs(default_location="110000")))
        assert loc.startswith("116.433840")

    def test_prefs_coord_kept(self) -> None:
        loc = _resolve_location(_state(user_preferences=_prefs(default_location="121.50,31.23")))
        assert loc == "121.50,31.23"

    def test_empty_prefs_default_falls_back(self) -> None:
        loc = _resolve_location(_state(user_preferences=_prefs(default_location=None)))
        assert loc.startswith("116.433840")

    def test_empty_override_uses_prefs(self) -> None:
        """override 为空 → 用 prefs 的坐标 (若有)."""
        loc = _resolve_location(
            _state(location_override="", user_preferences=_prefs(default_location="121.50,31.23"))
        )
        assert loc == "121.50,31.23"


# ---------------------------------------------------------------------------
# F001 §3.5: 兜底必须 WARN log (silent fallback 是 2026-09-07 bug 的根源)
# ---------------------------------------------------------------------------


class TestWarnLogging:
    def test_chinese_override_logs_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level("WARNING", logger="app.agents.nodes.search_restaurants"):
            _resolve_location(_state(location_override="国贸"))
        assert any(
            "location_override 非坐标" in rec.message and "override=国贸" in rec.message
            for rec in caplog.records
        )

    def test_adcode_override_logs_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level("WARNING", logger="app.agents.nodes.search_restaurants"):
            _resolve_location(_state(location_override="110000"))
        assert any(
            "location_override 非坐标" in rec.message and "override=110000" in rec.message
            for rec in caplog.records
        )

    def test_city_name_override_logs_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level("WARNING", logger="app.agents.nodes.search_restaurants"):
            _resolve_location(_state(location_override="北京"))
        assert any(
            "location_override 非坐标" in rec.message and "override=北京" in rec.message
            for rec in caplog.records
        )

    def test_chinese_prefs_logs_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level("WARNING", logger="app.agents.nodes.search_restaurants"):
            _resolve_location(_state(user_preferences=_prefs(default_location="国贸")))
        assert any(
            "prefs.default_location 非坐标" in rec.message and "location=国贸" in rec.message
            for rec in caplog.records
        )

    def test_valid_coord_does_not_log_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level("WARNING", logger="app.agents.nodes.search_restaurants"):
            _resolve_location(_state(location_override="116.50,39.90"))
        assert not any("fallback" in rec.message for rec in caplog.records)