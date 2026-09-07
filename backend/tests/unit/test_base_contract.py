"""Unit tests for the F003 cuisine expert contract.

Per `spec/features/F003-cuisine-expert-contract.md` §6, this single file
covers:
- `TestBaseContract` — ABC behaviour, parse_output happy + fallback
- `TestRegistry` — registry completeness, lookup, ordering
- `TestPromptTemplate` — placeholder rendering, 中文 hard constraint
"""
from __future__ import annotations

from decimal import Decimal

import pytest
from app.agents.cuisines import (
    CUISINE_REGISTRY,
    BaseCuisineExpert,
    assert_registry_complete,
)
from app.agents.cuisines.prompts.base import render_base_prompt
from app.agents.cuisines.registry import CUISINE_REGISTRY as REG
from app.agents.cuisines.stubs.sichuan import SichuanExpert
from app.agents.state import CuisineExpertInput, UserPreferencesDict
from app.core.constants import CUISINE_IDS


# A representative input that covers all renderable fields.
def _input() -> CuisineExpertInput:
    prefs: UserPreferencesDict = {
        "user_id": "u",
        "cuisine_weights": dict.fromkeys(CUISINE_IDS, 0.5),
        "allergies": ["peanut", "shellfish"],
        "spice_tolerance": 2,
        "temperature_preference": "room",
        "default_location": "国贸",
        "budget_lunch_min": Decimal("30.00"),
        "budget_lunch_max": Decimal("80.00"),
    }
    return {
        "user_message": "想吃辣",
        "user_preferences": prefs,
        "location": None,
        "spice_tolerance": 2,
        "budget_min": 30.0,
        "budget_max": 80.0,
    }


# ---------------------------------------------------------------------------
# TestBaseContract
# ---------------------------------------------------------------------------


class TestBaseContract:
    def test_sichuan_stub_subclasses_abc(self) -> None:
        assert issubclass(SichuanExpert, BaseCuisineExpert)

    def test_sichuan_stub_required_attrs(self) -> None:
        expert = SichuanExpert()
        assert expert.cuisine_id == "sichuan"
        assert expert.display_name == "川菜"
        assert expert.llm_model == "MiniMax-M3"
        assert isinstance(expert.prompt_fragment, str)

    def test_run_calls_llm_and_returns_parsed_output(self) -> None:
        """F003 Phase 2 — base class.run() 现在调真实 LLM (2026-09-07 落地).

        用 `FakeLLMProvider` 注入回包, 验证:
        - prompt 含菜系显示名 + 用户消息 + JSON schema 提示
        - parse_output 把 LLM 回包 → CuisineExpertOutput
        - cuisine_id 由 expert.cuisine_id 提供, 不依赖 LLM 自报
        """
        import asyncio
        from unittest.mock import patch

        from app.agents.llm.testing import FakeLLMProvider

        fake = FakeLLMProvider()
        fake.set_response({
            "content": (
                '{"conclusion":"今天适合川菜",'
                '"keywords":["川菜","麻婆豆腐"],'
                '"matched_allergies":[]}'
            ),
            "model": "fake",
            "usage": None,
        })
        # base.py 用了 `from app.agents.llm.factory import get_llm_provider`,
        # 所以 `app.agents.cuisines.base.get_llm_provider` 才是真正被查找的位置
        with patch("app.agents.cuisines.base.get_llm_provider", return_value=fake):
            result = asyncio.run(
                SichuanExpert().run({
                    "user_id": "u",
                    "user_message": "想吃辣",
                    "user_preferences": _input()["user_preferences"],
                })
            )

        assert result["cuisine_id"] == "sichuan"
        assert "川菜" in result["conclusion"]
        assert result["keywords"] == ["川菜", "麻婆豆腐"]
        # 验证 prompt 被实际发送
        assert fake.calls, "LLM 没被调用"
        prompt_text = fake.calls[0]["messages"][1]["content"]
        assert "想吃辣" in prompt_text
        assert "川菜" in prompt_text  # cuisine_display_name

    def test_run_llm_error_falls_back(self) -> None:
        """F003 Phase 2 — LLM 抛错时 run() 不抛, 返回 fallback keywords=[]."""
        import asyncio
        from unittest.mock import patch

        from app.agents.llm.testing import FakeLLMProvider
        from app.core.exceptions import LLMRateLimitError

        class BoomProvider(FakeLLMProvider):
            async def complete(self, request):  # type: ignore[override]
                raise LLMRateLimitError("boom", details={})

        with patch(
            "app.agents.cuisines.base.get_llm_provider",
            return_value=BoomProvider(),
        ):
            result = asyncio.run(
                SichuanExpert().run({
                    "user_id": "u",
                    "user_message": "hi",
                    "user_preferences": _input()["user_preferences"],
                })
            )

        assert result["cuisine_id"] == "sichuan"
        assert result["keywords"] == []  # fallback
        assert result["conclusion"] == "暂不可推荐"

    def test_parse_output_happy_path(self) -> None:
        expert = SichuanExpert()
        raw = (
            '{"conclusion":"今天适合推荐川菜",'
            '"keywords":["川菜","麻婆豆腐","回锅肉","麻辣"],'
            '"matched_allergies":["peanut"]}'
        )
        out = expert.parse_output(raw)

        assert out["cuisine_id"] == "sichuan"
        assert "川菜" in out["conclusion"]
        assert out["keywords"] == ["川菜", "麻婆豆腐", "回锅肉", "麻辣"]
        assert out["matched_allergies"] == ["peanut"]

    def test_parse_output_invalid_json_returns_fallback(self) -> None:
        expert = SichuanExpert()
        out = expert.parse_output("not json at all")

        assert out["cuisine_id"] == "sichuan"
        assert out["conclusion"] == "暂不可推荐"
        assert out["keywords"] == []
        assert out["matched_allergies"] == []

    def test_parse_output_non_dict_json_returns_fallback(self) -> None:
        expert = SichuanExpert()
        out = expert.parse_output("[1, 2, 3]")

        assert out["keywords"] == []
        assert out["conclusion"] == "暂不可推荐"

    def test_parse_output_missing_fields_uses_fallback(self) -> None:
        expert = SichuanExpert()
        # `conclusion` and `keywords` are both missing → invalid structure
        # should still produce an empty fallback rather than raising.
        out = expert.parse_output('{"unrelated": true}')

        assert out["cuisine_id"] == "sichuan"
        assert out["conclusion"] == ""  # data.get default
        assert out["keywords"] == []
        assert out["matched_allergies"] == []


