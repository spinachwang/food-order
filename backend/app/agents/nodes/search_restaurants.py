"""`search_restaurants` Node — F030 / F004 §3.2 row 4.

按 `state["selected_cuisines"]` 与 `state["cuisine_results"][cid]["keywords"]`
并行调用 `amap_search_restaurants` (F030 §3.1), 把结果聚合到
`restaurant_lists[cid]`. 单个 cuisine 失败 (AmapError) → 该 cuisine_id
列表为空 + 追加 error entry (F004 §3.4: "search_restaurants 异常 → 该
cuisine_id 餐厅列表为空, summary 跳过"). 整个 Node 不会抛错给上层.

输入位置: `state["location_override"]` (API 显式传) 优先, 否则用
`state["user_preferences"]["default_location"]`. 位置格式约束见 F001 §3.5
+ F030 §6.1: 本 Node 调用 `place/around` 仅收 `lng,lat` 坐标, 收到 adcode /
城市名 / 中文地标时统一 fallback 到国贸坐标并 WARN log (防止 silent fallback
再次掩盖 bug).

精度优先级 (F051 §6.4 — 修「只到区级」bug):
1. `default_location["longitude"]` + `["latitude"]` — geolocation 一次性捕获的
   原始坐标, 是用户真正的位置, 直接当 `place/around` 的 location.
2. `default_location["district_adcode"]` (→ city_adcode) — 区级中心点, 当
   上一步无坐标时 (e.g. 老用户 / 手动选到城市级).
3. `_DEFAULT_LOCATION` (国贸) — 兜底, 配 WARN log 含 user_id + 原始值.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, cast

from app.agents.state import AgentState
from app.core.exceptions import AmapError
from app.core.request_id import get_request_id
from app.mcp.amap.restaurant import amap_search_restaurants

logger = logging.getLogger(__name__)

# 注: F001 §3.5 兜底值在城市级是 `"110000"` (adcode). 本 Node 调
# `place/around` 必须收 `lng,lat`, 所以内部用坐标形式; fetch_weather.py 用
# adcode 形式. 两者都指向北京国贸, 语义一致.
_DEFAULT_LOCATION = "116.433840,39.908740"  # 国贸 (与 dev_route.py 习惯一致)
_DEFAULT_LOCATION_LABEL = "国贸"

# 6 位数字 adcode (例如 "110000")
_ADCODE_PATTERN = re.compile(r"^\d{6}$")


def _is_coord(value: str) -> bool:
    """是否 `lng,lat` 数字坐标 (例如 `116.43,39.91`). 高德 `place/around`
    必须传坐标, 其他格式 (adcode / 城市名 / 中文地标) 会触发
    `infocode=20000 INVALID_PARAMS`."""
    if "," not in value:
        return False
    left, _, right = value.partition(",")
    try:
        float(left.strip())
        float(right.strip())
    except ValueError:
        return False
    return True


def _resolve_structured_adcode(
    default_location: dict[str, Any], *, prefer: str = "district"
) -> str | None:
    """从 F051 StructuredAddress dict 抽出区/市级 adcode.

    `prefer="district"`: 优先 district_adcode (餐厅搜索的语义锚点更精确),
    缺失时 fallback 到 city_adcode.
    """
    if prefer == "district":
        adcode = default_location.get("district_adcode") or default_location.get(
            "city_adcode"
        )
    else:
        adcode = default_location.get("city_adcode") or default_location.get(
            "district_adcode"
        )
    if isinstance(adcode, str) and _ADCODE_PATTERN.match(adcode.strip()):
        return adcode.strip()
    return None


def _resolve_structured_coord(
    default_location: dict[str, Any],
) -> tuple[float, float] | None:
    """从 F051 StructuredAddress dict 抽出 (lng, lat) — 仅当两者都合法时返回.

    regeo 一次性写入的原始坐标是用户精确位置 (e.g. 河庄街道某小区), 用于
    place/around 时直接当 location, 不必再走 district_adcode → 区中心点
    fallback (后者精度损失严重, 1.5km 半径在大区里几乎搜不到).

    Returns:
        `(longitude, latitude)` 或 None (缺失 / 类型不对). 校验后的值必
        在 [-180, 180] / [-90, 90] — schema 已强校验, 此处只需类型 narrow.
    """
    lng = default_location.get("longitude")
    lat = default_location.get("latitude")
    if not isinstance(lng, (int, float)) or isinstance(lng, bool):
        return None
    if not isinstance(lat, (int, float)) or isinstance(lat, bool):
        return None
    return float(lng), float(lat)


def _resolve_location(state: AgentState) -> str:
    """解析锚点: 显式 override > 用户偏好高精度 lng/lat > district_adcode > 国贸坐标兜底.

    F030 §6.1: 仅放行 `lng,lat` 坐标; adcode / 城市名 / 中文地标 fallback
    到 `_DEFAULT_LOCATION` 并 WARN log (含 `user_id` 与原始值, 便于追溯
    silent fallback).

    F051 §6.4 升级: 优先级
      1. `state["location_override"]` (API 显式传 — 已是 lng,lat 或 adcode)
      2. `default_location["longitude"]` + `["latitude"]` (regeo 原始坐标)
      3. `default_location["district_adcode"]` (→ city_adcode)
      4. `_DEFAULT_LOCATION` (国贸) + WARN log
    wrapper 负责 translate adcode → "lng,lat"; 翻译失败时 fallback 到
    国贸坐标 + WARN log.
    """
    rid = get_request_id() or "-"
    user_id = str(state.get("user_id") or "-")

    override = state.get("location_override")
    if isinstance(override, str) and override.strip():
        v = override.strip()
        if _is_coord(v):
            return v
        # override 也可能是 adcode — 透传给 wrapper, 由其 translate
        if _ADCODE_PATTERN.match(v):
            return v
        logger.warning(
            "search_restaurants location_override 非坐标/非adcode, fallback "
            "rid=%s user=%s override=%s",
            rid, user_id, v,
        )
    prefs = state.get("user_preferences")
    if prefs is not None:
        default_loc = prefs.get("default_location")
        if isinstance(default_loc, dict):
            # 优先级 1: regeo 一次性捕获的原始坐标 (F051 §6.4 修精度 bug)
            coord = _resolve_structured_coord(default_loc)
            if coord is not None:
                lng, lat = coord
                return f"{lng},{lat}"
            # 优先级 2: district_adcode → city_adcode fallback
            adcode = _resolve_structured_adcode(default_loc, prefer="district")
            if adcode is not None:
                return adcode
            logger.warning(
                "search_restaurants prefs.default_location 是 dict 但 "
                "lng/lat 与 adcode 都不可用, fallback "
                "rid=%s user=%s location=%s",
                rid, user_id, default_loc,
            )
        elif isinstance(default_loc, str) and default_loc.strip():
            v = default_loc.strip()
            if _is_coord(v) or _ADCODE_PATTERN.match(v):
                return v
            logger.warning(
                "search_restaurants prefs.default_location (老字符串) 非坐标/非adcode, "
                "fallback rid=%s user=%s location=%s",
                rid, user_id, v,
            )
    return _DEFAULT_LOCATION


def _resolve_keywords(cid: str, state: AgentState) -> list[str]:
    """从 cuisine_results[cid] 取关键词; 缺失或空 → ['餐厅'] 兜底."""
    results = state.get("cuisine_results") or {}
    raw = results.get(cid) or {}
    keywords = raw.get("keywords") if isinstance(raw, dict) else None
    if not isinstance(keywords, list) or not keywords:
        return [_DEFAULT_LOCATION_LABEL]
    return [str(k) for k in keywords if isinstance(k, str) and k.strip()][:5]


async def _search_one(
    cid: str,
    keywords: list[str],
    location: str,
) -> tuple[str, list[dict[str, object]], dict[str, str] | None]:
    """调一次高德; 返回 (cuisine_id, restaurants, error_or_None)."""
    try:
        result = await amap_search_restaurants(
            keywords=keywords,
            location=location,
            radius_meters=1500,
            min_rating=3.5,
            max_results=10,
        )
    except AmapError as exc:
        # F004 §3.4: 单 cuisine 失败 → 该 cuisine_id 列表为空 + error entry
        logger.warning("F030 search failed for cuisine=%s: %s", cid, exc)
        return (
            cid,
            [],
            {
                "node": "search_restaurants",
                "code": exc.code,
                "message": exc.message,
                "cuisine_id": cid,
            },
        )
    except (ValueError, RuntimeError) as exc:
        # 入参非法 / 其他未预期错误 — 同样兜底
        logger.exception("F030 unexpected error for cuisine=%s", cid)
        return (
            cid,
            [],
            {
                "node": "search_restaurants",
                "code": "AMAP_UNEXPECTED",
                "message": str(exc),
                "cuisine_id": cid,
            },
        )
    else:
        return cid, cast(list[dict[str, object]], result["restaurants"]), None


async def node_search_restaurants(state: AgentState) -> dict[str, object]:
    """F030 主 Node —— 并行调高德, 聚合到 `restaurant_lists`.

    始终返回 `restaurant_lists` (dict), 即使全部失败也是空 dict.
    若有错误, 同时返回 `errors` 列表 (F004 §3.4).
    """
    selected = list(state.get("selected_cuisines") or [])
    cuisine_results = state.get("cuisine_results") or {}
    # 兼容: 选了但 cuisine_results 还没填完的边界
    cuisine_ids = list({*selected, *cast(list[str], list(cuisine_results.keys()))})

    if not cuisine_ids:
        return {"restaurant_lists": {}, "errors": []}

    location = _resolve_location(state)

    # 并行触发 — `asyncio.gather` 同时挂多个高德请求, 总耗时 ~max(各次)
    tasks = [_search_one(cid, _resolve_keywords(cid, state), location) for cid in cuisine_ids]
    results = await asyncio.gather(*tasks, return_exceptions=False)

    restaurant_lists: dict[str, list[dict[str, object]]] = {}
    errors: list[dict[str, str]] = []
    for cid, restaurants, err in results:
        restaurant_lists[cid] = restaurants
        if err is not None:
            errors.append(err)

    update: dict[str, object] = {"restaurant_lists": restaurant_lists}
    if errors:
        # 追加而非覆盖 — 其它 Node 也可能往 errors 写
        existing = list(state.get("errors") or [])
        update["errors"] = [*existing, *errors]
    return update


__all__ = ["node_search_restaurants"]
