"""F030 — `search_restaurants` Node 单测.

`_resolve_location` 必须返回 `lng,lat` 坐标 (高德 `place/around` 要求),
否则真实调用会触发 `infocode=20000 INVALID_PARAMS`. 这里只断言 Node 的
location 解析逻辑; 真实高德 HTTP 调用由 `test_amap_restaurant.py` 覆盖.

F001 §3.5 + F030 §6.1: 中文地标 / 城市名 fallback 到默认坐标 (lng,lat)
并 WARN log (silent fallback 是 2026-09-07 bug 的根源).
F051 升级后 (2026-09-08): adcode (6 位) 不再 fallback, 由 wrapper
(`amap_search_restaurants`) 负责 translate 成 `lng,lat`. StructuredAddress
dict 走 `district_adcode` (→ city_adcode) 路径.
F051 §6.4 再次升级 (2026-09-09): StructuredAddress 同时携带
`longitude`/`latitude` (regeo 一次性捕获的原始坐标) 时, **优先用经纬度**,
避免 district_adcode → 区中心点导致「整个区只搜到 1.5km 内 POI」的精度 bug.
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

    def test_adcode_override_passes_through(self) -> None:
        """F051 §6.3: adcode 不再 fallback, 透传给 wrapper translate 成 lng,lat."""
        loc = _resolve_location(_state(location_override="110000"))
        assert loc == "110000"

    def test_city_name_override_falls_back_to_coord(self) -> None:
        """F001 §3.5 + F030 §6.1: 中文城市名不能直接喂给 place/around → fallback."""
        loc = _resolve_location(_state(location_override="北京"))
        assert loc.startswith("116.433840")

    def test_adcode_prefs_passes_through(self) -> None:
        """F051 升级后: prefs 存 adcode (老字符串格式) → 透传给 wrapper translate."""
        loc = _resolve_location(_state(user_preferences=_prefs(default_location="110000")))
        assert loc == "110000"

    def test_structured_prefs_extracts_district_adcode(self) -> None:
        """F051 §3.1: StructuredAddress dict → 优先 district_adcode."""
        loc = _resolve_location(
            _state(
                user_preferences={
                    "default_location": {
                        "province": "上海市",
                        "province_adcode": "310000",
                        "city": "上海市",
                        "city_adcode": "310100",
                        "district": "静安区",
                        "district_adcode": "310106",
                    }
                }
            )
        )
        assert loc == "310106"

    def test_structured_prefs_falls_back_to_city_adcode(self) -> None:
        """F051 §3.1: 缺 district 时用 city_adcode (直辖市场景)."""
        loc = _resolve_location(
            _state(
                user_preferences={
                    "default_location": {
                        "province": "上海市",
                        "province_adcode": "310000",
                        "city": "上海市",
                        "city_adcode": "310100",
                    }
                }
            )
        )
        assert loc == "310100"

    # ---- F051 §6.4: regeo 原始 lng/lat 优先于 district_adcode ----

    def test_structured_prefs_prefers_lng_lat_over_district_adcode(self) -> None:
        """F051 §6.4 精度修复: StructuredAddress 同时有 lng/lat + district_adcode
        时, **直接用经纬度** 当 place/around 锚点, 不走 district 中心点 fallback.

        不再被 district_adcode "抢走", 避免「整个区只搜到 1.5km 内 POI」的 bug.
        """
        loc = _resolve_location(
            _state(
                user_preferences={
                    "default_location": {
                        "province": "浙江省",
                        "province_adcode": "330000",
                        "city": "杭州市",
                        "city_adcode": "330100",
                        "district": "钱塘区",
                        "district_adcode": "330114",
                        "longitude": 121.450000,  # 河庄街道某小区
                        "latitude": 30.230000,
                    }
                }
            )
        )
        # 必须拼成 "lng,lat" 形式给 place/around, 且不是 district_adcode
        assert loc == "121.45,30.23"
        assert _is_coord(loc)

    def test_structured_prefs_coord_only_no_district_adcode(self) -> None:
        """用户只选到城市级 + 一次性定位 → 没 district_adcode, 但有 lng/lat → 仍能用."""
        loc = _resolve_location(
            _state(
                user_preferences={
                    "default_location": {
                        "province": "上海市",
                        "province_adcode": "310000",
                        "city": "上海市",
                        "city_adcode": "310100",
                        "longitude": 121.473701,
                        "latitude": 31.230416,
                    }
                }
            )
        )
        assert loc == "121.473701,31.230416"

    def test_structured_prefs_partial_coord_ignored(self) -> None:
        """只有 longitude 没有 latitude → 走 adcode 路径 (避免单独坐标定位的伪精度)."""
        loc = _resolve_location(
            _state(
                user_preferences={
                    "default_location": {
                        "province": "浙江省",
                        "province_adcode": "330000",
                        "city": "杭州市",
                        "city_adcode": "330100",
                        "district": "钱塘区",
                        "district_adcode": "330114",
                        "longitude": 121.45,  # 没有 latitude
                    }
                }
            )
        )
        # 退回 district_adcode 路径
        assert loc == "330114"

    def test_structured_prefs_non_numeric_coord_ignored(self) -> None:
        """lng/lat 不是数字 → 忽略, 走 adcode 路径 (避免 schema 校验失效时崩)."""
        loc = _resolve_location(
            _state(
                user_preferences={
                    "default_location": {
                        "province": "浙江省",
                        "province_adcode": "330000",
                        "city": "杭州市",
                        "city_adcode": "330100",
                        "district": "钱塘区",
                        "district_adcode": "330114",
                        "longitude": "121.45",  # 字符串, 应该忽略
                        "latitude": "30.23",
                    }
                }
            )
        )
        assert loc == "330114"

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
            "location_override 非坐标/非adcode" in rec.message
            and "override=国贸" in rec.message
            for rec in caplog.records
        )

    def test_adcode_override_does_not_log_warning(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """F051 升级后: adcode 透传给 wrapper, 不再 fallback, 无 WARN log."""
        with caplog.at_level("WARNING", logger="app.agents.nodes.search_restaurants"):
            _resolve_location(_state(location_override="110000"))
        assert not any("fallback" in rec.message for rec in caplog.records)

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
            "prefs.default_location (老字符串)" in rec.message
            and "location=国贸" in rec.message
            for rec in caplog.records
        )

    def test_valid_coord_does_not_log_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level("WARNING", logger="app.agents.nodes.search_restaurants"):
            _resolve_location(_state(location_override="116.50,39.90"))
        assert not any("fallback" in rec.message for rec in caplog.records)