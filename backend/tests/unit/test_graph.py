"""F004 §7 — LangGraph graph wiring contract.

This unit test pins the *shape* F004 promises to the SSE layer (§3.2 / §4):

1. `build_graph()` returns a `CompiledStateGraph` — single executable entry.
2. `AgentState` (in `app.agents.state`) has every spec §3.1 field.
3. End-to-end the graph runs to `END` with all upstream Nodes stubbed
   (F030 / F031 / F040 + cuisine experts are still NotImplementedError — but
   the Node layer must catch them gracefully so the workflow completes).
4. Parallel cuisine fanout aggregates into `state["cuisine_results"]` keyed
   by `cuisine_id` (consistent with F003's `test_cuisine_parallel` contract).
5. `build_graph(checkpointer=True)` wires `MemorySaver` and `thread_id`
   config round-trips State.
6. `astream_events(version="v2")` yields events whose names map onto the
   SSE event names in spec §4 (i.e. `cuisine_selected`, `cuisine_result`,
   `restaurant_found`, `weather`, `recommendation`, `done`).

These are the contracts M1 cares about; deeper behavior (LLM, AMAP) belongs
to F002 / F030 / F031 / F040 — and is mocked here so this test stays fast.
"""

from __future__ import annotations

import inspect
from contextlib import ExitStack
from decimal import Decimal
from typing import Any, cast
from unittest.mock import patch

import pytest
from app.agents.cuisines import CUISINE_REGISTRY
from app.agents.graph import build_graph
from app.agents.state import (
    AgentState,
    CuisineExpertOutput,
    UserPreferencesDict,
)
from app.core.constants import CUISINE_IDS

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _state(**overrides: Any) -> AgentState:
    """A minimal valid AgentState; tests override fields as needed."""
    prefs: UserPreferencesDict = {
        "user_id": "u-test",
        "cuisine_weights": dict.fromkeys(CUISINE_IDS, 0.5),
        "allergies": [],
        "spice_tolerance": 1,
        "temperature_preference": "room",
        "default_location": "国贸",
        "budget_lunch_min": Decimal("30.00"),
        "budget_lunch_max": Decimal("80.00"),
    }
    state: AgentState = {
        "user_id": "u-test",
        "user_message": "今天想吃辣的",
        "session_id": None,
        "location_override": None,
        "user_preferences": prefs,
    }
    state.update(overrides)  # type: ignore[typeddict-item]
    return state


async def _collect_events(
    graph_input: dict[str, object],
    *,
    config: dict[str, Any] | None = None,
    checkpointer: bool = False,
) -> list[dict[str, object]]:
    """Pull events from `astream_events(version='v2')` into a plain list."""
    compiled = build_graph(checkpointer=checkpointer)
    cfg = config or {"configurable": {"thread_id": "test-1"}}
    out: list[dict[str, object]] = []
    async for ev in compiled.astream_events(graph_input, config=cfg, version="v2"):  # type: ignore[attr-defined]
        out.append(dict(ev))
    return out


class AsyncMockRouter:
    """Fake `route_cuisines` — returns a fixed RouterOutput.

    LangGraph calls the Node function with `state` as the first positional
    argument; we accept it and ignore. Returning a dict makes `unittest.mock.patch`
    callable respond as `MagicMock(return_value=...)` would for sync code.
    """

    def __init__(self, return_value: dict[str, object]) -> None:
        self._return_value = return_value

    async def __call__(self, state: AgentState, **kwargs: Any) -> dict[str, object]:
        return self._return_value


# ---------------------------------------------------------------------------
# Tests — §3.1 State schema, §3.2 single entry, §6 / §3.3 edges
# ---------------------------------------------------------------------------


