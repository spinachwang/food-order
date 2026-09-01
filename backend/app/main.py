"""FastAPI application entry point — M0 healthz + M1 preferences + exception handlers."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import api_router
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.user_id import UserIdMiddleware


def create_app() -> FastAPI:
    """Application factory."""
    settings = get_settings()
    app = FastAPI(
        title="food-order API",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # Order matters: CORS first, then X-User-Id middleware so request handlers
    # (and exception handlers below) can read request.state.user_id.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(UserIdMiddleware)

    # Error envelope — applies to DomainError, RequestValidationError, HTTPException.
    register_exception_handlers(app)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        """Liveness probe."""
        return {"status": "ok"}

    app.include_router(api_router, prefix="/api/v1")
    return app


app = create_app()
