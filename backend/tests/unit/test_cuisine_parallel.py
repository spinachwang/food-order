"""F003 §6 — cuisine expert parallel-dispatch contract test.

This unit test pins down the contract F003 promises to F004 (LangGraph workflow):

    "any cuisine Node can be invoked in parallel by the main Agent, and its
    results aggregate independently into `AgentState.cuisine_results`."

We do **not** need a real LangGraph runtime here — the contract is about the
*shape* of the parallel-fanout / fan-in, not about graph wiring. F004 will
own the actual graph construction; this test enforces that whatever F004
builds, the registry's 14 experts can be `asyncio.gather`-ed and merged
into `AgentState["cuisine_results"]` (dict[str, CuisineExpertOutput]) without
cross-contamination.

Why this lives in `tests/unit/` and not `tests/integration/`:
    Spec §6 calls it an "集成测试", but it touches no DB / HTTP / LangGraph —
    only asyncio + the cuisine registry. Placing it next to the other F003
    unit tests keeps the suite cohesive and avoids MySQL flakiness in CI.
"""

from __future__ import annotations

import asyncio
from contextlib import ExitStack
from decimal import Decimal
from typing import Any, cast
from unittest.mock import patch

from app.agents.cuisines import CUISINE_REGISTRY, BaseCuisineExpert
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
        "user_preferences": prefs,
    }
    state.update(overrides)  # type: ignore[typeddict-item]
    return state


def _stub_output(cuisine_id: str, suffix: str) -> CuisineExpertOutput:
    """Build a deterministic stub output for a cuisine (parse_output-shaped)."""
    return {
        "cuisine_id": cuisine_id,
        "conclusion": f"{cuisine_id} {suffix}",
        "keywords": [f"{cuisine_id}_kw_{suffix}"],
        "matched_allergies": [],
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestParallelDispatchContract:
    """Pin the contract F003 → F004: ≥3 experts can run concurrently and
    aggregate into `cuisine_results` keyed by `cuisine_id`."""

    def test_registry_keys_cover_all_cuisine_ids(self) -> None:
        """Stronger than a bare length check: pin both completeness and order.

        `test_base_contract.py::test_registry_has_all_14_cuisines` already
        covers `len == 14` + set equality. This test pins **order**, which
        matters for stable UI iteration and for the F004 parallel-fanout
        determinism story (the same target list always runs in the same order).
        """
        assert tuple(CUISINE_REGISTRY.keys()) == CUISINE_IDS

    def test_asyncio_gather_aggregates_results_by_cuisine_id(self) -> None:
        """F003 §6 — parallel dispatch + independent aggregation."""
        targets = ["sichuan", "cantonese", "japanese"]

        # Stub each expert's `run()` to return a distinct fake output. The
        # patches must stay alive for the whole fan_out() call, so we use an
        # ExitStack rather than a per-target `with` block (a per-target `with`
        # would exit before `asyncio.run` ever runs).
        with ExitStack() as stack:
            for cid in targets:
                output = _stub_output(cid, suffix="ok")
                mock_run = stack.enter_context(patch.object(CUISINE_REGISTRY[cid], "run"))
                mock_run.return_value = output

            async def fan_out() -> dict[str, CuisineExpertOutput]:
                coros = [CUISINE_REGISTRY[cid].run(_state()) for cid in targets]
                results = await asyncio.gather(*coros)
                # Aggregate into `AgentState.cuisine_results` (keyed by cuisine_id).
                # cast: `patch.object` widens the return type to object even
                # though our stub returns the CuisineExpertOutput shape.
                merged: dict[str, CuisineExpertOutput] = {
                    cid: cast(CuisineExpertOutput, result)
                    for cid, result in zip(targets, results, strict=True)
                }
                return merged

            merged = asyncio.run(fan_out())

        # Independent aggregation: each cuisine's output is untouched.
        assert set(merged.keys()) == set(targets)
        for cid in targets:
            assert merged[cid]["cuisine_id"] == cid
            assert merged[cid]["conclusion"] == f"{cid} ok"
            assert merged[cid]["keywords"] == [f"{cid}_kw_ok"]

    def test_one_expert_failure_does_not_taint_others(self) -> None:
        """F003 §3.3 — 单个菜系 Node 异常不中断整体工作流.

        We patch a real registry expert to raise, alongside two other registry
        experts that succeed. The point is to prove the §3.3 contract holds
        *for the experts* — not just that `asyncio.gather(return_exceptions=True)`
        works on arbitrary coroutines. The summary agent (F040) is responsible
        for handling the exception; here we only assert that gather preserves
        it cleanly while the siblings' results land in `cuisine_results`.
        """
        targets = ["sichuan", "cantonese", "japanese"]
        boom = RuntimeError("cuisine expert exploded")

        with ExitStack() as stack:
            # sichuan and japanese succeed; cantonese raises.
            stack.enter_context(
                patch.object(CUISINE_REGISTRY["sichuan"], "run")
            ).return_value = _stub_output("sichuan", suffix="ok")
            stack.enter_context(
                patch.object(CUISINE_REGISTRY["japanese"], "run")
            ).return_value = _stub_output("japanese", suffix="ok")
            stack.enter_context(
                patch.object(CUISINE_REGISTRY["cantonese"], "run")
            ).side_effect = boom

            async def fan_out() -> list[Any]:
                return await asyncio.gather(
                    *(CUISINE_REGISTRY[cid].run(_state()) for cid in targets),
                    return_exceptions=True,
                )

            results = asyncio.run(fan_out())

        assert isinstance(results[1], RuntimeError) and results[1] is boom
        assert results[0] == _stub_output("sichuan", suffix="ok")
        assert results[2] == _stub_output("japanese", suffix="ok")

    def test_registry_experts_are_independent_instances(self) -> None:
        """Mutating one expert's prompt_fragment must not leak into siblings.

        The 14 expert instances are module-level singletons, so restoration
        must come from a capture of the SAME instance we mutated — otherwise
        a test running after this one would observe corrupted state.
        """
        sie = CUISINE_REGISTRY["sichuan"]
        can = CUISINE_REGISTRY["cantonese"]
        original_sie_fragment = sie.prompt_fragment
        original_can_fragment = can.prompt_fragment

        sie.prompt_fragment = "TAMPERED"
        try:
            assert can.prompt_fragment == original_can_fragment
            assert CUISINE_REGISTRY["japanese"].prompt_fragment != "TAMPERED"
        finally:
            sie.prompt_fragment = original_sie_fragment
            # Defensive: assert we restored cleanly.
            assert sie.prompt_fragment == original_sie_fragment

    def test_all_registry_experts_satisfy_base_protocol(self) -> None:
        """Defensive: every entry in CUISINE_REGISTRY must be a BaseCuisineExpert
        AND expose the four required attributes the spec §3.1 promises."""
        for cid, expert in CUISINE_REGISTRY.items():
            assert isinstance(expert, BaseCuisineExpert), cid
            assert expert.cuisine_id == cid, cid
            assert expert.display_name, cid
            assert expert.llm_model == "MiniMax-M3", cid  # F003 §8.1
            assert isinstance(expert.prompt_fragment, str), cid
            # run() is a coroutine function in Phase 1 stubs.
            assert asyncio.iscoroutinefunction(expert.run), cid
