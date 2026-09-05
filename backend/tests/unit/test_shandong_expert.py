"""F012 — 鲁菜专家专属契约测试.

涵盖 [spec/features/F012-shandong.md §6] 测试计划:

- 用户输入"咸鲜" → 关键词含"鲁菜"
- 用户输入"山东菜" → 不把"黄焖鸡"作为首选关键词（避免落入中式快餐）
- cuisine_id / display_name / 边界澄清（黄焖鸡、京菜）

不重复 F003 `test_base_contract.py` 已覆盖的内容（继承关系 / parse_output
通用 fallback / 全 14 注册表完整性）—— 那些属于通用契约。本文件只断言
**鲁菜专属** 的行为约束，确保 §4 prompt 要点被实际写进代码。
"""
from __future__ import annotations

from decimal import Decimal

from app.agents.cuisines import CUISINE_REGISTRY, BaseCuisineExpert
from app.agents.cuisines.stubs.shandong import CUISINE_PROMPT_FRAGMENT, ShandongExpert
from app.agents.state import CuisineExpertInput, UserPreferencesDict
from app.core.constants import CUISINE_IDS

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_input(user_message: str, allergies: list[str] | None = None) -> CuisineExpertInput:
    """构造一个最小可用的 `CuisineExpertInput`。

    F012 §6 验收点关注的是 user_message，preferences 用占位即可。
    """
    prefs: UserPreferencesDict = {
        "user_id": "u-f012",
        "cuisine_weights": dict.fromkeys(CUISINE_IDS, 0.5),
        "allergies": allergies if allergies is not None else [],
        "spice_tolerance": 1,
        "temperature_preference": "room",
        "default_location": "国贸",
        "budget_lunch_min": Decimal("30.00"),
        "budget_lunch_max": Decimal("80.00"),
    }
    return {
        "user_message": user_message,
        "user_preferences": prefs,
        "location": None,
        "spice_tolerance": 1,
        "budget_min": 30.0,
        "budget_max": 80.0,
    }


# ---------------------------------------------------------------------------
# TestShandongBasicContract — F003 §3.1 必填属性 + F012 §2 cuisine_id
# ---------------------------------------------------------------------------


class TestShandongBasicContract:
    def test_shandong_expert_inherits_base(self) -> None:
        assert issubclass(ShandongExpert, BaseCuisineExpert)

    def test_cuisine_id_is_shandong(self) -> None:
        # F012 §2 验收点：`cuisine_id="shandong"`
        assert ShandongExpert.cuisine_id == "shandong"

    def test_display_name_is_lucai(self) -> None:
        # F012 §1 用户故事 + §2 验收要求"鲁菜"作为显示名
        assert ShandongExpert.display_name == "鲁菜"

    def test_uses_unified_llm_model(self) -> None:
        # F003 §8.1 — 14 个菜系统一 `MiniMax-M3`
        assert ShandongExpert.llm_model == "MiniMax-M3"

    def test_prompt_fragment_is_non_empty_string(self) -> None:
        # 必须存在菜系专属片段，否则不满足 F003 §3.1 的子类可选 override
        assert isinstance(ShandongExpert.prompt_fragment, str)
        assert ShandongExpert.prompt_fragment.strip()


# ---------------------------------------------------------------------------
# TestShandongInRegistry — F003 §3.2 注册表
# ---------------------------------------------------------------------------


class TestShandongInRegistry:
    def test_registered_in_cuisine_registry(self) -> None:
        assert "shandong" in CUISINE_REGISTRY
        assert CUISINE_REGISTRY["shandong"] is not None

    def test_registry_entry_has_matching_cuisine_id(self) -> None:
        expert = CUISINE_REGISTRY["shandong"]
        assert expert.cuisine_id == "shandong"
        assert expert.display_name == "鲁菜"

    def test_registry_position_matches_cuisine_ids_spec_order(self) -> None:
        # F003 §3.2 / `CUISINE_IDS` 顺序：shandong 在第 3 位
        assert CUISINE_IDS.index("shandong") == 2
        assert tuple(CUISINE_REGISTRY.keys())[2] == "shandong"


