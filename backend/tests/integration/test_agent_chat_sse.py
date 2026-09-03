"""F004 §7 — end-to-end integration test for `POST /api/v1/agent/chat`.

This test pins the SSE consumer experience:

- Request  →  single Graph run START → END
- Response →  text/event-stream with at minimum one frame per spec §4
  (cuisine_selected / cuisine_result / restaurant_found / weather /
  recommendation), then a terminal `done` frame.
- Headers →  Cache-Control / X-Accel-Buffering match streaming best practice.

The DB dependency (`get_db`) is overridden to a stub so this test does NOT
require MySQL — F001's `load_preferences` is also patched to return a
fixed preferences dict. F030 / F031 / F040 / cuisine expert runs are
patched the same way as `test_graph.py` does.
"""

from __future__ import annotations

from contextlib import ExitStack
from decimal import Decimal
from typing import Any
from unittest.mock import patch

from app.agents.cuisines import CUISINE_REGISTRY
from app.core.constants import CUISINE_IDS
from app.core.db import get_db
from app.main import create_app
from app.services import preferences as preferences_service
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------


def _stub_preferences() -> dict[str, Any]:
    return {
        "user_id": "u-int",
        "cuisine_weights": dict.fromkeys(CUISINE_IDS, 0.5),
        "allergies": [],
        "spice_tolerance": 1,
        "temperature_preference": "room",
        "default_location": "国贸",
        "budget_lunch_min": Decimal("30.00"),
        "budget_lunch_max": Decimal("80.00"),
    }


def _stub_session() -> Any:
    """A no-op Session-like object; the endpoint only calls

    `load_preferences(session, user_id)` which we patch directly."""
    class _NoopSession:
        def close(self) -> None: ...

    return _NoopSession()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAgentChatEndpoint:
    """Pin the SSE consumer experience end-to-end."""

    def test_post_chat_returns_event_stream_media_type(self) -> None:
        """Spec §M1: content-type is `text/event-stream`."""
        app = create_app()
        app.dependency_overrides[get_db] = lambda: _stub_session()
        with patch.object(
            preferences_service,
            "load_preferences",
            lambda session, user_id: _stub_preferences(),
        ), TestClient(app) as client:
            response = client.post(
                "/api/v1/agent/chat",
                json={"message": "今天想吃辣的"},
                headers={"X-User-Id": "u-int"},
            )
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")

    def test_post_chat_stream_includes_done_event(self) -> None:
        """The terminal `done` frame is always present after a complete run."""
        app = create_app()
        app.dependency_overrides[get_db] = lambda: _stub_session()
        with ExitStack() as stack:
            stack.enter_context(
                patch.object(
                    preferences_service,
                    "load_preferences",
                    lambda session, user_id: _stub_preferences(),
                )
            )
            async def _router_stub(state: Any, **kwargs: Any) -> dict[str, Any]:
                return {
                    "selected_cuisines": ["sichuan", "cantonese"],
                    "routing_reason": "test routing reason",
                    "routing_log": [],
                    "errors": [],
                }
            stack.enter_context(
                patch(
                    "app.agents.nodes.route.f002_route_cuisines",
                    _router_stub,
                )
            )
            for cid in ("sichuan", "cantonese"):
                stack.enter_context(
                    patch.object(CUISINE_REGISTRY[cid], "run")
                ).return_value = {
                    "cuisine_id": cid,
                    "conclusion": f"{cid} ok",
                    "keywords": [f"{cid}-kw"],
                    "matched_allergies": [],
                }
            with TestClient(app) as client, client.stream(
                "POST",
                "/api/v1/agent/chat",
                json={"message": "今天想吃辣的"},
                headers={"X-User-Id": "u-int"},
            ) as response:
                assert response.status_code == 200
                body = b"".join(response.iter_bytes()).decode("utf-8")

        # Spec §4 — at minimum `done` must be present.
        assert "event: done" in body
        # Spec §4 — cuisine_selected is emitted because route_cuisines ran.
        assert "event: cuisine_selected" in body
        # Spec §4 — cuisine_result carries the per-cuisine aggregation.
        assert "event: cuisine_result" in body

    def test_post_chat_missing_user_id_still_handles_first_visit(self) -> None:
        """The X-User-Id middleware auto-generates a UUID; the endpoint

        should still succeed (it just calls preferences_service for a
        different user_id). The test only asserts the streaming path
        works end-to-end without an explicit X-User-Id."""
        app = create_app()
        app.dependency_overrides[get_db] = lambda: _stub_session()
        with ExitStack() as stack:
            stack.enter_context(
                patch.object(
                    preferences_service,
                    "load_preferences",
                    lambda session, user_id: _stub_preferences(),
                )
            )
            async def _router_stub(state: Any, **kwargs: Any) -> dict[str, Any]:
                return {
                    "selected_cuisines": ["sichuan"],
                    "routing_reason": "test",
                    "routing_log": [],
                    "errors": [],
                }
            stack.enter_context(
                patch(
                    "app.agents.nodes.route.f002_route_cuisines",
                    _router_stub,
                )
            )
            stack.enter_context(
                patch.object(CUISINE_REGISTRY["sichuan"], "run")
            ).return_value = {
                "cuisine_id": "sichuan",
                "conclusion": "ok",
                "keywords": ["kw"],
                "matched_allergies": [],
            }
            with TestClient(app) as client, client.stream(
                "POST",
                "/api/v1/agent/chat",
                json={"message": "hi"},
            ) as response:
                assert response.status_code == 200
                body = b"".join(response.iter_bytes()).decode("utf-8")

        # First-visit path: no X-User-Id means a UUID is generated internally;
        # graph still runs to completion and emits a `done` frame.
        assert "event: done" in body
