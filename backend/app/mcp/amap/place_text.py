"""F051 — 高德 MCP POI 关键字搜索 Tool (复用 F030 协议, types 参数化).

设计要点 (per spec/features/F051-structured-address.md §5.3):

- 封装 `GET /v3/place/text` 按关键字搜索 POI (街道/商圈/小区/楼宇/餐厅)
- 输入: `keywords` + `city` (adcode 或城市名) + `types` (高德 POI 分类码或中文类名)
- 输出: `PlaceSearchResult` (TypedDict), 含 poi_id / name / address / 经纬度 / 类型
- 错误码沿用 F031 §5: `AMAP_INVALID_KEY` / `AMAP_QUOTA_EXCEEDED` /
  `AMAP_NETWORK_ERROR` / `AMAP_LOCATION_INVALID` (city 解析失败)

F051 §5.3 vs F030 §3.3:
- F030 用 `place/around` (餐厅周边搜索, location 锚点 + 半径) — 本模块**不替代**
- F051 用 `place/text` (POI 关键字搜索, 任意 city 范围) — 本模块**新加**
- 二者通过 `types` 参数共享: F030 `_AMAP_FOOD_CATEGORY = "050000"` 缺省,
  F051 允许调用方传 `"商圈"` / `"商务住宅|地名地址信息"` 等

不使用 LangChain `@tool` 装饰器 — 由前端 `usePlaceSearch` Hook 直接 await.
"""
from __future__ import annotations

import logging
from typing_extensions import TypedDict

from app.mcp.amap.client import AmapClient

logger = logging.getLogger(__name__)

# 高德 `/v3/place/text` endpoint
_PLACE_TEXT_PATH = "/v3/place/text"

# 入参上限 (防止误用拖慢下游)
_MAX_KEYWORDS_LENGTH = 64
_MAX_TYPES_LENGTH = 64
_MAX_CITY_LENGTH = 64
_MIN_OFFSET = 1
_MAX_OFFSET = 25
_DEFAULT_OFFSET = 10

# F030 §3.3 缺省 types —— 向后兼容
DEFAULT_TYPES = "050000"  # 餐饮服务大类


# ----- 类型契约 (F051 §5.3) -----


class PoiCandidate(TypedDict):
    """高德 `place/text` 返回的单个 POI 候选.

    与 F030 `Restaurant` 重叠但更轻量 —— 只保留选址场景需要的字段.
    """

    poi_id: str
    name: str
    address: str
    type: str  # 高德原始 type 字符串 (例: "餐饮服务;中餐厅;四川菜")
    location: tuple[float, float]  # (longitude, latitude)


class PlaceSearchResult(TypedDict):
    """F051 §5.3 输出 envelope.

    `count` 是高德原始返回条数 (≤ offset); `pois` 是按类型 / 距离等规则
    过滤后的列表 (本模块暂不过滤, 直接投影高德返回).
    """

    pois: list[PoiCandidate]
    count: int


# ----- 主入口 -----