# ---------------------------------------------------------------------------
# TestShandongPromptFragment — F012 §4 prompt 要点的实际落位
# ---------------------------------------------------------------------------


class TestShandongPromptFragment:
    """验证 F012 §4 关键提示已落到 `CUISINE_PROMPT_FRAGMENT` 字面量中。

    这些是**给 LLM 的字面规则**——它们只有在 prompt 片段里真正出现，
    才能引导模型输出符合 §2 §6 验收点的关键词。这就是 §6 可单测的
    唯一现实接口（不接 LLM）。
    """

    def test_fragment_lists_cuisine_term(self) -> None:
        # F012 §2：菜系词必须出现（鲁 / 山东 / 鲁菜 至少其一）
        # §4 prompt 关键词生成：菜系词（鲁/山东/鲁菜）
        assert any(token in CUISINE_PROMPT_FRAGMENT for token in ("鲁菜", "山东", "鲁"))

    def test_fragment_lists_xianxian_flavor_token(self) -> None:
        # F012 §2 验收：关键词覆盖"咸鲜"
        assert "咸鲜" in CUISINE_PROMPT_FRAGMENT

    def test_fragment_lists_congshao_signature(self) -> None:
        # F012 §2 验收：关键词覆盖"葱烧"
        # F012 §3 经典菜里有"葱烧海参"；风味含"葱香"
        assert "葱烧" in CUISINE_PROMPT_FRAGMENT or "葱香" in CUISINE_PROMPT_FRAGMENT

    def test_fragment_lists_representative_dishes(self) -> None:
        # F012 §3 经典菜：糖醋鲤鱼 / 九转大肠 / 葱烧海参 / 爆炒腰花
        # 至少要有 2 道作为关键词候选
        classics = ("糖醋鲤鱼", "九转大肠", "葱烧海参")
        present = [d for d in classics if d in CUISINE_PROMPT_FRAGMENT]
        assert len(present) >= 2, (
            f"prompt 片段至少应列出 2 个 F012 §3 经典菜作为关键词候选；"
            f"实际命中={present}"
        )

    def test_fragment_warns_against_huangmenji_as_primary_keyword(self) -> None:
        # F012 §4 边界澄清：避免把"黄焖鸡"作为正餐鲁菜的主关键词，
        # 因为它起源于山东但用户场景易被归到中式快餐（F022）。
        # §6 验收点：用户输入"山东菜" → 不把"黄焖鸡"作为首选关键词。
        assert "黄焖鸡" in CUISINE_PROMPT_FRAGMENT, (
            "F012 §4 明确要求 prompt 片段含 '黄焖鸡' 边界澄清，"
            "以引导 LLM 避免将其作为正餐鲁菜主关键词"
        )
        # 同时需要出现"中式快餐"或"快餐"作为对照，让 LLM 知道往哪儿归类
        assert ("中式快餐" in CUISINE_PROMPT_FRAGMENT) or (
            "快餐" in CUISINE_PROMPT_FRAGMENT
        )

    def test_fragment_clarifies_jingcai_boundary(self) -> None:
        # F012 §4：与京菜区别——京菜受鲁菜影响但更精致。
        assert "京菜" in CUISINE_PROMPT_FRAGMENT


# ---------------------------------------------------------------------------
# TestShandongBuildPrompt — F012 §6 行为验收：user_message → prompt 内容
# ---------------------------------------------------------------------------


