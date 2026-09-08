"""`/api/v1/geocode/regeo` router — F051 §5.2.

HTTP 包装 `amap_regeo` MCP Tool: 前端 AddressPickerDialog "📍 使用当前
位置" 按钮 — 浏览器 `navigator.geolocation` 拿到坐标 → 此路由反查
province / city / district / adcode.

输入: `location` (必填) — `"lng,lat"` 字符串.
输出: `RegeoInfo` TypedDict (province / city / district / adcode /
formatted_address / longitude / latitude).

错误码由 [app.core.exceptions](app/core/exceptions.py) 透传
`AMAP_LOCATION_INVALID` / `AMAP_INVALID_KEY` / `AMAP_QUOTA_EXCEEDED` /
`AMAP_NETWORK_ERROR`. 入参格式错误由 FastAPI 自动 422.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.core.request_id import get_request_id
from app.core.user_id import get_current_user_id
from app.mcp.amap.regeo import RegeoInfo, amap_regeo

router = APIRouter()


@router.get("/regeo", response_model=RegeoInfo)
async def geocode_regeo(
    location: str = Query(
        ...,
        description="经纬度字符串, 格式 'lng,lat' (例: '121.473701,31.230416')",
    ),
    _user_id: str = Depends(get_current_user_id),
) -> RegeoInfo:
    """F051 §5.2: 逆地理编码 — 经纬度 → 行政区划."""
    _ = get_request_id()
    return await amap_regeo(location=location)


__all__ = ["router"]
