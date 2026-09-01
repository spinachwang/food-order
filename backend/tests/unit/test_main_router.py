"""Unit tests for the F002 main router (`app.agents.main_router`).

Covers the full F002 §3.3 control flow on a per-path basis:
- Rule layer short-circuits without calling LLM (the structural guarantee)
- Explicit naming outranks modifier tags
- Contradictory modifier tags escalate to the LLM layer
- LLM layer fallback triple (bad JSON / null list / timeout)
- Ambient ("随便" / "都行") uses weighted sampling with injected RNG
- Allergy filter + `ALL_CUISINES_FILTERED` reason copy
- Empty / garbage message short-circuits with `EMPTY_MESSAGE`, no LLM call
- `routing_log` shape + rule-layer `elapsed_ms` budget
- `routing_reason` ≤30 chars on every path

These tests should drive the RED state before `main_router.py` and
`routing/` exist — the import will fail.
"""
from __future__ import annotations

import asyncio
import random
from decimal import Decimal
from typing import Any

import pytest
from app.agents.llm.testing import FakeLLMProvider
from app.agents.llm.types import ChatResponse
from app.agents.main_router import (
    ALL_CUISINES_FILTERED,
    EMPTY_MESSAGE,
    MAX_SELECTED_CUISINES,
    NO_CUISINE_MATCHED,
    ROUTER_LLM_TIMEOUT_SECONDS,
    route_cuisines,
)
from app.agents.state import AgentState, RoutingLogEntry, UserPreferencesDict
from app.core.constants import CUISINE_IDS, NEUTRAL_CUISINE_WEIGHT
from app.core.exceptions import LLMTimeoutError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _prefs(**overrides: Any) -> UserPreferencesDict:
    base: UserPreferencesDict = {
        "user_id": "u-test",
        "cuisine_weights": dict.fromkeys(CUISINE_IDS, NEUTRAL_CUISINE_WEIGHT),
        "allergies": [],
        "spice_tolerance": 1,
        "temperature_preference": "room",
        "default_location": "国贸",
        "budget_lunch_min": Decimal("30.00"),
        "budget_lunch_max": Decimal("80.00"),
    }
    base.update(overrides)
    return base


def _state(message: str, **kwargs: Any) -> AgentState:
    prefs = kwargs.pop("preferences", None) or _prefs()
    state: AgentState = {
        "user_id": "u-test",
        "user_message": message,
        "user_preferences": prefs,
    }
    state.update(kwargs)  # type: ignore[typeddict-item]
    return state


def _run(coro: Any) -> Any:
    """Bridge async coroutines for sync tests."""
    return asyncio.run(coro)


def _llm_response(content: str) -> ChatResponse:
    return {"content": content, "model": "fake-model", "usage": None}


# ---------------------------------------------------------------------------
# Constants sanity
# ---------------------------------------------------------------------------


class TestConstants:
    def test_three_error_codes_distinct(self) -> None:
        assert EMPTY_MESSAGE != NO_CUISINE_MATCHED
        assert NO_CUISINE_MATCHED != ALL_CUISINES_FILTERED
        assert EMPTY_MESSAGE != ALL_CUISINES_FILTERED

    def test_max_selected_is_three(self) -> None:
        # Spec §3.3 — "1-3 个 cuisine_id".
        assert MAX_SELECTED_CUISINES == 3

    def test_llm_timeout_is_five_seconds(self) -> None:
        # Spec §2 — LLM fallback layer <5s, degrade on timeout.
        assert ROUTER_LLM_TIMEOUT_SECONDS == 5.0


# ---------------------------------------------------------------------------
# Rule layer — short-circuits, never calls LLM
# ---------------------------------------------------------------------------