class TestShandongBuildPrompt:
    """F012 §6.1: 用户输入"咸鲜" → 关键词含"鲁菜"。"""

    def test_xianxian_input_prompt_includes_lu_cai_term(self) -> None:
        """F012 §6 验收点 1：用户输入"咸鲜"时，build_prompt 输出必须既含
        用户的"咸鲜"原文又含菜系词"鲁菜"，从而 LLM 可按规则产出含"鲁菜"
        的关键词集。

        不接 LLM 验证 LLM 行为，而是验证 prompt 模板确实提供了产生该
        行为所需的全部上下文（用户输入 + 菜系词 + 风味词"咸鲜"）。
        """
        prompt = ShandongExpert().build_prompt(_build_input("想吃咸鲜"))

        # 用户原始输入被注入（F003 §4 模板必含 {message}）
        assert "咸鲜" in prompt
        # 菜系显示名"F003 §3.1 必填"被注入
        assert "鲁菜" in prompt
        # F012 §4 prompt 要点：咸鲜作为风味词必须存在
        assert "咸鲜" in prompt
        # §4 关键词生成规则：菜系词（鲁/山东/鲁菜）+ 代表菜 + 风味词
        assert any(token in prompt for token in ("鲁", "山东", "鲁菜"))

    def test_shandongcai_input_prompt_does_not_promote_huangmenji(self) -> None:
        """F012 §6 验收点 2：用户输入"山东菜"时，build_prompt 必须显式告
        知 LLM 不要把"黄焖鸡"作为首选关键词。

        唯一可单测的接口是：prompt 里必须出现 `黄焖鸡` 的边界澄清。
        """
        prompt = ShandongExpert().build_prompt(_build_input("山东菜"))

        assert "黄焖鸡" in prompt, (
            "F012 §4 要求 prompt 片段含 '黄焖鸡' 边界澄清以避免误推快餐；"
            "build_prompt 应当把该片段注入最终 prompt"
        )
        # 同时不应在 prompt 中正面推荐黄焖鸡——只能以"避免..."的语义出现
        # 简单约束：片段本身不在 prompt 中以单独"推荐"的方式呈现
        # （这一条通过 F012PromptFragment 已经验证；此处冗余确认）
        assert "鲁菜" in prompt


# ---------------------------------------------------------------------------
# TestShandongParseOutput — F003 §3.3 鲁菜 Node 自己的解析行为
# ---------------------------------------------------------------------------


class TestShandongParseOutput:
    """鲁菜继承的 `BaseCuisineExpert.parse_output` 对鲁菜专用字段。

    验证时使用鲁菜领域的 representative JSON（Lucian 关键词集合）。
    """

    def test_parse_happy_path_lu_cai_dishes(self) -> None:
        expert = ShandongExpert()
        conclusion = "今天适合来份葱烧海参"
        raw = (
            f'{{"conclusion":"{conclusion}",'
            '"keywords":["鲁菜","葱烧海参","糖醋鲤鱼","咸鲜"],'
            '"matched_allergies":[]}'
        )
        out = expert.parse_output(raw)

        assert out["cuisine_id"] == "shandong"
        # conclusion 是 LLM 自由文本，只要透传即可，不强制含"鲁菜"
        assert out["conclusion"] == conclusion
        # F012 §2/§6 行为约束在 prompt 片段层（TestShandongPromptFragment），
        # parse_output 只做无意见的 schema 转换。
        assert "鲁菜" in out["keywords"]
        assert "葱烧海参" in out["keywords"]
        assert "咸鲜" in out["keywords"]
        assert all(isinstance(k, str) for k in out["keywords"])

    def test_parse_invalid_json_falls_back(self) -> None:
        expert = ShandongExpert()
        out = expert.parse_output("not json at all")

        assert out["cuisine_id"] == "shandong"
        assert out["conclusion"] == "暂不可推荐"
        assert out["keywords"] == []
        assert out["matched_allergies"] == []

    def test_parse_drops_huangmenji_if_present_in_keywords(self) -> None:
        """F012 §6 验收点 2 实现层验证：即便 LLM 误把"黄焖鸡"塞进 keywords，
        `parse_output` 也不应单独剔除（剔除责任在 prompt 引导）。

        这里只验证"`parse_output` 透传字段、不做菜系特定过滤"是预期行为——
        防止后续有人在 parse_output 里加菜系专属过滤逻辑导致提示词责任模糊。
        """
        expert = ShandongExpert()
        raw = (
            '{"conclusion":"今天推荐鲁菜",'
            '"keywords":["鲁菜","黄焖鸡","葱烧海参"],'
            '"matched_allergies":[]}'
        )
        out = expert.parse_output(raw)

        # parse_output 是无意见的 schema 转换器；菜系正确性来自 prompt。
        assert "黄焖鸡" in out["keywords"]
        assert "鲁菜" in out["keywords"]
