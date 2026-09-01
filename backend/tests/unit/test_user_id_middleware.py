"""Unit tests for `UserIdMiddleware` — header / generated UUID / cookie semantics."""
from __future__ import annotations

import re

from app.core.user_id import (
    USER_ID_COOKIE,
    USER_ID_COOKIE_MAX_AGE,
    USER_ID_HEADER,
    UserIdMiddleware,
    get_current_user_id,
)
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)


def _build_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(UserIdMiddleware)

    @app.get("/whoami")
    def whoami(user_id: str = Depends(get_current_user_id)) -> dict[str, str]:
        return {"user_id": user_id}

    return app


class TestUserIdMiddleware:
    def test_generates_uuid_when_header_missing(self) -> None:
        # Arrange
        client = TestClient(_build_app())

        # Act
        resp = client.get("/whoami")

        # Assert
        assert resp.status_code == 200
        user_id = resp.json()["user_id"]
        assert _UUID_RE.match(user_id), f"Expected UUID4, got {user_id!r}"

    def test_sets_cookie_when_uuid_was_generated(self) -> None:
        client = TestClient(_build_app())
        resp = client.get("/whoami")
        set_cookie = resp.headers.get("set-cookie", "")
        assert f"{USER_ID_COOKIE}=" in set_cookie
        # HttpOnly + SameSite=Lax + Path=/
        assert "HttpOnly" in set_cookie
        assert "SameSite=lax" in set_cookie or "samesite=lax" in set_cookie.lower()
        assert "Path=/" in set_cookie
        assert f"Max-Age={USER_ID_COOKIE_MAX_AGE}" in set_cookie

    def test_honors_incoming_header_value(self) -> None:
        # Arrange
        client = TestClient(_build_app())
        explicit = "550e8400-e29b-41d4-a716-446655440000"

        # Act
        resp = client.get("/whoami", headers={USER_ID_HEADER: explicit})

        # Assert
        assert resp.status_code == 200
        assert resp.json()["user_id"] == explicit
        # No Set-Cookie when caller already provided one (avoid clobbering).
        set_cookie = resp.headers.get("set-cookie", "")
        assert USER_ID_COOKIE not in set_cookie

    def test_strips_whitespace_around_header(self) -> None:
        client = TestClient(_build_app())
        explicit = "550e8400-e29b-41d4-a716-446655440000"
        resp = client.get("/whoami", headers={USER_ID_HEADER: f"  {explicit}  "})
        assert resp.json()["user_id"] == explicit

    def test_each_request_without_header_gets_distinct_uuid(self) -> None:
        # TestClient persists cookies across requests within a single instance,
        # which means the middleware would reuse the same UUID after the first
        # request. To exercise "no header, no cookie → fresh UUID" twice we
        # need two independent clients.
        client_a = TestClient(_build_app())
        client_b = TestClient(_build_app())
        first = client_a.get("/whoami").json()["user_id"]
        second = client_b.get("/whoami").json()["user_id"]
        assert first != second