class TestGraphContract:
    """Pin the public graph contract (build_graph + AgentState fields)."""

    def test_build_graph_returns_compiled_state_graph(self) -> None:
        """Spec §2 + §3.2 — single function entry returning CompiledStateGraph."""
        compiled = build_graph()
        # LangGraph >=0.2 exposes this type name; structural check via duck-typing
        # to avoid importing the private class across versions.
        assert type(compiled).__name__ == "CompiledStateGraph"
        assert hasattr(compiled, "astream_events")
        assert hasattr(compiled, "invoke")
        assert hasattr(compiled, "get_state")

    def test_build_graph_with_checkpointer_uses_memory_saver(self) -> None:
        """Spec §5 — M1 uses MemorySaver; checkpointer=True wires it.

        LangGraph 0.2.x exports the in-memory checkpointer under two
        aliases (`MemorySaver` / `InMemorySaver`) — they resolve to the
        same class, so we check behaviorally via `BaseCheckpointSaver`.
        """
        from langgraph.checkpoint.base import BaseCheckpointSaver  # type: ignore[import-not-found]

        with_memory = build_graph(checkpointer=True)
        assert isinstance(with_memory.checkpointer, BaseCheckpointSaver)
        assert with_memory.checkpointer is not None

    def test_agent_state_contains_all_spec_fields(self) -> None:
        """Spec §3.1 — the 12 documented fields exist on AgentState.

        We use `__optional_keys__ | __required_keys__` (TypedDict internals)
        rather than instance checks — TypedDict is structural, no instances
        to inspect. This catches silent renames or accidental field drops.
        """
        keys: set[str] = set(AgentState.__required_keys__)  # type: ignore[attr-defined]
        keys |= set(AgentState.__optional_keys__)  # type: ignore[attr-defined]
        for required in (
            "user_id",
            "user_message",
            "user_preferences",
            "selected_cuisines",
            "routing_reason",
            "routing_log",
            "cuisine_results",
            "restaurant_lists",
            "weather",
            "recommendation",
            "errors",
            "session_id",
            "location_override",
        ):
            assert required in keys, f"AgentState missing field: {required!r}"

    def test_graph_node_count_matches_spec_table(self) -> None:
        """Spec §3.2 lists 7 logical Nodes (load/route/fanout/search/weather/

        summarize/stream). The cuisine fanout is one Node dispatching to N
        experts, so we assert ≥5 named nodes exist on the compiled graph.
        """
        # CompiledStateGraph stores nodes on _state_builder / nodes dict across
        # versions; the most stable surface is `get_graph().nodes`.
        compiled = build_graph()
        nodes = compiled.get_graph().nodes
        names = {n for n in nodes if not n.startswith("__")}
        # Source/sink pseudo-nodes appear as "__start__" / "__end__" in 0.2.x.
        for expected in (
            "load_preferences",
            "route_cuisines",
            "cuisine_fanout",
            "search_restaurants",
            "fetch_weather",
            "summarize",
        ):
            assert expected in names, f"missing node: {expected}"


