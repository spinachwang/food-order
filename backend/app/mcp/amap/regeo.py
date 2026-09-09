"""F051 — 高德 MCP 逆地理编码 Tool.

设计要点 (per spec/features/F051-structured-address.md §5.2):

- 封装 `GET /v3/geocode/regeo` 把经纬度转回 adcode + 行政区划文本
- 输入: `location: str` ("lng,lat" 格式)
- 输出: `RegeoInfo` (TypedDict), 字段含 province / city / district /
  adcode / 格式化地址 / 经纬度
- 错误码沿用 F031 §5: `AMAP_INVALID_KEY` / `AMAP_QUOTA_EXCEEDED` /
  `AMAP_NETWORK_ERROR` / `AMAP_LOCATION_INVALID`

不使用 LangChain `@tool` 装饰器 (项目不依赖 LangChain Tools) — 函数
签名遵循 LangChain Tool 风格, 由前端 `useGeolocation` Hook 直接 await.
"""
from __future__ import annotations

import logging
import re

from typing_extensions import TypedDict

from app.mcp.amap.client import AmapClient

logger = logging.getLogger(__name__)

# 高德 `/v3/geocode/regeo` endpoint
_REGEO_PATH = "/v3/geocode/regeo"

# location 参数校验: "lng,lat" 格式, 整数/小数, 经度 [-180, 180], 纬度 [-90, 90]
_LOCATION_PATTERN = re.compile(
    r"^\s*(-?\d{1,3}(?:\.\d+)?)\s*,\s*(-?\d{1,2}(?:\.\d+)?)\s*$"
)


# ----- 类型契约 (F051 §5.2) -----


class RegeoInfo(TypedDict):
    """高德 `/geocode/regeo` 返回结构 (扩展子集).

    必填区段 (AMAP 一定返回):
        `province` / `city` / `district` / `adcode` / `formatted_address` /
        `longitude` / `latitude`.

    细粒度区段 (AMAP 偶发缺失, 全部 str | None):
        - `street` ← `addressComponent.township` (街道名)
        - `community` ← `addressComponent.neighborhood.name` (小区/村名)
        - `door_no` ← `addressComponent.streetNumber.number` (门牌号)
        - `poi_id` ← `pois[0].id` (最近 POI id, 形如 `B0FF...`)
    """

    province: str
    city: str
    district: str
    adcode: str
    formatted_address: str
    longitude: float
    latitude: float
    # ---- 细粒度 (F051 §3.2: 街道 / 小区 / POI id / 门牌号) ----
    street: str | None
    community: str | None
    door_no: str | None
    poi_id: str | None


# POI id 形如 `B0I6KCBRAM` / `B0FFGKABCD1234567890` (高德, 短/长两类都见):
# 8-32 位大写字母+数字 — 兼容 StructuredAddress schema 的 `_POI_ID_PATTERN`.
# 防止 AMAP 偶尔返回不合规 id 把校验炸了 (空字符串 / 含特殊字符).
_POI_ID_PATTERN = re.compile(r"^[A-Z0-9]{8,32}$")

# AMAP POI type 字段用分号分隔的多级分类, 例:
#   "商务住宅;住宅区;住宅小区"
#   "餐饮服务;中餐厅;四川菜"
# community 兜底判定: 命中"商务住宅"/"住宅区"/"地名地址信息"任一即视为小区.
_POI_COMMUNITY_TYPES = ("商务住宅", "住宅区", "地名地址信息")


# ----- 主入口 -----


async def amap_regeo(
    *,
    location: str,
    client: AmapClient | None = None,
) -> RegeoInfo:
    """F051 主入口 —— 调用高德『逆地理编码』API.

    Args:
        location: 经纬度字符串, 格式 "lng,lat" (例: "121.473701,31.230416").
                  经度 ∈ [-180, 180], 纬度 ∈ [-90, 90].
        client: 已构造的 `AmapClient`. 不传则用工厂.

    Returns:
        `RegeoInfo` — 含 province / city / district / adcode / 格式化地址 /
        经纬度.

    Raises:
        ValueError: 入参非法 (location 不是 "lng,lat" 格式或越界)
        AmapInvalidKeyError: API key 无效或未配置
        AmapQuotaExceededError: 高德配额耗尽
        AmapNetworkError: 网络/超时重试耗尽
        AmapLocationInvalidError: 高德无法解析该坐标 (陆地外 / 海域)
    """
    # ---- 入参校验 ----
    match = _LOCATION_PATTERN.match(location)
    if match is None:
        raise ValueError(
            f"location 必须是 'lng,lat' 格式 (例: '121.473701,31.230416'), "
            f"实际={location!r}"
        )
    lng, lat = float(match.group(1)), float(match.group(2))
    if not (-180.0 <= lng <= 180.0):
        raise ValueError(f"location 经度越界 [-180, 180], 实际={lng}")
    if not (-90.0 <= lat <= 90.0):
        raise ValueError(f"location 纬度越界 [-90, 90], 实际={lat}")

    # ---- HTTP 调用 ----
    if client is None:
        from app.mcp.amap.client import get_amap_client

        client = get_amap_client()

    payload = await client.get_json(
        _REGEO_PATH,
        params={
            "location": f"{lng},{lat}",
            # extensions=all 才会返回 `pois[]` (最近 POI) + `neighborhood`
            # (小区/村), 这是细粒度地址字段的来源. base 仅返回地址区段.
            "extensions": "all",
        },
    )

    # 高德 /v3/geocode/regeo 返回 `regeocode` (单数 dict),
    # 不是 `regeocodes` 数组 — 见 amap_regeo_debug.py 实测响应.
    raw_regeocode = payload.get("regeocode")
    if not isinstance(raw_regeocode, dict):
        # 海上 / 边界外 / key 未开通时高德返回 status=1 + regeocode 缺失或非 dict
        from app.core.exceptions import AmapLocationInvalidError

        raise AmapLocationInvalidError(
            "高德 regeo 返回空结果",
            details={
                "location": location,
                "status": payload.get("status"),
                "infocode": payload.get("infocode"),
            },
        )

    return _parse_regeo(raw_regeocode, fallback_lng=lng, fallback_lat=lat)


