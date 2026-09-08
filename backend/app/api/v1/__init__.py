"""API v1 router registry.

`api_router` aggregates per-domain routers (preferences, agent/chat).
`main.py` mounts it once at `/api/v1`.
"""
from __future__ import annotations

from fastapi import APIRouter

# Import side-effect: each submodule registers its routes onto `api_router`.
from app.api.v1 import agent, districts, geocode, places, preferences

api_router = APIRouter()
api_router.include_router(preferences.router, prefix="/preferences", tags=["preferences"])
api_router.include_router(agent.router, prefix="/agent", tags=["agent"])
# F051 §5: 高德 MCP Tool 的 HTTP 包装 — 前端 AddressPickerDialog 通过这些
# 路由触达 district / place text / regeo. 顺序无关; 按 spec 章节排.
api_router.include_router(districts.router, prefix="/districts", tags=["districts"])
api_router.include_router(places.router, prefix="/places", tags=["places"])
api_router.include_router(geocode.router, prefix="/geocode", tags=["geocode"])
