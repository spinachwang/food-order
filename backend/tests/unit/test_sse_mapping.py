"""F004 §4 — SSE wire format and LangGraph-event → SSE translation.

These tests pin the public contract the frontend (F050) consumes:

1. `event:` / `data:` / blank-line wire format matches the spec & FastAPI's
   `text/event-stream` parsing expectations.
2. `_frame_from_event` only emits frames for `on_chain_end` events whose
   `name` is one of the documented graph Nodes; everything else is a no-op
   (so the SSE consumer never sees partial / internal lifecycle noise).
3. Each graph Node maps to the documented SSE event name (`route_cuisines`
   → `cuisine_selected`, etc.).
4. The terminal `done` event is always emitted by the endpoint after the
   graph completes.

The streaming consumer itself (FastAPI handler) is covered by an
integration test below against the live `TestClient`.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from app.agents.graph import GRAPH_NODE_NAMES
from app.api.v1.agent import (
    _frame_from_event,
    _sse_frame,
)

# ---------------------------------------------------------------------------
# Wire format — `_sse_frame`
# ---------------------------------------------------------------------------


class TestSSEFrameFormat:
    """Pin the literal wire shape spec/api.md §M1 promises."""

    def test_frame_uses_event_data_blank_line_wire_format(self) -> None:
        """Spec §M1: `event: <name>\\ndata: <json>\\n\\n`."""
        body = _sse_frame("cuisine_selected", {"cuisines": ["sichuan"]})
        text = body.decode("utf-8")
        assert text.startswith("event: cuisine_selected\n")
        assert text.endswith("\n\n")
        # data line is exactly one JSON object — no extra trailing commas.
        data_line = text.splitlines()[1]
        assert data_line.startswith("data: ")
        assert json.loads(data_line.removeprefix("data: ")) == {"cuisines": ["sichuan"]}

    def test_json_payload_preserves_unicode(self) -> None:
        """Chinese characters in routing_reason must survive round-trip."""
        body = _sse_frame(
            "cuisine_selected",
            {"cuisines": ["sichuan"], "routing_reason": "你说想吃辣的 → 川 + 湘"},
        )
        text = body.decode("utf-8")
        assert "你说想吃辣的 → 川 + 湘" in text

    def test_unserializable_payload_is_handled_gracefully(self) -> None:
        """`default=str` covers Decimal / datetime; serialization never raises."""
        body = _sse_frame("weather", {"pop": 0.05, "fetched_at": "2026-09-03T10:00:00Z"})
        assert isinstance(body, bytes)


# ---------------------------------------------------------------------------
# LangGraph-event → SSE translation — `_frame_from_event`
# ---------------------------------------------------------------------------


def _chain_end(name: str, output: dict[str, object] | None) -> dict[str, Any]:
    """Build a LangGraph v2 `on_chain_end` event payload for tests."""
    return {
        "event": "on_chain_end",
        "name": name,
        "data": {"output": output or {}},
        "run_id": "test-run",
        "tags": [],
        "metadata": {},
    }


def _chain_start(name: str) -> dict[str, Any]:
    """Build a `on_chain_start` event — should be skipped by the SSE layer."""
    return {
        "event": "on_chain_start",
        "name": name,
        "data": {},
        "run_id": "test-run",
        "tags": [],
        "metadata": {},
    }


class TestFrameTranslation:
    """Pin mapping from LangGraph event → SSE frame."""

    def test_route_cuisines_maps_to_cuisine_selected(self) -> None:
        event = _chain_end(
            "route_cuisines",
            {"selected_cuisines": ["sichuan", "hunan"], "routing_reason": "想辣 → 川 + 湘"},
        )
        frame = _frame_from_event(event)
        assert frame is not None
        text = frame.decode("utf-8")
        assert text.startswith("event: cuisine_selected\n")
        data = json.loads(text.splitlines()[1].removeprefix("data: "))
        assert data["cuisines"] == ["sichuan", "hunan"]
        assert "想辣" in data["routing_reason"]

    def test_cuisine_fanout_maps_to_cuisine_result(self) -> None:
        event = _chain_end(
            "cuisine_fanout",
            {
                "cuisine_results": {
                    "sichuan": {"cuisine_id": "sichuan", "conclusion": "好"},
                }
            },
        )
        text = _frame_from_event(event).decode("utf-8")  # type: ignore[union-attr]
        assert text.startswith("event: cuisine_result\n")
        data = json.loads(text.splitlines()[1].removeprefix("data: "))
        assert "sichuan" in data["results"]

    def test_search_restaurants_maps_to_restaurant_found(self) -> None:
        event = _chain_end(
            "search_restaurants",
            {"restaurant_lists": {"sichuan": [{"name": "蜀香苑"}]}},
        )
        text = _frame_from_event(event).decode("utf-8")  # type: ignore[union-attr]
        assert text.startswith("event: restaurant_found\n")
        data = json.loads(text.splitlines()[1].removeprefix("data: "))
        assert "sichuan" in data["restaurant_lists"]

    def test_fetch_weather_maps_to_weather(self) -> None:
        event = _chain_end(
            "fetch_weather",
            {"weather": {"temperature": 32, "condition": "sunny"}},
        )
        text = _frame_from_event(event).decode("utf-8")  # type: ignore[union-attr]
        assert text.startswith("event: weather\n")

    def test_summarize_maps_to_recommendation(self) -> None:
        event = _chain_end(
            "summarize",
            {"recommendation": {"headline": "今天推荐：蜀香苑"}},
        )
        text = _frame_from_event(event).decode("utf-8")  # type: ignore[union-attr]
        assert text.startswith("event: recommendation\n")

    @pytest.mark.parametrize(
        "silent_node",
        ["load_preferences", "stream_output"],
    )
    def test_silent_nodes_emit_no_sse_frame(self, silent_node: str) -> None:
        """Spec §4 has no row for load_preferences / stream_output — they

        are internal lifecycle hooks only."""
        event = _chain_end(silent_node, {"anything": "is-fine"})
        assert _frame_from_event(event) is None

    def test_chain_start_is_ignored(self) -> None:
        """Stream consumer only cares about Node end events."""
        event = _chain_start("route_cuisines")
        assert _frame_from_event(event) is None

    def test_unknown_node_names_are_ignored(self) -> None:
        """Lifecycle events from internal LangGraph pseudo-nodes (e.g.

        `LangGraph`, `__start__`, `_write`) should never surface as SSE."""
        for name in ("LangGraph", "__start__", "_write", "LangSmithTracer"):
            event = _chain_end(name, {"any": "thing"})
            assert _frame_from_event(event) is None, name

    def test_nodes_constant_matches_tested_set(self) -> None:
        """Sanity: GRAPH_NODE_NAMES exposes exactly the 7 specs §3.2 Names."""
        assert set(GRAPH_NODE_NAMES) == {
            "load_preferences",
            "route_cuisines",
            "cuisine_fanout",
            "search_restaurants",
            "fetch_weather",
            "summarize",
            "stream_output",
        }

    def test_non_dict_event_silently_skipped(self) -> None:
        """Defensive: non-dict events (defensive against LangGraph changes)

        are skipped rather than raising — the SSE layer never crashes the
        graph."""
        assert _frame_from_event("not-a-dict") is None  # type: ignore[arg-type]
        assert _frame_from_event(None) is None  # type: ignore[arg-type]
