"""`/api/v1/districts` router — F051 §5.1.

HTTP 包装 `amap_get_district` MCP Tool: 前端 AddressPickerDialog 通过此
路由拉省 / 市 / 区级联列表. 输入:
- `keywords` (可选): 省 / 市 / 区名; 不传 → 国家级根 → 36 省级.
- `subdistrict` (可选 0-3): 下钻深度.

错误码由 [app.core.exceptions](app/core/exceptions.py) 的统一 handler
透传 `AMAP_INVALID_KEY` / `AMAP_QUOTA_EXCEEDED` / `AMAP_NETWORK_ERROR` /
`AMAP_DISTRICT_NOT_FOUND` — 路由本身只做 HTTP 入参校验.
"""
from __future__ import annotations

from typing import Literal, cast

from fastapi import APIRouter, Depends, Query

from app.core.request_id import get_request_id
from app.core.user_id import get_current_user_id
from app.mcp.amap.district import DistrictInfo, amap_get_district

router = APIRouter()


@router.get("", response_model=list[DistrictInfo])
async def get_districts(
    keywords: str | None = Query(
        default=None,
        max_length=64,
        description="省/市/区名; 不传 → 国家级根 (中国 → 36 省级单位)",
    ),
    subdistrict: int = Query(
        default=1,
        ge=0,
        le=3,
        description="下钻层级深度; 0=仅 keywords 命中节点, 1=下钻 1 级, ...",
    ),
    _user_id: str = Depends(get_current_user_id),
) -> list[DistrictInfo]:
    """F051 §5.1: 行政区划查询 — 前端 AddressPickerDialog 主入口.

    Auth 仍走 `get_current_user_id` (与 preferences / agent 一致), 防止匿名滥用
    高德配额. `user_id` 本身不参与查询参数 — 仅用于 request_id 关联日志.

    `subdistrict` 在 HTTP 层声明为 `int` (FastAPI 把 query string coerce 成 int),
    由 `Query(ge=0, le=3)` 校验范围后再 cast 给 MCP tool 的 `Literal[0, 1, 2, 3]`.
    """
    _ = get_request_id()  # 已通过 logger filter 注入
    return await amap_get_district(
        keywords=keywords,
        subdistrict=cast(Literal[0, 1, 2, 3], subdistrict),
    )


__all__ = ["router"]