class TestRuleLayerShortCircuit:
    def test_spicy_short_circuits_without_llm(self) -> None:
        provider = FakeLLMProvider()
        out = _run(
            route_cuisines(_state("想吃辣的"), provider=provider)
        )
        assert out["selected_cuisines"] == ["sichuan", "hunan"]
        assert provider.calls == [], "rule layer must not call LLM"

    def test_explicit_cuisine_naming_short_circuits(self) -> None:
        provider = FakeLLMProvider()
        for msg, expected_first in [
            ("想吃川菜", "sichuan"),
            ("来个粤菜", "cantonese"),
            ("想吃日料", "japanese"),
            ("西餐", "western"),
            ("快餐", "western_fastfood"),
        ]:
            provider.calls.clear()
            out = _run(route_cuisines(_state(msg), provider=provider))
            assert expected_first in out["selected_cuisines"], msg
            assert provider.calls == [], f"{msg!r} must not call LLM"

    @pytest.mark.parametrize(
        "msg, expected_subset",
        [
            ("想吃辣的", {"sichuan", "hunan"}),
            ("清淡的", {"cantonese", "suzhou", "zhejiang"}),
            ("养生", {"cantonese", "suzhou", "zhejiang"}),
            ("不油", {"cantonese", "suzhou", "zhejiang"}),
            ("快餐", {"western_fastfood", "chinese_fastfood"}),
            ("夜宵", {"snacks"}),
            ("奶茶", {"dessert_drinks"}),
            ("咖啡", {"dessert_drinks"}),
        ],
    )
    def test_modifier_rules_match_expected_cuisines(
        self, msg: str, expected_subset: set[str]
    ) -> None:
        provider = FakeLLMProvider()
        out = _run(route_cuisines(_state(msg), provider=provider))
        assert set(out["selected_cuisines"]) >= expected_subset, (
            f"{msg!r} expected at least {expected_subset}, got {out['selected_cuisines']}"
        )
        assert provider.calls == []

    def test_light_returns_three_cuisines(self) -> None:
        # F002 §3.3 + §7 (and spec correction): "清淡" → exactly 3 cuisines.
        provider = FakeLLMProvider()
        out = _run(route_cuisines(_state("清淡的"), provider=provider))
        assert len(out["selected_cuisines"]) == 3
        assert set(out["selected_cuisines"]) == {"cantonese", "suzhou", "zhejiang"}

    def test_max_three_cuisines_enforced(self) -> None:
        # Spec §3.3 — "截断 3 个".
        provider = FakeLLMProvider()
        out = _run(
            route_cuisines(
                _state(
                    "想吃点开胃的",
                    preferences=_prefs(
                        cuisine_weights={
                            "sichuan": 0.9,
                            "cantonese": 0.9,
                            "hunan": 0.9,
                            "japanese": 0.9,
                            "western": 0.9,
                        },
                    ),
                ),
                provider=provider,
                rng=random.Random(0),
            )
        )
        assert len(out["selected_cuisines"]) <= MAX_SELECTED_CUISINES


# ---------------------------------------------------------------------------
# Intent-tag partitioning (priority / contradiction)
# ---------------------------------------------------------------------------


class TestIntentTagPriority:
    def test_explicit_naming_outranks_modifier(self) -> None:
        # "日料，清淡的" — japanese (explicit) must come first;
        # cantonese/suzhou (light) follow without crowding japanese out.
        provider = FakeLLMProvider()
        out = _run(route_cuisines(_state("日料，清淡的"), provider=provider))
        assert out["selected_cuisines"][0] == "japanese"
        assert "cantonese" in out["selected_cuisines"]
        assert provider.calls == []

    def test_contradictory_modifiers_escalate_to_llm(self) -> None:
        # "想吃清淡的辣菜" — spicy + light both fire, no explicit naming
        # → must NOT merge, must escalate to LLM.
        provider = FakeLLMProvider(
            response=_llm_response(
                '{"selected_cuisines": ["cantonese"], "routing_reason": "帮你折中一下 → 粤"}'
            )
        )
        out = _run(route_cuisines(_state("想吃清淡的辣菜"), provider=provider))
        assert provider.calls, "contradictory modifiers must reach the LLM"
        assert out["selected_cuisines"] == ["cantonese"]


# ---------------------------------------------------------------------------
# LLM fallback layer
# ---------------------------------------------------------------------------