# ---------------------------------------------------------------------------
# TestRegistry
# ---------------------------------------------------------------------------


class TestRegistry:
    def test_registry_has_all_14_cuisines(self) -> None:
        assert set(REG.keys()) == set(CUISINE_IDS)
        assert len(REG) == 14

    def test_registry_values_are_expert_instances(self) -> None:
        for cuisine_id, expert in REG.items():
            assert isinstance(expert, BaseCuisineExpert), cuisine_id
            assert expert.cuisine_id == cuisine_id

    def test_registry_lookup_by_cuisine_id(self) -> None:
        assert CUISINE_REGISTRY["sichuan"].display_name == "川菜"
        with pytest.raises(KeyError):
            CUISINE_REGISTRY["nonexistent"]

    def test_registry_keys_in_spec_order(self) -> None:
        # Order matters for UI stability (M2+).
        assert tuple(REG.keys()) == CUISINE_IDS

    def test_assert_registry_complete_passes_for_current_spec(self) -> None:
        # Will raise AssertionError if registry drift exists.
        assert_registry_complete()

    def test_all_cuisines_use_unified_llm_model(self) -> None:
        for expert in REG.values():
            assert expert.llm_model == "MiniMax-M3"


# ---------------------------------------------------------------------------
# TestPromptTemplate
# ---------------------------------------------------------------------------


class TestPromptTemplate:
    def test_render_base_prompt_includes_all_sections(self) -> None:
        prompt = render_base_prompt("川菜", "代表菜：麻婆豆腐", _input())

        assert "川菜" in prompt
        assert "想吃辣" in prompt
        assert "国贸" in prompt  # location
        assert "中辣" in prompt  # spice label
        assert "30.00-80.00" in prompt or "30-80" in prompt  # budget label

    def test_render_base_prompt_includes_hard_constraint_chinese_only(self) -> None:
        prompt = render_base_prompt("川菜", "代表菜：x", _input())
        assert "禁止英文" in prompt
        assert "硬约束" in prompt

    def test_render_base_prompt_handles_missing_budget(self) -> None:
        inp = _input()
        inp["user_preferences"]["budget_lunch_min"] = None
        inp["user_preferences"]["budget_lunch_max"] = None
        prompt = render_base_prompt("川菜", "", inp)
        assert "不限" in prompt

    def test_render_base_prompt_no_allergies_says_wu(self) -> None:
        inp = _input()
        inp["user_preferences"]["allergies"] = []
        prompt = render_base_prompt("川菜", "", inp)
        assert "无" in prompt

    def test_stub_prompt_fragment_is_present_in_rendered_output(self) -> None:
        # The fragment is per-cuisine — verify it actually gets injected.
        prompt = SichuanExpert().build_prompt(_input())
        assert "代表菜" in prompt
        assert "麻婆豆腐" in prompt  # from SichuanExpert.prompt_fragment