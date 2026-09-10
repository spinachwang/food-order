"""Unit tests for F010 — 川菜专家 (Sichuan cuisine expert).

Per `spec/features/F010-sichuan.md` §6:
- mock LLM 返回合法 JSON → `parse_output` 字段正确
- 关键词必含 "川菜" + 至少 2 个代表菜
- 花生过敏用户消息 → `matched_allergies` 含 `"peanut"`

Parallel-trigger integration is covered by F003 `test_cuisine_parallel.py`.
"""

from __future__ import annotations

import json
from decimal import Decimal

import pytest
from app.agents.cuisines.base import BaseCuisineExpert
from app.agents.cuisines.prompts.sichuan import SIGNATURE_DISHES
from app.agents.cuisines.registry import CUISINE_REGISTRY
from app.agents.cuisines.sichuan import SichuanExpert
from app.agents.state import CuisineExpertInput, UserPreferencesDict
from app.core.constants import CUISINE_IDS


def _make_input(*, allergies: list[str] | None = None) -> CuisineExpertInput:
    """构造一个代表所有可渲染字段的输入."""
    prefs: UserPreferencesDict = {
        "user_id": "u",
        "cuisine_weights": dict.fromkeys(CUISINE_IDS, 0.5),
        "allergies": allergies or [],
        "spice_tolerance": 2,
        "temperature_preference": "room",
        "default_location": "国贸",
        "budget_lunch_min": Decimal("30.00"),
        "budget_lunch_max": Decimal("80.00"),
    }
    return {
        "user_message": "今天想吃川菜",
        "user_preferences": prefs,
        "location": None,
        "spice_tolerance": 2,
        "budget_min": 30.0,
        "budget_max": 80.0,
    }


# ---------------------------------------------------------------------------
# Identity — F010 §2 验收 1
# ---------------------------------------------------------------------------


class TestSichuanIdentity:
    def test_subclasses_base_cuisine_expert(self) -> None:
        assert issubclass(SichuanExpert, BaseCuisineExpert)

    def test_cuisine_id_is_sichuan(self) -> None:
        assert SichuanExpert().cuisine_id == "sichuan"

    def test_display_name_is_chinese(self) -> None:
        assert SichuanExpert().display_name == "川菜"

    def test_uses_unified_llm_model(self) -> None:
        """F003 §8.1 — 所有菜系统一使用 MiniMax-M3."""
        assert SichuanExpert().llm_model == "MiniMax-M3"


# ---------------------------------------------------------------------------
# Prompt fragment — F010 §4 内容校验
# ---------------------------------------------------------------------------


class TestSichuanPromptFragment:
    def test_explicit_peanut_oil_warning(self) -> None:
        """F010 §4 + §2: 必须显式标注'川菜常含花生油'."""
        fragment = SichuanExpert().prompt_fragment
        # LOW-1 fix: 直接断言 "花生油" (而非仅 "花生"), 避免被 "花生碎" 误满足.
        assert "花生油" in fragment

    def test_distinguishes_from_hunan_by_mala(self) -> None:
        """F010 §4: 与湘菜区别 — 川偏'麻', 湘偏'辣'."""
        fragment = SichuanExpert().prompt_fragment
        assert "湘" in fragment
        assert "麻" in fragment
        assert "辣" in fragment

    def test_distinguishes_from_anhui(self) -> None:
        """F010 §4: 与徽菜区别 — 共享重油但徽菜偏咸鲜."""
        fragment = SichuanExpert().prompt_fragment
        assert "徽" in fragment
        assert "咸鲜" in fragment
        # LOW-2 fix: 显式断言 "重油" 共享属性, 防止 prompt 退化为仅 "川菜偏麻辣".
        assert "重油" in fragment

    def test_prompt_includes_allergen_action_directive(self) -> None:
        """F010 §2 验收 3 + 扩展: 必须给出可执行的 LLM 过敏原动作指令."""
        fragment = SichuanExpert().prompt_fragment
        # 当用户有 peanut 过敏时, LLM 必须在 matched_allergies 中输出 "peanut".
        assert "matched_allergies" in fragment
        assert "peanut" in fragment

    def test_contains_all_signature_dishes(self) -> None:
        """F010 §3: 14 道代表菜全部出现在 prompt_fragment."""
        fragment = SichuanExpert().prompt_fragment
        for dish in SIGNATURE_DISHES:
            assert dish in fragment, f"代表菜 {dish!r} 未出现在 prompt_fragment 中"

    def test_signature_dishes_binds_to_class(self) -> None:
        """MED-2 fix: 类属性 `signature_dishes` 必须绑定到 SIGNATURE_DISHES."""
        # 通过类访问与实例访问结果一致, 且指向同一 tuple 对象
        assert SichuanExpert.signature_dishes is SIGNATURE_DISHES
        assert SichuanExpert().signature_dishes is SIGNATURE_DISHES
        # tuple 本身不可变 (无需依赖类的 frozen 语义)
        assert isinstance(SIGNATURE_DISHES, tuple)
        with pytest.raises(TypeError):
            SIGNATURE_DISHES[0] = "其它菜"  # type: ignore[index]

    def test_includes_keyword_generation_rule(self) -> None:
        """F010 §4: 关键词必须含 1 菜系词 + 2-3 代表菜 + 1-2 风味词."""
        fragment = SichuanExpert().prompt_fragment
        assert "菜系词" in fragment
        assert "代表菜" in fragment
        assert "风味" in fragment

    def test_includes_distance_ranking_guidance(self) -> None:
        """F010 §4: 餐厅按距离 + 评分排序, 距离超 2km 降权."""
        fragment = SichuanExpert().prompt_fragment
        assert "距离" in fragment
        assert "评分" in fragment
        assert "2km" in fragment or "2 km" in fragment