class TestLLMFallback:
    def test_gray_zone_message_triggers_llm(self) -> None:
        provider = FakeLLMProvider(
            response=_llm_response(
                '{"selected_cuisines": ["suzhou"], "routing_reason": "暖胃 → 苏"}'
            )
        )
        out = _run(route_cuisines(_state("想吃点暖胃的"), provider=provider))
        assert provider.calls, "gray-zone must reach the LLM"
        assert out["selected_cuisines"] == ["suzhou"]

    def test_unknown_cuisine_id_dropped(self) -> None:
        # LLM hallucinates a non-existent cuisine — silently dropped.
        provider = FakeLLMProvider(
            response=_llm_response(
                '{"selected_cuisines": ["suzhou", "atlantis_cuisine"], '
                '"routing_reason": "苏帮菜"}'
            )
        )
        out = _run(route_cuisines(_state("想吃点清淡的"), provider=provider))
        assert "atlantis_cuisine" not in out["selected_cuisines"]
        assert "suzhou" in out["selected_cuisines"]

    def test_bad_json_degrades_with_top1_fallback(self) -> None:
        provider = FakeLLMProvider(response=_llm_response("not json at all"))
        # Seed preferences so top-1 is sichuan.
        prefs = _prefs(cuisine_weights={"sichuan": 1.0, "cantonese": 0.5})
        out = _run(
            route_cuisines(
                _state("想吃点暖胃的", preferences=prefs), provider=provider
            )
        )
        assert out["selected_cuisines"] == ["sichuan"]
        assert any(
            e.get("code") == NO_CUISINE_MATCHED
            for e in out.get("errors", [])
        ), out

    def test_null_selected_cuisines_degrades(self) -> None:
        provider = FakeLLMProvider(
            response=_llm_response(
                '{"selected_cuisines": null, "routing_reason": "?"}'
            )
        )
        prefs = _prefs(cuisine_weights={"hunan": 1.0})
        out = _run(
            route_cuisines(
                _state("想吃点暖胃的", preferences=prefs), provider=provider
            )
        )
        assert out["selected_cuisines"] == ["hunan"]
        assert any(
            e.get("code") == NO_CUISINE_MATCHED for e in out.get("errors", [])
        )

    def test_timeout_degrades_without_raising(self) -> None:
        # Provider that hangs forever — wait_for should time out.
        class _Hangs:
            model = "fake"
            timeout = 0.0
            max_retries = 0

            async def complete(self, request):  # type: ignore[no-untyped-def]
                await asyncio.sleep(ROUTER_LLM_TIMEOUT_SECONDS * 5)
                return _llm_response("unreachable")

        prefs = _prefs(cuisine_weights={"hunan": 1.0})
        out = _run(
            route_cuisines(
                _state("想吃点暖胃的", preferences=prefs),
                provider=_Hangs(),  # type: ignore[arg-type]
            )
        )
        assert out["selected_cuisines"] == ["hunan"]
        assert any(
            e.get("code") == NO_CUISINE_MATCHED for e in out.get("errors", [])
        )

    def test_llm_raises_domain_error_degrades_without_raising(self) -> None:
        class _Explodes:
            model = "fake"
            timeout = 0.0
            max_retries = 0

            async def complete(self, request):  # type: ignore[no-untyped-def]
                raise LLMTimeoutError("fake timeout")

        prefs = _prefs(cuisine_weights={"hunan": 1.0})
        out = _run(
            route_cuisines(
                _state("想吃点暖胃的", preferences=prefs),
                provider=_Explodes(),  # type: ignore[arg-type]
            )
        )
        assert out["selected_cuisines"] == ["hunan"]
        assert any(
            e.get("code") == NO_CUISINE_MATCHED for e in out.get("errors", [])
        )


# ---------------------------------------------------------------------------
# Ambient ("随便") — weighted random sampling
# ---------------------------------------------------------------------------


