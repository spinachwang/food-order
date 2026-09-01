"""API v1 router registry.

`api_router` aggregates per-domain routers (preferences now; agent/chat in F002).
`main.py` mounts it once at `/api/v1`.
"""
from __future__ import annotations

from fastapi import APIRouter

# Import side-effect: each submodule registers its routes onto `api_router`.
from app.api.v1 import preferences

api_router = APIRouter()
api_router.include_router(preferences.router, prefix="/preferences", tags=["preferences"])
