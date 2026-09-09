"""F051 — 高德 MCP 行政区划查询 Tool.

设计要点 (per spec/features/F051-structured-address.md §5.1):

- 封装 `GET /v3/config/district` 拉省 / 市 / 区级联列表
- 输入: `keywords: str | None` (不传 → 拉省级列表), `subdistrict: 0/1/2/3`
  控制返回层级深度
- 输出: `list[DistrictInfo]` (TypedDict), 字段含 adcode / name / level /
  center (经纬度) / 下属子区列表
- 错误码沿用 F031 §5: `AMAP_INVALID_KEY` / `AMAP_QUOTA_EXCEEDED` /
  `AMAP_NETWORK_ERROR`; 新增 `AMAP_DISTRICT_NOT_FOUND`

不使用 LangChain `@tool` 装饰器 (项目不依赖 LangChain Tools) — 函数
签名遵循 LangChain Tool 风格, 由前端 `useDistrictList` Hook 直接 await.
"""
from __future__ import annotations

import logging
from typing import Literal

from typing_extensions import TypedDict

from app.mcp.amap.client import AmapClient

logger = logging.getLogger(__name__)

# 高德 `/v3/config/district` endpoint
_DISTRICT_PATH = "/v3/config/district"

# subdistrict 取值范围
_SUBDISTRICT_VALUES = (0, 1, 2, 3)
# keywords 长度上限 (防止误用拖慢下游; 真实场景用户只输入省/市/区名)
_MAX_KEYWORDS_LENGTH = 64


# ----- 类型契约 (F051 §5.1) -----


DistrictLevel = Literal["country", "province", "city", "district", "street"]


class DistrictInfo(TypedDict):
    """高德 `/config/district` 返回的单条行政区划.

    `districts` 仅当 `subdistrict >= 1` 且该节点有下属区划时非空.
    """

    adcode: str
    name: str
    level: DistrictLevel
    center: tuple[float, float]  # (longitude, latitude) — None-safe 转 0.0,0.0
    districts: list["DistrictInfo"]


# ----- 主入口 -----


async def amap_get_district(
    *,
    keywords: str | None = None,
    subdistrict: Literal[0, 1, 2, 3] = 1,
    client: AmapClient | None = None,
) -> list[DistrictInfo]:
    """F051 主入口 —— 调用高德『行政区划』API.

    Args:
        keywords: 省 / 市 / 区名 (高德中文名). 不传或空字符串 → 拉省级列表
                  (4 直辖市 + 27 省会 + 港澳, 约 36 项).
        subdistrict: 下钻层级深度.
                     - 0: 不下钻 (仅返回 keywords 命中节点)
                     - 1: keywords → 下属 1 级 (省 → 市, 市 → 区)
                     - 2: 再下钻 1 级 (省 → 市 → 区)
                     - 3: 再下钻 1 级 (省 → 市 → 区 → 街道)
        client: 已构造的 `AmapClient`. 不传则用工厂 (推荐用于生产,
                测试时可注入 monkeypatched key 的实例).

    Returns:
        `list[DistrictInfo]` — 高德返回的行政区划节点列表 (通常长度 1,
        keywords=None 时长度 ≈ 36 个省级单位).

    Raises:
        ValueError: 入参非法 (subdistrict 越界 / keywords 过长)
        AmapInvalidKeyError: API key 无效或未配置
        AmapQuotaExceededError: 高德配额耗尽
        AmapNetworkError: 网络/超时重试耗尽
        AmapDistrictNotFoundError: keywords 未命中 (高德返回空 districts)
    """
    # ---- 入参校验 ----
    if subdistrict not in _SUBDISTRICT_VALUES:
        raise ValueError(
            f"subdistrict 必须在 {_SUBDISTRICT_VALUES}, 实际={subdistrict}"
        )
    if keywords is not None and len(keywords) > _MAX_KEYWORDS_LENGTH:
        raise ValueError(
            f"keywords 长度必须 <= {_MAX_KEYWORDS_LENGTH}, 实际={len(keywords)}"
        )

    # ---- HTTP 调用 ----
    if client is None:
        from app.mcp.amap.client import get_amap_client

        client = get_amap_client()

    params: dict[str, str] = {
        "subdistrict": str(subdistrict),
        "extensions": "base",  # 行政区划查询不需 POI 扩展
    }
    if keywords is not None and keywords.strip():
        params["keywords"] = keywords.strip()
    # keywords 为空时不传, 高德默认返回国家级根 (中国)

    payload = await client.get_json(_DISTRICT_PATH, params=params)

    raw_districts = payload.get("districts") or []
    if not isinstance(raw_districts, list):
        logger.warning(
            "Amap /v3/config/district 返回非 list districts, payload=%s", payload
        )
        raw_districts = []

    # ---- 解析 ----
    parsed: list[DistrictInfo] = []
    for item in raw_districts:
        if not isinstance(item, dict):
            continue
        node = _parse_district(item)
        if node is not None:
            parsed.append(node)

    # ---- 错误: keywords 命中但空结果 ----
    if parsed == [] and keywords is not None and keywords.strip():
        from app.core.exceptions import AmapDistrictNotFoundError

        raise AmapDistrictNotFoundError(
            f"高德未找到行政区划 (keywords={keywords!r})",
            details={"keywords": keywords},
        )

    # ---- 展开: subdistrict >= 1 时, 调用方想要的是 matched node 的子级 ----
    # `subdistrict=0` (不展开) 路径在 `app.mcp.amap.restaurant` 用: 用 adcode
    # 反查中心坐标, 必须保留 matched node 自身; `subdistrict>=1` (级联展开)
    # 才是 AddressPickerDialog 省→市→区级联的输入, 应当返回子级列表, 让
    # `cityList.map(...)` 直接拿到市级条目 (而不是把省级节点当城市填进下拉).
    if subdistrict >= 1 and len(parsed) == 1:
        return list(parsed[0]["districts"])
    return parsed


# ----- 内部辅助 -----


def _parse_district(item: dict[str, object]) -> DistrictInfo | None:
    """从高德原始 district dict 抽出强类型字段; 缺关键字段则丢弃."""
    adcode = item.get("adcode")
    name = item.get("name")
    if not isinstance(adcode, str) or not isinstance(name, str):
        return None

    center = _parse_center(item.get("center"))

    raw_districts = item.get("districts") or []
    districts: list[DistrictInfo] = []
    if isinstance(raw_districts, list):
        for child in raw_districts:
            if isinstance(child, dict):
                child_parsed = _parse_district(child)
                if child_parsed is not None:
                    districts.append(child_parsed)

    return {
        "adcode": adcode,
        "name": name,
        "level": _coerce_level(item.get("level")),
        "center": center,
        "districts": districts,
    }


def _parse_center(raw: object) -> tuple[float, float]:
    """高德 center 格式: 'lng,lat'. 解析失败兜底 (0.0, 0.0)."""
    if not isinstance(raw, str) or not raw.strip():
        return (0.0, 0.0)
    parts = raw.split(",")
    if len(parts) != 2:
        return (0.0, 0.0)
    try:
        return (float(parts[0]), float(parts[1]))
    except (TypeError, ValueError):
        return (0.0, 0.0)


def _coerce_level(raw: object) -> DistrictLevel:
    """高德 level 字段: 'country' / 'province' / 'city' / 'district' / 'street'."""
    if raw == "country":
        return "country"
    if raw == "province":
        return "province"
    if raw == "city":
        return "city"
    if raw == "district":
        return "district"
    if raw == "street":
        return "street"
    return "district"  # 未知值兜底


__all__ = ["amap_get_district", "DistrictInfo", "DistrictLevel"]