class TestAmbientSampling:
    def test_ambient_message_uses_rng(self) -> None:
        provider = FakeLLMProvider()
        out_a = _run(
            route_cuisines(
                _state("随便",
                       preferences=_prefs(cuisine_weights={"sichuan": 0.9, "cantonese": 0.1})),
                provider=provider,
                rng=random.Random(2026),
            )
        )
        out_b = _run(
            route_cuisines(
                _state("随便",
                       preferences=_prefs(cuisine_weights={"sichuan": 0.9, "cantonese": 0.1})),
                provider=provider,
                rng=random.Random(2026),
            )
        )
        assert provider.calls == [], "ambient path must not call LLM"
        assert out_a["selected_cuisines"] == out_b["selected_cuisines"]

    def test_high_sichuan_weight_dominates_sampling(self) -> None:
        provider = FakeLLMProvider()
        rng = random.Random(0)
        weights = {"sichuan": 0.9, "cantonese": 0.1, "hunan": 0.1}
        wins = 0
        for _ in range(500):
            out = _run(
                route_cuisines(
                    _state("随便", preferences=_prefs(cuisine_weights=weights)),
                    provider=provider,
                    rng=rng,
                )
            )
            if "sichuan" in out["selected_cuisines"]:
                wins += 1
        # 0.9 / 1.1 ≈ 0.818 → should appear in ≥70% of ambient picks
        # (n ∈ {2,3}, so sample size at least 2 each time).
        assert wins / 500 >= 0.70, wins / 500


# ---------------------------------------------------------------------------
# Allergy filter
# ---------------------------------------------------------------------------


class TestAllergyFilter:
    def test_peanut_allergy_removes_sichuan(self) -> None:
        provider = FakeLLMProvider()
        out = _run(
            route_cuisines(
                _state(
                    "想吃辣的",
                    preferences=_prefs(allergies=["peanut"]),
                ),
                provider=provider,
            )
        )
        assert "sichuan" not in out["selected_cuisines"]
        assert "hunan" in out["selected_cuisines"]

    def test_shellfish_allergy_removes_fujian(self) -> None:
        provider = FakeLLMProvider(
            response=_llm_response(
                '{"selected_cuisines": ["fujian", "suzhou"], "routing_reason": "沿海 → 闽 + 苏"}'
            )
        )
        out = _run(
            route_cuisines(
                _state("想吃点清淡的",
                       preferences=_prefs(allergies=["shellfish"])),
                provider=provider,
            )
        )
        assert "fujian" not in out["selected_cuisines"]
        assert "suzhou" in out["selected_cuisines"]

    def test_unlisted_allergies_are_no_op(self) -> None:
        provider = FakeLLMProvider()
        out = _run(
            route_cuisines(
                _state(
                    "想吃辣的",
                    preferences=_prefs(allergies=["soy", "dairy"]),
                ),
                provider=provider,
            )
        )
        assert "sichuan" in out["selected_cuisines"]
        assert "hunan" in out["selected_cuisines"]

    def test_all_cuisines_filtered_returns_human_copy(self) -> None:
        # Construct a scenario where allergy filter wipes everything.
        # Peanut + western_fastfood + shellfish allergies vs a rule that
        # would otherwise only return sichuan/western_fastfood/fujian.
        provider = FakeLLMProvider()
        out = _run(
            route_cuisines(
                _state(
                    "想吃辣的",
                    preferences=_prefs(allergies=["peanut", "fried_food"]),
                ),
                provider=provider,
            )
        )
        # spicy returns [sichuan, hunan]; peanut removes sichuan, hunan
        # is not in conflict table, so out is ["hunan"] — NOT empty.
        # Force the ALL_CUISINES_FILTERED path with a narrower test:
        provider.calls.clear()
        out2 = _run(
            route_cuisines(
                _state("随便",
                       preferences=_prefs(
                           cuisine_weights={"sichuan": 1.0, "western_fastfood": 1.0},
                           allergies=["peanut", "fried_food"],
                       )),
                provider=provider,
                rng=random.Random(0),
            )
        )
        assert out2["selected_cuisines"] == []
        assert out2["routing_reason"] == "今天没合适的，换个口味吧"
        assert any(
            e.get("code") == ALL_CUISINES_FILTERED
            for e in out2.get("errors", [])
        )


# ---------------------------------------------------------------------------
# Empty / garbage message short-circuit
# ---------------------------------------------------------------------------