async def amap_search_places(
    *,
    keywords: str,
    city: str | None = None,
    types: str | None = None,
    offset: int = _DEFAULT_OFFSET,
    client: AmapClient | None = None,
) -> PlaceSearchResult:
    """F051 主入口 —— 调用高德『POI 关键字搜索』API.

    Args:
        keywords: 搜索关键字 (例: "南京西路", "静安嘉里中心", "海底捞").
                  长度 ≤ 64.
        city: 限定城市 (adcode 或城市名, 例: "310100" / "上海市").
              不传则全国范围搜索. 长度 ≤ 64.
        types: POI 分类过滤 (高德分类码或中文类名).
               - 不传 → DEFAULT_TYPES ("050000" 餐饮服务大类, 向后兼容 F030)
               - "商圈" → 街道/商圈候选 (F051 §4.2)
               - "商务住宅|地名地址信息" → 小区/楼宇候选 (F051 §4.2)
               长度 ≤ 64.
        offset: 返回条数上限 (1-25, 默认 10).
        client: 已构造的 `AmapClient`. 不传则用工厂.

    Returns:
        `PlaceSearchResult` — `pois` 字段按 `offset` 截断; `count` 是高德原始条数.

    Raises:
        ValueError: 入参非法 (keywords 为空 / 越界)
        AmapInvalidKeyError: API key 无效或未配置
        AmapQuotaExceededError: 高德配额耗尽
        AmapNetworkError: 网络/超时重试耗尽
        AmapLocationInvalidError: city 解析失败 (高德返回 infocode 20001/20002)
    """
    # ---- 入参校验 ----
    if not isinstance(keywords, str) or not keywords.strip():
        raise ValueError("keywords 必须是非空字符串")
    if len(keywords) > _MAX_KEYWORDS_LENGTH:
        raise ValueError(
            f"keywords 长度必须 <= {_MAX_KEYWORDS_LENGTH}, 实际={len(keywords)}"
        )
    if city is not None and len(city) > _MAX_CITY_LENGTH:
        raise ValueError(
            f"city 长度必须 <= {_MAX_CITY_LENGTH}, 实际={len(city)}"
        )
    if types is not None and len(types) > _MAX_TYPES_LENGTH:
        raise ValueError(
            f"types 长度必须 <= {_MAX_TYPES_LENGTH}, 实际={len(types)}"
        )
    if not (_MIN_OFFSET <= offset <= _MAX_OFFSET):
        raise ValueError(
            f"offset 必须在 [{_MIN_OFFSET}, {_MAX_OFFSET}], 实际={offset}"
        )

    # ---- HTTP 调用 ----
    if client is None:
        from app.mcp.amap.client import get_amap_client

        client = get_amap_client()

    params: dict[str, str] = {
        "keywords": keywords.strip(),
        "offset": str(offset),
        "page": "1",
        "extensions": "base",
        "types": types if types is not None else DEFAULT_TYPES,
    }
    if city is not None and city.strip():
        params["city"] = city.strip()
        # city 限定时同时设置 citylimit=true 强制只在 city 范围内匹配
        params["citylimit"] = "true"

    payload = await client.get_json(_PLACE_TEXT_PATH, params=params)

    raw_pois = payload.get("pois") or []
    if not isinstance(raw_pois, list):
        logger.warning(
            "Amap /v3/place/text 返回非 list pois, payload=%s", payload
        )
        raw_pois = []

    raw_count = len(raw_pois)

    # ---- 解析 + 截断 ----
    pois: list[PoiCandidate] = []
    for item in raw_pois:
        if not isinstance(item, dict):
            continue
        candidate = _parse_poi(item)
        if candidate is not None:
            pois.append(candidate)
        if len(pois) >= offset:
            break

    return {"pois": pois, "count": raw_count}


# ----- 内部辅助 -----


def _parse_poi(item: dict[str, object]) -> PoiCandidate | None:
    """从高德原始 POI dict 抽出强类型字段; 缺关键字段则丢弃."""
    poi_id = item.get("id")
    name = item.get("name")
    if not isinstance(poi_id, str) or not isinstance(name, str):
        return None

    address = item.get("address") or ""
    poi_type = item.get("type") or ""

    location_str = item.get("location")
    longitude, latitude = _parse_location(location_str)
    if longitude is None or latitude is None:
        return None

    return {
        "poi_id": poi_id,
        "name": name,
        "address": address if isinstance(address, str) else "",
        "type": poi_type if isinstance(poi_type, str) else "",
        "location": (longitude, latitude),
    }


def _parse_location(raw: object) -> tuple[float | None, float | None]:
    """高德 location 格式: 'lng,lat'. 解析失败返回 (None, None)."""
    if not isinstance(raw, str) or not raw.strip():
        return (None, None)
    parts = raw.split(",")
    if len(parts) != 2:
        return (None, None)
    try:
        return (float(parts[0]), float(parts[1]))
    except (TypeError, ValueError):
        return (None, None)


__all__ = [
    "amap_search_places",
    "PoiCandidate",
    "PlaceSearchResult",
    "DEFAULT_TYPES",
]
