"""F030 — 高德 MCP 周边搜索（餐厅）Tool.

设计要点 (per spec/features/F030-amap-restaurant-search.md):

- 输入: 关键词 + 锚点 + 半径 + 最低评分 + 上限条数
- 输出: 结构化餐厅列表 (TypedDict), 含 POI ID / 名称 / 距离 / 评分 / 价格
- 排序: `score = (distance / max_distance) * w + (1 - rating/5) * (1-w)`, 升序
- 过滤: 距离 > 3000m 剔除; 评分 < min_rating 剔除
- 错误: 通过 `AmapClient` 抛 `AmapError` 子类
- 边缘: `count=0` → `restaurants=[]`, `partial=True`, 不抛错

不使用 LangChain `@tool` 装饰器 (项目不依赖 LangChain Tools) — 函数
签名遵循 LangChain Tool 风格: typed params + 单个 typed return, 由
LangGraph Node (`search_restaurants.py`) 直接 await 调用.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from typing_extensions import TypedDict

from app.mcp.amap.client import AmapClient

logger = logging.getLogger(__name__)

# ---- 业务常量 (从 spec 派生; 命名常量便于单测复用) ----

# 高德 POI 分类码 —— 050000 = 餐饮服务大类 (https://lbs.amap.com/api/webservice/guide/poi/poi-search)
_AMAP_FOOD_CATEGORY = "050000"
# F030 §2: 距离 > 3km 直接剔除
_MAX_DISTANCE_METERS = 3000
# F030 §2: 排序权重 — 距离 vs 评分 (距离主导)
_DISTANCE_WEIGHT = 0.6
# 入参上限 (防止误用拖慢下游)
_MAX_KEYWORDS = 5
_MIN_KEYWORDS = 1
_MAX_RADIUS_METERS = 5000
_MIN_RADIUS_METERS = 50
_MIN_MAX_RESULTS = 1
_MAX_MAX_RESULTS = 25
# F030 §2: 部分结果阈值 —— 不足 3 家 → partial=true
_PARTIAL_THRESHOLD = 3


# ----- 类型契约 (F030 §3) -----


class Restaurant(TypedDict):
    """高德返回的餐厅信息（最小可用子集）."""

    poi_id: str
    name: str
    address: str
    distance_meters: int
    rating: float | None
    avg_price: Decimal | None
    cuisine_tags: list[str]
    location: tuple[float, float]


class RestaurantSearchResult(TypedDict):
    """F030 §3.2 输出 envelope.

    `partial=True` 表示返回结果不足 `PARTIAL_THRESHOLD`, 调用方
    (summary agent) 据此调整措辞.
    """

    restaurants: list[Restaurant]
    partial: bool
    raw_count: int


# ----- 内部辅助 dataclass -----


@dataclass(frozen=True)
class _PoiRaw:
    """高德原始 POI 字段 (从 dict 抽出 + 强类型转换)."""

    poi_id: str
    name: str
    address: str
    distance_meters: int
    longitude: float
    latitude: float
    rating: float | None
    avg_price: Decimal | None
    cuisine_tags: list[str]


# ----- 主入口 -----


async def amap_search_restaurants(
    *,
    keywords: list[str],
    location: str,
    radius_meters: int = 1500,
    min_rating: float = 3.5,
    max_results: int = 10,
    client: AmapClient | None = None,
) -> RestaurantSearchResult:
    """F030 主入口 —— 调用高德『周边搜索』API.

    Args:
        keywords: 1-5 个关键词 (来自 F003 菜系专家)
        location: 锚点 (地标 / 经纬度字符串 `lng,lat`)
        radius_meters: 搜索半径 (50-5000m, 默认 1500)
        min_rating: 最低评分 (默认 3.5)
        max_results: 上限条数 (1-25, 默认 10)
        client: 已构造的 `AmapClient`. 不传则用工厂 (推荐用于生产,
                测试时可注入带 monkeypatched key 的实例).

    Returns:
        `RestaurantSearchResult`: 已按"距离+评分"加权排序的餐厅列表,
        长度 0-10 (受 `max_results` 与 `MAX_DISTANCE_METERS` 共同约束).
        不足 3 家时 `partial=True`.

    Raises:
        ValueError: 入参非法 (关键词数 / 半径范围 / 上限范围)
        AmapInvalidKeyError: API key 无效或未配置
        AmapQuotaExceededError: 高德配额耗尽
        AmapNetworkError: 网络/超时重试耗尽
    """
    # ---- 入参校验 ----
    _validate_keywords(keywords)
    _validate_radius(radius_meters)
    _validate_max_results(max_results)
    if min_rating < 0 or min_rating > 5:
        raise ValueError(f"min_rating 必须在 [0, 5], 实际={min_rating}")

    # ---- HTTP 调用 ----
    if client is None:
        # 延迟导入: 工厂构造 (含 key 校验)
        from app.mcp.amap.client import get_amap_client

        client = get_amap_client()

    # F051 §6.3: location 可能是 6 位 adcode (StructuredAddress.city_adcode);
    # 高德 place/around 仅收 `lng,lat`, 这里 translate adcode → 中心点经纬度.
    coord_location = await _ensure_coord(location, client=client)

    payload = await client.get_json(
        "/v3/place/around",
        params={
            "keywords": "|".join(keywords),
            "types": _AMAP_FOOD_CATEGORY,
            "location": coord_location,
            "radius": str(radius_meters),
            "offset": str(max_results),
            "page": "1",
            "extensions": "all",  # 返回 biz_ext (含 rating / cost)
        },
    )

    pois_raw = payload.get("pois") or []
    if not isinstance(pois_raw, list):
        # 协议漂移 —— 按 0 结果处理 (F030 §5 AMAP_NO_RESULT 走 partial=true)
        logger.warning("Amap /v3/place/around 返回非 list pois, payload=%s", payload)
        pois_raw = []

    raw_count = len(pois_raw)

    # ---- 解析 + 过滤 ----
    parsed: list[_PoiRaw] = []
    for item in pois_raw:
        if not isinstance(item, dict):
            continue
        poi = _parse_poi(item)
        if poi is None:
            continue
        # F030 §9: 评分缺失不剔除, 仅降权 (排序时把 None 视为中性 3.0)
        if poi.rating is not None and poi.rating < min_rating:
            continue
        # F030 §2: 距离 > 3km 剔除
        if poi.distance_meters > _MAX_DISTANCE_METERS:
            continue
        parsed.append(poi)

    # ---- 排序 ----
    sorted_parsed = _sort_by_score(parsed)

    # ---- 截断 ----
    top = sorted_parsed[:max_results]

    # ---- 投影到 TypedDict ----
    restaurants: list[Restaurant] = [
        {
            "poi_id": p.poi_id,
            "name": p.name,
            "address": p.address,
            "distance_meters": p.distance_meters,
            "rating": p.rating,
            "avg_price": p.avg_price,
            "cuisine_tags": list(p.cuisine_tags),
            "location": (p.longitude, p.latitude),
        }
        for p in top
    ]

    return {
        "restaurants": restaurants,
        "partial": len(restaurants) < _PARTIAL_THRESHOLD,
        "raw_count": raw_count,
    }


# ----- 内部辅助 -----


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


# F051 §6.3: adcode (6 位数字) → 行政区中心点 (lng,lat).
# 高德 `/v3/config/district?keywords=<adcode>&subdistrict=0` 返回该 adcode
# 节点的 `center` 字段; 同一 Node 多次调高德时复用同一份缓存.
_ADCODE_PATTERN = re.compile(r"^\d{6}$")
_adcode_coord_cache: dict[str, str] = {}


async def _ensure_coord(location: str, *, client: AmapClient) -> str:
    """把 F051 StructuredAddress 取出的 adcode (或兼容字符串) 转成
    `place/around` 接受的 `lng,lat` 格式.

    Args:
        location: 来自 Node 的 location — 形如 `116.43,39.91` (坐标),
            `110000` (6 位 adcode), 或其他 (区级地标 / 城市名 — 透传,
            让上层 fallback 或让 Amap 自己报错).
        client: 已构造的 AmapClient (透传给 `amap_get_district`).

    Returns:
        `lng,lat` 格式坐标字符串. 若输入已是坐标 → 透传; adcode → 调
        `/v3/config/district` 取 center; 其他 → 透传.

    Raises:
        AmapDistrictNotFoundError: adcode 在高德查不到 (罕见, 多半是
            错误数据). 上层应捕获并 fallback 到默认坐标.
    """
    if _is_coord(location):
        return location
    if not _ADCODE_PATTERN.match(location.strip()):
        # 区级地标 / 城市名 / 完整地址 — 透传, 让上游 fallback 处理
        return location
    cached = _adcode_coord_cache.get(location)
    if cached is not None:
        return cached
    # 延迟导入避免循环依赖 (district.py 不依赖本模块, 但放在顶部 import
    # 会让 single-tool test 多拉一份 client 模块)
    from app.mcp.amap.district import amap_get_district

    nodes = await amap_get_district(keywords=location, subdistrict=0, client=client)
    if not nodes:
        # 高德协议上 keywords=adcode 应总命中; 命中不到时让上层 fallback
        from app.core.exceptions import AmapDistrictNotFoundError

        raise AmapDistrictNotFoundError(
            f"高德未找到 adcode 对应的行政区划 (adcode={location!r})",
            details={"adcode": location},
        )
    lng, lat = nodes[0]["center"]
    if lng == 0.0 and lat == 0.0:
        # 高德偶尔对港澳 / 边境返回 (0,0) — 不视作合法坐标
        from app.core.exceptions import AmapDistrictNotFoundError

        raise AmapDistrictNotFoundError(
            f"高德未返回 adcode 中心点 (adcode={location!r})",
            details={"adcode": location},
        )
    coord = f"{lng},{lat}"
    _adcode_coord_cache[location] = coord
    return coord


def _validate_keywords(keywords: list[str]) -> None:
    if not isinstance(keywords, list) or not (_MIN_KEYWORDS <= len(keywords) <= _MAX_KEYWORDS):
        raise ValueError(
            f"keywords 必须是 {_MIN_KEYWORDS}-{_MAX_KEYWORDS} 个字符串列表, "
            f"实际={len(keywords) if isinstance(keywords, list) else type(keywords).__name__}"
        )
    if not all(isinstance(k, str) and k.strip() for k in keywords):
        raise ValueError("keywords 每个元素必须是非空字符串")


def _validate_radius(radius_meters: int) -> None:
    if not (_MIN_RADIUS_METERS <= radius_meters <= _MAX_RADIUS_METERS):
        raise ValueError(
            f"radius_meters 必须在 [{_MIN_RADIUS_METERS}, {_MAX_RADIUS_METERS}], "
            f"实际={radius_meters}"
        )


def _validate_max_results(max_results: int) -> None:
    if not (_MIN_MAX_RESULTS <= max_results <= _MAX_MAX_RESULTS):
        raise ValueError(
            f"max_results 必须在 [{_MIN_MAX_RESULTS}, {_MAX_MAX_RESULTS}], 实际={max_results}"
        )


def _parse_poi(item: dict[str, Any]) -> _PoiRaw | None:
    """从高德原始 POI dict 抽出强类型字段; 缺关键字段则丢弃 (返回 None)."""
    poi_id = item.get("id")
    name = item.get("name")
    if not isinstance(poi_id, str) or not isinstance(name, str):
        return None

    location_str = item.get("location")
    longitude, latitude = _parse_location(location_str)
    if longitude is None or latitude is None:
        return None

    distance = _to_int(item.get("distance"), default=0)

    # biz_ext 是嵌套 dict, 缺则为空 dict
    biz_ext = item.get("biz_ext") or {}
    if not isinstance(biz_ext, dict):
        biz_ext = {}

    rating = _to_float(biz_ext.get("rating"))
    cost = _to_decimal(biz_ext.get("cost"))

    # tag 是 list[str]
    tags_raw = item.get("tag") or []
    if isinstance(tags_raw, list):
        cuisine_tags = [str(t) for t in tags_raw if isinstance(t, (str, int))]
    else:
        # 高德偶尔把 tag 返回为逗号分隔字符串
        cuisine_tags = [t.strip() for t in str(tags_raw).split(",") if t.strip()]

    return _PoiRaw(
        poi_id=poi_id,
        name=name,
        address=str(item.get("address", "")),
        distance_meters=distance,
        longitude=longitude,
        latitude=latitude,
        rating=rating,
        avg_price=cost,
        cuisine_tags=cuisine_tags,
    )


def _parse_location(location_str: Any) -> tuple[float | None, float | None]:
    """`"lng,lat"` → `(lng, lat)`. 解析失败返回 `(None, None)`."""
    if not isinstance(location_str, str) or "," not in location_str:
        return None, None
    parts = location_str.split(",", maxsplit=1)
    if len(parts) != 2:
        return None, None
    try:
        return float(parts[0]), float(parts[1])
    except (TypeError, ValueError):
        return None, None


def _to_int(value: Any, *, default: int) -> int:
    if isinstance(value, bool):  # bool 是 int 子类, 显式排除
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return default
    if isinstance(value, float):
        return int(value)
    return default


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    return None


def _to_decimal(value: Any) -> Decimal | None:
    """价格 → `Decimal`. 空字符串 / None / 非数字 → None."""
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    try:
        return Decimal(str(value))
    except (TypeError, ValueError, ArithmeticError):
        return None


def _sort_by_score(pois: list[_PoiRaw]) -> list[_PoiRaw]:
    """按 (距离 / max_distance) + (1 - rating/5) 加权升序.

    F030 §4: 距离主导 (`_DISTANCE_WEIGHT=0.6`). 评分缺失时按中性 3.0
    计算, 不直接剔除 (F030 §9 决议).
    """

    if not pois:
        return []

    max_distance = max(p.distance_meters for p in pois) or 1  # 避免除零

    def score(p: _PoiRaw) -> float:
        distance_norm = p.distance_meters / max_distance
        rating_value = p.rating if p.rating is not None else 3.0
        rating_norm = 1.0 - (rating_value / 5.0)
        return _DISTANCE_WEIGHT * distance_norm + (1 - _DISTANCE_WEIGHT) * rating_norm

    return sorted(pois, key=score)


__all__ = [
    "Restaurant",
    "RestaurantSearchResult",
    "amap_search_restaurants",
]
