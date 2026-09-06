"""`search_restaurants` Node — F030 / F004 §3.2 row 4.

按 `state["selected_cuisines"]` 与 `state["cuisine_results"][cid]["keywords"]`
并行调用 `amap_search_restaurants` (F030 §3.1), 把结果聚合到
`restaurant_lists[cid]`. 单个 cuisine 失败 (AmapError) → 该 cuisine_id
列表为空 + 追加 error entry (F004 §3.4: "search_restaurants 异常 → 该
cuisine_id 餐厅列表为空, summary 跳过"). 整个 Node 不会抛错给上层.

输入位置: `state["location_override"]` (API 显式传) 优先, 否则用
`state["user_preferences"]["default_location"]`. 锚点为空时按"国贸"
兜底, 与现有 dev_route.py 习惯保持一致.
"""

from __future__ import annotations

import asyncio
import logging
from typing import cast

from app.agents.state import AgentState
from app.core.exceptions import AmapError
from app.mcp.amap.restaurant import amap_search_restaurants

logger = logging.getLogger(__name__)

_DEFAULT_LOCATION = "116.433840,39.908740"  # 国贸 (与 dev_route.py 习惯一致)
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