# ---------------------------------------------------------------------------
# parse_output — F010 §6 (mock LLM)
# ---------------------------------------------------------------------------


class TestSichuanParseOutput:
    def test_happy_path_extracts_all_fields(self) -> None:
        """F010 §6: mock LLM 返回合法 JSON → parse_output 字段正确."""
        expert = SichuanExpert()
        raw = (
            '{"conclusion":"今天适合推荐川菜,麻婆豆腐是不错的选择",'
            '"keywords":["川菜","麻婆豆腐","回锅肉","麻辣","花椒"],'
            '"matched_allergies":["peanut"]}'
        )
        out = expert.parse_output(raw)

        assert out["cuisine_id"] == "sichuan"
        assert "川菜" in out["conclusion"]
        assert out["keywords"] == ["川菜", "麻婆豆腐", "回锅肉", "麻辣", "花椒"]
        assert out["matched_allergies"] == ["peanut"]

    def test_keywords_cover_cuisine_term_dishes_and_flavor(self) -> None:
        """F010 §6: 关键词必含'川菜'+ 至少 2 个代表菜 + 至少 1 个风味词.

        模拟 LLM 按 prompt 规则输出的合规 JSON.
        """
        expert = SichuanExpert()
        sig_subset = list(SIGNATURE_DISHES)[:3]  # 麻婆豆腐, 回锅肉, 水煮鱼
        keywords = ["川菜", *sig_subset, "麻辣", "花椒"]
        raw = json.dumps(
            {"conclusion": "x", "keywords": keywords, "matched_allergies": []},
            ensure_ascii=False,
        )
        out = expert.parse_output(raw)

        # 1) 菜系词
        assert "川菜" in out["keywords"]
        # 2) 至少 2 个代表菜
        dish_keywords = [k for k in out["keywords"] if k in SIGNATURE_DISHES]
        assert len(dish_keywords) >= 2
        # 3) 至少 1 个风味词
        flavor_keywords = {"麻辣", "花椒", "火锅", "鲜香", "糊辣", "鱼香"}
        assert any(k in flavor_keywords for k in out["keywords"])

    def test_peanut_allergy_user_produces_peanut_match(self) -> None:
        """F010 §6: 花生过敏用户消息 → matched_allergies 含 'peanut'.

        模拟 LLM 看到用户花生过敏后的合规输出.
        """
        expert = SichuanExpert()
        raw = (
            '{"conclusion":"川菜常用花生油,花生过敏需注意",'
            '"keywords":["川菜","麻辣火锅","麻辣"],'
            '"matched_allergies":["peanut"]}'
        )
        out = expert.parse_output(raw)
        assert "peanut" in out["matched_allergies"]

    def test_invalid_json_falls_back_gracefully(self) -> None:
        """F003 §3.3: LLM 返回非法 JSON 时降级到 fallback 输出."""
        expert = SichuanExpert()
        out = expert.parse_output("not valid json {{{")
        assert out["cuisine_id"] == "sichuan"
        assert out["conclusion"] == "暂不可推荐"
        assert out["keywords"] == []
        assert out["matched_allergies"] == []


# ---------------------------------------------------------------------------
# build_prompt — F010 §4 与 F003 §4 模板组合校验
# ---------------------------------------------------------------------------


class TestSichuanBuildPrompt:
    def test_peanut_allergy_surfaced_in_prompt(self) -> None:
        """用户花生过敏时, 该信息应在 prompt 中对 LLM 可见."""
        inp = _make_input(allergies=["peanut"])
        prompt = SichuanExpert().build_prompt(inp)
        assert "peanut" in prompt

    def test_cuisine_specific_guidance_in_rendered_prompt(self) -> None:
        """菜系专属片段被注入到渲染后的 prompt 中."""
        inp = _make_input()
        prompt = SichuanExpert().build_prompt(inp)
        assert "麻婆豆腐" in prompt
        assert "花椒" in prompt


# ---------------------------------------------------------------------------
# Registry — F010 §5
# ---------------------------------------------------------------------------


class TestSichuanRegistry:
    def test_sichuan_registered(self) -> None:
        assert "sichuan" in CUISINE_REGISTRY
        assert isinstance(CUISINE_REGISTRY["sichuan"], SichuanExpert)

    def test_registry_lookup_returns_sichuan_expert(self) -> None:
        expert = CUISINE_REGISTRY["sichuan"]
        assert expert.display_name == "川菜"
        assert expert.cuisine_id == "sichuan"