# ----- 内部辅助 -----


def _parse_regeo(
    item: dict[str, object], *, fallback_lng: float, fallback_lat: float
) -> RegeoInfo:
    """从高德原始 regeo dict 抽出强类型字段; 缺关键字段时填默认值.

    `addressComponent` 是嵌套 dict, 含 province / city / district / adcode;
    字段缺失时填空字符串 / '000000' 占位, 调用方需自行校验 (StructuredAddress
    的正则会拦截 5 位 / 全 0 的非法 adcode).
    """
    component = item.get("addressComponent") or {}
    if not isinstance(component, dict):
        component = {}

    province = _coerce_str(component.get("province"))
    city = _coerce_str(component.get("city"))
    district = _coerce_str(component.get("district"))
    adcode = _coerce_str(component.get("adcode"))

    formatted_address = _coerce_str(item.get("formatted_address"))

    location_str = item.get("location")
    lng, lat = _parse_location(location_str, fallback_lng, fallback_lat)

    # ---- 细粒度字段 (F051 §3.2 StructuredAddress 街道/小区/POI/门牌号) ----
    # 优先级: streetNumber.street (最具体, 含路名+门牌) > township (街道/镇).
    # 高德偶发只填其中一个, 取先命中且非空者.
    street_number = component.get("streetNumber") or {}
    if not isinstance(street_number, dict):
        street_number = {}
    township = _coerce_str(component.get("township"))
    street_name = _coerce_str(street_number.get("street"))
    street = township or street_name or None

    neighborhood = component.get("neighborhood") or {}
    if not isinstance(neighborhood, dict):
        neighborhood = {}
    community_raw = _coerce_str(neighborhood.get("name"))
    community = community_raw or None

    door_raw = _coerce_str(street_number.get("number"))
    door_no = door_raw or None

    # POI: 取 `pois[0].id` (最近的 POI). AMAP 偶发给非标准 id (如空 / 含特殊
    # 字符的内部临时 id), 用 `_POI_ID_PATTERN` 拦截, 不合规直接 None.
    raw_pois = item.get("pois") or []
    poi_id: str | None = None
    community_fallback: str | None = None
    if isinstance(raw_pois, list):
        for raw_poi in raw_pois:
            if not isinstance(raw_poi, dict):
                continue
            candidate_id = _coerce_str(raw_poi.get("id"))
            if poi_id is None and candidate_id and _POI_ID_PATTERN.match(candidate_id):
                poi_id = candidate_id
            # community 兜底: 当 addressComponent.neighborhood.name 缺失时,
            # 用 POI 的 name 兜底 (AMAP 把小区名塞在 pois[].name 而非 neighborhood).
            # 仅当 POI type 命中住宅/小区分类时采纳 — 避免把"海底捞"当成小区名.
            if community is None and community_fallback is None:
                poi_type = _coerce_str(raw_poi.get("type"))
                if any(t in poi_type for t in _POI_COMMUNITY_TYPES):
                    poi_name = _coerce_str(raw_poi.get("name"))
                    if poi_name:
                        community_fallback = poi_name
        # 兜底放最后赋值, 这样如果第一个 POI 没 type 命中但第二个命中,
        # 仍能拿到 community (且不覆盖已从 neighborhood 取得的值)
        if community is None:
            community = community_fallback

    return {
        "province": province,
        "city": city,
        "district": district,
        "adcode": adcode,
        "formatted_address": formatted_address,
        "longitude": lng,
        "latitude": lat,
        "street": street,
        "community": community,
        "door_no": door_no,
        "poi_id": poi_id,
    }


def _parse_location(
    raw: object, fallback_lng: float, fallback_lat: float
) -> tuple[float, float]:
    """高德 location 格式: 'lng,lat'. 解析失败用 fallback."""
    if not isinstance(raw, str) or not raw.strip():
        return (fallback_lng, fallback_lat)
    parts = raw.split(",")
    if len(parts) != 2:
        return (fallback_lng, fallback_lat)
    try:
        return (float(parts[0]), float(parts[1]))
    except (TypeError, ValueError):
        return (fallback_lng, fallback_lat)


def _coerce_str(raw: object) -> str:
    return raw if isinstance(raw, str) else ""


__all__ = ["amap_regeo", "RegeoInfo"]
