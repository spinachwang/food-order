"""X-User-Id middleware + `get_current_user_id` dependency (F001 §2).

Flow:
    request in  →  read `X-User-Id` header first
                  missing → read `x_user_id` cookie (browser-persisted)
                  missing → generate UUID4
                  populate `request.state.user_id`
    response out → if we generated a UUID, `Set-Cookie: x_user_id=<uuid>`
                   (HttpOnly, SameSite=Lax, Path=/).

Authentication is out of scope (M2). The cookie is just a convenience so the
frontend can persist its anonymous identity across page reloads.
"""
from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

USER_ID_HEADER = "X-User-Id"
USER_ID_COOKIE = "x_user_id"
USER_ID_COOKIE_MAX_AGE = 60 * 60 * 24 * 365  # 1 year


class UserIdMiddleware(BaseHTTPMiddleware):
    """ASGI middleware that guarantees a stable user_id per request."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        # Priority: explicit header (test / API caller) > cookie (browser reload)
        # > generated UUID (first-time visitor).
        incoming = request.headers.get(USER_ID_HEADER)
        if not incoming:
            cookie_value = request.cookies.get(USER_ID_COOKIE)
            if cookie_value:
                incoming = cookie_value

        if incoming:
            user_id = incoming.strip()
            generated = False
        else:
            user_id = str(uuid.uuid4())
            generated = True

        # Stash on request.state for downstream handlers
        request.state.user_id = user_id

        response = await call_next(request)

        # Only set the cookie when we *generated* a UUID. Don't clobber the
        # caller's header value, and don't re-issue if the cookie was already
        # carrying the value.
        if generated:
            response.set_cookie(
                key=USER_ID_COOKIE,
                value=user_id,
                max_age=USER_ID_COOKIE_MAX_AGE,
                httponly=True,
                samesite="lax",
                path="/",
            )
        return response


def get_current_user_id(request: Request) -> str:
    """FastAPI dependency that returns the request's resolved user_id.

    Must be called after `UserIdMiddleware` has run — i.e. always, since the
    middleware is registered on the app globally.
    """
    user_id: str | None = getattr(request.state, "user_id", None)
    if user_id is None:
        # Defensive: should never trigger because middleware always populates.
        raise RuntimeError("UserIdMiddleware did not run on this request")
    return user_id