class TestEndToEndHappyPath:
    """Spec §7 happy-path — graph runs START → END, recommendation populated."""

    @pytest.mark.asyncio
    async def test_graph_completes_to_end_with_stubbed_upstream(self) -> None:
        """All Nodes must catch NotImplementedError / any exception upstream
        nodes may raise during Phase 1. F030/F031/F040/cuisine-run all raise
        NotImplementedError today; the graph must still reach END with a
        State that includes `selected_cuisines`, partial `cuisine_results`,
        and a (stub) recommendation shape.
        """
        compiled = build_graph()
        result = await compiled.ainvoke(_state())  # type: ignore[attr-defined]

        # Always present after a complete run.
        assert result["user_id"] == "u-test"
        assert "selected_cuisines" in result
        # cuisine_results is a dict keyed by cuisine_id (F003 §6 contract).
        assert isinstance(result.get("cuisine_results"), dict)
        # Errors list — every Node contributes via `errors`.
        assert isinstance(result.get("errors"), list)

    @pytest.mark.asyncio
    async def test_cuisine_fanout_aggregates_results_by_cuisine_id(self) -> None:
        """Spec §3.2 + F003 §6 — fanout emits one cuisine_result per selected

        cuisine, aggregated into the dict-keyed State slot.

        We mock the F002 `route_cuisines` return shape so the test does
        not depend on which rules a particular user message triggers —
        the cuisine fanout contract is independent of upstream routing.
        """
        targets = ("sichuan", "cantonese", "japanese")
        router_output: dict[str, object] = {
            "selected_cuisines": list(targets),
            "routing_reason": "test",
            "routing_log": [],
            "errors": [],
        }
        with ExitStack() as stack:
            # Bypass F002 routing — route_cuisines is the F002 entry; we
            # patch at the import boundary used by the LangGraph Node.
            stack.enter_context(
                patch(
                    "app.agents.nodes.route.f002_route_cuisines",
                    AsyncMockRouter(router_output),
                )
            )
            for cid in targets:
                stack.enter_context(
                    patch.object(CUISINE_REGISTRY[cid], "run")
                ).return_value = {
                    "cuisine_id": cid,
                    "conclusion": f"{cid} ok",
                    "keywords": [f"{cid}-kw"],
                    "matched_allergies": [],
                }
            compiled = build_graph()
            result = await compiled.ainvoke(_state())  # type: ignore[attr-defined]

        results = cast(dict[str, CuisineExpertOutput], result["cuisine_results"])
        assert set(results.keys()) == set(targets)
        for cid in targets:
            assert results[cid]["cuisine_id"] == cid
            assert results[cid]["keywords"] == [f"{cid}-kw"]

    @pytest.mark.asyncio
    async def test_one_cuisine_failure_does_not_break_graph(self) -> None:
        """Spec §3.4 — 单个菜系 Node 异常不中断整体工作流.

        Patches `route_cuisines` to inject [sichuan, cantonese, japanese]
        deterministically, then makes the cantonese expert raise. The
        graph must still reach END with the other two cuisines aggregated
        and the failure recorded in `errors`.
        """
        targets = ("sichuan", "cantonese", "japanese")
        router_output: dict[str, object] = {
            "selected_cuisines": list(targets),
            "routing_reason": "test",
            "routing_log": [],
            "errors": [],
        }
        with ExitStack() as stack:
            stack.enter_context(
                patch(
                    "app.agents.nodes.route.f002_route_cuisines",
                    AsyncMockRouter(router_output),
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
            stack.enter_context(
                patch.object(CUISINE_REGISTRY["cantonese"], "run")
            ).side_effect = RuntimeError("boom")
            stack.enter_context(
                patch.object(CUISINE_REGISTRY["japanese"], "run")
            ).return_value = {
                "cuisine_id": "japanese",
                "conclusion": "ok",
                "keywords": ["kw"],
                "matched_allergies": [],
            }
            compiled = build_graph()
            result = await compiled.ainvoke(_state())  # type: ignore[attr-defined]

        # Graph still reaches END.
        results = cast(dict[str, CuisineExpertOutput], result["cuisine_results"])
        assert "sichuan" in results and "japanese" in results
        # Failing cuisine is recorded as an error entry, NOT raised.
        errors = cast(list[dict[str, str]], result["errors"])
        assert any(
            "cantonese" in (e.get("cuisine_id") or e.get("message", ""))
            for e in errors
        ), errors


class TestStreamingContract:
    """Spec §4 — LangGraph emits lifecycle events; the SSE consumer layer

    maps them onto the SSE event names described in spec §4. Here we
    pin the lower-level contract: `astream_events(version='v2')` yields
    events whose `name` field carries the LangGraph Node name, enabling
    the API layer to translate each event to its SSE counterpart.
    """

    @pytest.mark.asyncio
    async def test_astream_events_carries_node_names(self) -> None:
        """Each lifecycle event must carry a `name` matching a graph Node.

        The SSE consumer (`api/v1/agent.py`) keys off `name == 'route_cuisines'`
        to emit `cuisine_selected`, `name == 'cuisine_fanout'` to emit
        `cuisine_result`, etc. Without `name` the mapping would be lossy.
        """
        with ExitStack() as stack:
            stack.enter_context(
                patch(
                    "app.agents.nodes.route.f002_route_cuisines",
                    AsyncMockRouter({
                        "selected_cuisines": ["sichuan"],
                        "routing_reason": "test",
                        "routing_log": [],
                        "errors": [],
                    }),
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
            events = await _collect_events({"user_id": "u-test", "user_message": "今天想吃辣的"})

        names = {str(ev.get("name") or ev.get("event") or "") for ev in events}
        for expected in (
            "load_preferences",
            "route_cuisines",
            "cuisine_fanout",
            "search_restaurants",
            "fetch_weather",
            "summarize",
            "stream_output",
        ):
            assert expected in names, f"missing Node event: {expected}, got {names}"

    @pytest.mark.asyncio
    async def test_events_are_async_iterable(self) -> None:
        """AStream contract — must be async-iterable (router uses `async for`)."""
        compiled = build_graph()
        ev_iter = compiled.astream_events(  # type: ignore[attr-defined]
            {"user_id": "u-test", "user_message": "hi"},
            version="v2",
        )
        assert inspect.isasyncgen(ev_iter), (
            "astream_events must yield AsyncIterator[StreamEvent]"
        )
        # Drain to keep no pending tasks leaking between tests.
        async for _ in ev_iter:
            pass


class TestCheckpointing:
    """Spec §5 — session_id 不为空按 session_id 恢复."""

    @pytest.mark.asyncio
    async def test_memory_saver_round_trip_per_thread_id(self) -> None:
        compiled = build_graph(checkpointer=True)
        cfg = {"configurable": {"thread_id": "session-A"}}
        await compiled.ainvoke(  # type: ignore[attr-defined]
            {"user_id": "u-test", "user_message": "hi", "session_id": "session-A"},
            config=cfg,
        )
        snapshot = compiled.get_state(cfg)  # type: ignore[attr-defined]
        assert snapshot is not None
        # State must be retrievable by thread_id.
        values = snapshot.values  # type: ignore[attr-defined]
        assert values["user_id"] == "u-test"
        assert values["user_message"] == "hi"
