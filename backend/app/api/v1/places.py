"""`/api/v1/places/search` router — F051 §5.3.

HTTP 包装 `amap_search_places` MCP Tool: 前端 AddressPickerDialog 商圈 /
小区 / 楼宇搜索. 输入:
- `keywords` (必填): 搜索关键字.
- `city` (可选): adcode 或城市名, 限定搜索范围.
- `types` (可选): POI 分类过滤 (高德分类码或中文类名); 不传 → "050000"
  餐饮服务大类 (向后兼容 F030).
- `offset` (可选 1-25): 返回条数上限.

错误码由 [app.core.exceptions](app/core/exceptions.py) 透传.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.core.request_id import get_request_id
from app.core.user_id import get_current_user_id
from app.mcp.amap.place_text import PlaceSearchResult, amap_search_places

router = APIRouter()


@router.get("/search", response_model=PlaceSearchResult)
async def search_places(
    keywords: str = Query(
        ...,
        min_length=1,
        max_length=64,
        description="搜索关键字 (例: '南京西路' / '静安嘉里中心')",
    ),
    city: str | None = Query(
        default=None,
        max_length=64,
        description="限定城市 (adcode 或城市名, 例: '310100')",
    ),
    types: str | None = Query(
        default=None,
        max_length=64,
        description="POI 分类过滤 (例: '商圈' / '商务住宅|地名地址信息')",
    ),
    offset: int = Query(
        default=10,
        ge=1,
        le=25,
        description="返回条数上限 (1-25)",
    ),
    _user_id: str = Depends(get_current_user_id),
) -> PlaceSearchResult:
    """F051 §5.3: POI 关键字搜索 — 商圈 / 小区 / 楼宇 主入口.

    city 限定时由 wrapper 自动加 `citylimit=true` (强制只在 city 范围内匹配).
    """
    _ = get_request_id()  # 已通过 logger filter 注入
    return await amap_search_places(
        keywords=keywords, city=city, types=types, offset=offset
    )


__all__ = ["router"]