class TestEmptyMessageShortCircuit:
    @pytest.mark.parametrize("msg", ["", "   ", "！！！@#￥", "..."])
    def test_empty_or_garbage_returns_empty_message_without_llm(
        self, msg: str
    ) -> None:
        provider = FakeLLMProvider()
        out = _run(route_cuisines(_state(msg), provider=provider))
        assert out["selected_cuisines"] == []
        assert provider.calls == [], f"empty message {msg!r} must not reach LLM"
        assert any(
            e.get("code") == EMPTY_MESSAGE for e in out.get("errors", [])
        ), out


# ---------------------------------------------------------------------------
# Missing user_preferences — degrade to neutral weights
# ---------------------------------------------------------------------------


class TestMissingPreferences:
    def test_missing_prefs_does_not_raise(self) -> None:
        provider = FakeLLMProvider()
        state: AgentState = {
            "user_id": "u-test",
            "user_message": "想吃辣的",
        }  # no user_preferences key
        out = _run(route_cuisines(state, provider=provider))
        # Falls back to neutral weights; rule layer still fires on "辣的".
        assert "sichuan" in out["selected_cuisines"]
        assert "hunan" in out["selected_cuisines"]


# ---------------------------------------------------------------------------
# Routing reason — universal ≤30 codepoint constraint
# ---------------------------------------------------------------------------


class TestRoutingReasonFormat:
    @pytest.mark.parametrize(
        "msg",
        [
            "想吃辣的",
            "清淡的",
            "想吃川菜",
            "随便",
            "想吃清淡的辣菜",
            "想吃点暖胃的",
            "",
        ],
    )
    def test_reason_within_codepoint_limit_on_every_path(self, msg: str) -> None:
        provider = FakeLLMProvider(
            response=_llm_response(
                '{"selected_cuisines": ["suzhou"], "routing_reason": "帮你挑了一份苏帮菜"}'
            )
        )
        out = _run(route_cuisines(_state(msg), provider=provider))
        assert "routing_reason" in out, f"missing routing_reason for {msg!r}"
        # Spec §2: "≤30 字、人话风格". Count codepoints (Python str length)
        # to match the spec wording exactly.
        assert len(out["routing_reason"]) <= 30, (
            f"{msg!r} → routing_reason too long "
            f"({len(out['routing_reason'])} codepoints): {out['routing_reason']!r}"
        )

    def test_llm_long_reason_clipped(self) -> None:
        long_reason = "这" * 50  # 50 codepoints — must be clipped to ≤30
        provider = FakeLLMProvider(
            response=_llm_response(
                f'{{"selected_cuisines": ["suzhou"], "routing_reason": "{long_reason}"}}'
            )
        )
        out = _run(route_cuisines(_state("想吃点暖胃的"), provider=provider))
        assert len(out["routing_reason"]) <= 30


# ---------------------------------------------------------------------------
# routing_log shape + rule-layer elapsed_ms budget
# ---------------------------------------------------------------------------


class TestRoutingLog:
    def test_log_entries_have_required_fields(self) -> None:
        provider = FakeLLMProvider()
        out = _run(route_cuisines(_state("想吃辣的"), provider=provider))
        log = out.get("routing_log", [])
        assert log, "expected at least one log entry"
        for entry in log:
            assert set(entry.keys()) >= {"ts", "layer", "detail", "elapsed_ms"}

    def test_rule_layer_elapsed_ms_under_budget(self) -> None:
        provider = FakeLLMProvider()
        out = _run(route_cuisines(_state("想吃辣的"), provider=provider))
        rule_entries = [
            e for e in out.get("routing_log", []) if e.get("layer") == "rule"
        ]
        assert rule_entries, "expected a rule-layer log entry"
        for entry in rule_entries:
            assert entry["elapsed_ms"] < 100, (
                f"rule layer took {entry['elapsed_ms']}ms — over the 100ms budget"
            )

    def test_log_entry_types(self) -> None:
        # TypedDict shape check — works under mypy --strict.
        provider = FakeLLMProvider()
        out = _run(route_cuisines(_state("想吃辣的"), provider=provider))
        entry: RoutingLogEntry = out["routing_log"][0]  # type: ignore[typeddict-item]
        assert isinstance(entry["layer"], str)
        assert isinstance(entry["detail"], str)
        assert isinstance(entry["elapsed_ms"], int)
