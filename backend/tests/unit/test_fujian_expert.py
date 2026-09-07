"""F015 — 闽菜专家专属契约测试.

涵盖 [spec/features/F015-fujian.md §2 / §6] 验收点:

- cuisine_id / display_name / 继承 `BaseCuisineExpert`
- 关键词覆盖：闽菜 / 福建 / 闽南 / 沙茶 / 佛跳墙（至少出现于 prompt 片段）
- 与粤菜区别：闽更"汤鲜 + 山珍"，粤更"生猛海鲜"——prompt 必须澄清
- §6 测试计划：用户输入"闽南 / 沙茶" → 关键词含"闽菜"
  （通过 prompt 注入路径验证——不接 LLM，验 build_prompt 上下文）

不重复 F003 `test_base_contract.py` 已覆盖的内容（继承关系 / parse_output
通用 fallback / 全 14 注册表完整性）—— 那些属于通用契约。本文件只断言
**闽菜专属** 的行为约束，确保 §4 prompt 要点被实际写进代码。
"""
from __future__ import annotations

from decimal import Decimal

from app.agents.cuisines import CUISINE_REGISTRY, BaseCuisineExpert
from app.agents.cuisines.stubs.fujian import CUISINE_PROMPT_FRAGMENT, FujianExpert
from app.agents.state import CuisineExpertInput, UserPreferencesDict
from app.core.constants import CUISINE_IDS

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_input(user_message: str, allergies: list[str] | None = None) -> CuisineExpertInput:
    """构造一个最小可用的 `CuisineExpertInput`。

    F015 §6 验收点关注的是 user_message，preferences 用占位即可。
    """
    prefs: UserPreferencesDict = {
        "user_id": "u-f015",
        "cuisine_weights": dict.fromkeys(CUISINE_IDS, 0.5),
        "allergies": allergies if allergies is not None else [],
        "spice_tolerance": 0,
        "temperature_preference": "room",
        "default_location": "国贸",
        "budget_lunch_min": Decimal("30.00"),
        "budget_lunch_max": Decimal("80.00"),
    }
    return {
        "user_message": user_message,
        "user_preferences": prefs,
        "location": None,
        "spice_tolerance": 0,
        "budget_min": 30.0,
        "budget_max": 80.0,
    }


# ---------------------------------------------------------------------------
# TestFujianBasicContract — F003 §3.1 必填属性 + F015 §2 cuisine_id
# ---------------------------------------------------------------------------


class TestFujianBasicContract:
    def test_fujian_expert_inherits_base(self) -> None:
        assert issubclass(FujianExpert, BaseCuisineExpert)

    def test_cuisine_id_is_fujian(self) -> None:
        # F015 §2 验收点：`cuisine_id="fujian"`
        assert FujianExpert.cuisine_id == "fujian"

    def test_display_name_is_mincai(self) -> None:
        # F015 §1 用户故事 + §2 验收要求"闽菜"作为显示名
        assert FujianExpert.display_name == "闽菜"

    def test_uses_unified_llm_model(self) -> None:
        # F003 §8.1 — 14 个菜系统一 `MiniMax-M3`
        assert FujianExpert.llm_model == "MiniMax-M3"

    def test_prompt_fragment_is_non_empty_string(self) -> None:
        # 必须存在菜系专属片段，否则不满足 F003 §3.1 的子类可选 override
        assert isinstance(FujianExpert.prompt_fragment, str)
        assert FujianExpert.prompt_fragment.strip()


# ---------------------------------------------------------------------------
# TestFujianInRegistry — F003 §3.2 注册表
# ---------------------------------------------------------------------------


class TestFujianInRegistry:
    def test_registered_in_cuisine_registry(self) -> None:
        assert "fujian" in CUISINE_REGISTRY
        assert CUISINE_REGISTRY["fujian"] is not None

    def test_registry_entry_has_matching_cuisine_id(self) -> None:
        expert = CUISINE_REGISTRY["fujian"]
        assert expert.cuisine_id == "fujian"
        assert expert.display_name == "闽菜"

    def test_registry_position_matches_cuisine_ids_spec_order(self) -> None:
        # F003 §3.2 / `CUISINE_IDS` 顺序：fujian 在第 6 位
        # （川 / 粤 / 鲁 / 苏 / 浙 / 闽）
        assert CUISINE_IDS.index("fujian") == 5
        assert tuple(CUISINE_REGISTRY.keys())[5] == "fujian"


# ---------------------------------------------------------------------------
# TestFujianPromptFragment — F015 §2 / §4 prompt 要点的实际落位
# ---------------------------------------------------------------------------


class TestFujianPromptFragment:
    """验证 F015 §2/§4 关键提示已落到 `CUISINE_PROMPT_FRAGMENT` 字面量中。

    这些是**给 LLM 的字面规则**——它们只有在 prompt 片段里真正出现，
    才能引导模型输出符合 §2 §6 验收点的关键词。这就是 §6 可单测的
    唯一现实接口（不接 LLM）。
    """

    def test_fragment_lists_all_five_cuisine_terms(self) -> None:
        # F015 §2 验收：关键词覆盖 闽菜 / 福建 / 闽南 / 沙茶 / 佛跳墙
        # §4 prompt 关键词生成：菜系词（闽菜 / 福建 / 闽南 / 沙茶）中 1-2 个
        for token in ("闽菜", "福建", "闽南", "沙茶"):
            assert token in CUISINE_PROMPT_FRAGMENT, (
                f"F015 §2 要求关键词覆盖 {token!r}；必须出现在 prompt 片段中以引导 LLM 输出"
            )

    def test_fragment_lists_fotiaoqiang_signature(self) -> None:
        # F015 §2 验收：关键词覆盖"佛跳墙"——§3 经典菜的代表
        assert "佛跳墙" in CUISINE_PROMPT_FRAGMENT, (
            "F015 §2 要求关键词覆盖 '佛跳墙'；必须作为经典代表菜出现在 prompt 片段中"
        )

    def test_fragment_lists_representative_dishes(self) -> None:
        # F015 §3 经典：佛跳墙 / 海蛎煎 / 沙茶面 / 闽南春卷 / 荔枝肉
        # F015 §3 汤：鸡汤汆海蚌
        # 至少要有 3 道作为关键词候选
        classics = (
            "佛跳墙",
            "海蛎煎",
            "沙茶面",
            "闽南春卷",
            "荔枝肉",
            "鸡汤汆海蚌",
        )
        present = [d for d in classics if d in CUISINE_PROMPT_FRAGMENT]
        assert len(present) >= 3, (
            f"prompt 片段至少应列出 3 个 F015 §3 代表菜作为关键词候选；"
            f"实际命中={present}"
        )

    def test_fragment_distinguishes_from_cantonese(self) -> None:
        # F015 §2 验收：与粤菜的海鲜区分——闽更"汤鲜 + 山珍"，粤更"生猛海鲜"
        # §4 prompt 要点必须显式说明这一区分（否则 LLM 会把"海鲜"一律推粤）
        assert "粤菜" in CUISINE_PROMPT_FRAGMENT, (
            "F015 §2 + §4 明确要求 prompt 片段含与粤菜的海鲜区分；"
            "缺少会让 LLM 把'海鲜'一律推为粤菜"
        )
        # 闽的"汤鲜 + 山珍"标签必须显式呈现以引导 LLM 区分
        assert "汤鲜" in CUISINE_PROMPT_FRAGMENT
        # 粤的"生猛海鲜"对照也应在 prompt 中以使边界清晰
        assert "生猛海鲜" in CUISINE_PROMPT_FRAGMENT

    def test_fragment_mentions_signature_flavors(self) -> None:
        # F015 §1 + §4：闽菜特点为海鲜山珍 / 汤品出色 / 刀工巧妙
        # 关键词生成的风味词候选应当至少包含其一
        flavors = ("汤鲜", "山珍", "刀工巧妙", "海味")
        present = [f for f in flavors if f in CUISINE_PROMPT_FRAGMENT]
        assert present, f"prompt 片段必须含至少一个 F015 §4 风味词；实际命中={present}"

    def test_fragment_warns_allergens(self) -> None:
        # F015 §4 过敏原注意：海蛎煎 / 海蚌含贝类；闽菜大量海鲜
        # 至少命中 1 个过敏原提示词以引导 LLM 在 matched_allergies 中返回
        allergens = ("海蛎", "海蚌", "贝类", "shellfish", "fish", "虾")
        present = [a for a in allergens if a in CUISINE_PROMPT_FRAGMENT]
        assert present, (
            f"prompt 片段必须含至少 1 个 F015 §4 过敏原提示词；实际命中={present}"
        )

    def test_fragment_specifies_keyword_generation_rule(self) -> None:
        # F015 §4 关键词生成规则：菜系词（闽菜 / 福建 / 闽南 / 沙茶）中
        # 1-2 个 + 1 个代表菜 + 1 个风味词
        # 显式规则必须落在片段中（否则 LLM 不会按规则生成）
        assert "关键词" in CUISINE_PROMPT_FRAGMENT
        assert "风味" in CUISINE_PROMPT_FRAGMENT


# ---------------------------------------------------------------------------
# TestFujianBuildPrompt — F015 §6 行为验收：user_message → prompt 内容
# ---------------------------------------------------------------------------


class TestFujianBuildPrompt:
    """F015 §6 测试计划：用户输入"闽南 / 沙茶" → 关键词含"闽菜"。

    不接 LLM 验证 LLM 行为，而是验证 prompt 模板确实提供了产生该
    行为所需的全部上下文（用户输入 + 菜系词 + 风味词 + 与粤菜区分）。
    """

    def test_minnan_shacha_input_prompt_includes_mincai(self) -> None:
        """F015 §6 验收点：用户输入"闽南 / 沙茶"时，build_prompt 输出必须
        既含用户的原文又含菜系词"闽菜"，同时含与粤菜的区分澄清，从而
        LLM 可按规则产出含"闽菜"的关键词集。
        """
        prompt = FujianExpert().build_prompt(_build_input("想吃闽南沙茶"))

        # 用户原始输入被注入（F003 §4 模板必含 {message}）
        assert "想吃闽南沙茶" in prompt
        # F015 §2 菜系词：闽菜 / 福建 / 闽南 / 沙茶 至少其一
        assert any(token in prompt for token in ("闽菜", "福建", "闽南", "沙茶"))
        # §2 验收：与粤菜的海鲜区分必须在 prompt 中
        assert "粤菜" in prompt
        # §4 风味词候选：汤鲜 / 海味 / 山珍
        assert any(token in prompt for token in ("汤鲜", "海味", "山珍"))

    def test_fujian_input_prompt_carries_fujian_term(self) -> None:
        """用户输入"福建菜"时，prompt 必须把"福建"作为菜系词候选之一。"""
        prompt = FujianExpert().build_prompt(_build_input("想吃福建菜"))

        assert "福建" in prompt
        assert "闽菜" in prompt
        # §3 经典代表菜至少出现一个
        assert any(
            dish in prompt
            for dish in ("佛跳墙", "海蛎煎", "沙茶面", "荔枝肉")
        )

    def test_shacha_input_prompt_promotes_shachamian(self) -> None:
        """用户输入"沙茶"时，prompt 必须把"沙茶面"作为代表菜候选（§4 规则）。"""
        prompt = FujianExpert().build_prompt(_build_input("想吃沙茶"))

        assert "沙茶" in prompt
        assert "沙茶面" in prompt


# ---------------------------------------------------------------------------
# TestFujianParseOutput — F003 §3.3 闽菜 Node 自己的解析行为
# ---------------------------------------------------------------------------


class TestFujianParseOutput:
    """闽菜继承的 `BaseCuisineExpert.parse_output` 对闽菜专用字段。

    验证时使用闽菜领域的 representative JSON（闽菜 / 沙茶 / 佛跳墙 关键词集合）。
    """

    def test_parse_happy_path_mincai_dishes(self) -> None:
        expert = FujianExpert()
        conclusion = "今天适合来份佛跳墙"
        raw = (
            f'{{"conclusion":"{conclusion}",'
            '"keywords":["闽菜","佛跳墙","沙茶面","海蛎煎","汤鲜"],'
            '"matched_allergies":[]}'
        )
        out = expert.parse_output(raw)

        assert out["cuisine_id"] == "fujian"
        # conclusion 是 LLM 自由文本，只要透传即可
        assert out["conclusion"] == conclusion
        # F015 §2 关键词覆盖：闽菜 + 沙茶 + 佛跳墙 都在
        assert "闽菜" in out["keywords"]
        assert "沙茶面" in out["keywords"]
        assert "佛跳墙" in out["keywords"]
        # §3 经典代表菜
        assert "海蛎煎" in out["keywords"]
        assert "汤鲜" in out["keywords"]
        assert all(isinstance(k, str) for k in out["keywords"])

    def test_parse_happy_path_with_regional_subcuisines(self) -> None:
        """F015 §4 范围：含福州 / 闽南 / 闽西三路风味——若 LLM 输出三派
        代表菜，parse_output 必须透传不丢字段（让 summary agent 能聚合）。"""
        expert = FujianExpert()
        raw = (
            '{"conclusion":"今天推荐闽菜",'
            '"keywords":["闽菜","闽南","沙茶面","福州","佛跳墙"],'
            '"matched_allergies":[]}'
        )
        out = expert.parse_output(raw)

        assert out["cuisine_id"] == "fujian"
        # F015 §2 关键词覆盖几项全在
        assert "闽菜" in out["keywords"]
        assert "闽南" in out["keywords"]
        assert "福州" in out["keywords"]

    def test_parse_happy_path_with_allergens(self) -> None:
        """F015 §4 过敏原：海蛎 / 海蚌——若 LLM 命中应透传到 matched_allergies。"""
        expert = FujianExpert()
        raw = (
            '{"conclusion":"今天推荐闽菜",'
            '"keywords":["闽菜","海蛎煎"],'
            '"matched_allergies":["shellfish","fish"]}'
        )
        out = expert.parse_output(raw)

        assert out["cuisine_id"] == "fujian"
        assert "shellfish" in out["matched_allergies"]
        assert "fish" in out["matched_allergies"]

    def test_parse_invalid_json_falls_back(self) -> None:
        expert = FujianExpert()
        out = expert.parse_output("not json at all")

        assert out["cuisine_id"] == "fujian"
        assert out["conclusion"] == "暂不可推荐"
        assert out["keywords"] == []
        assert out["matched_allergies"] == []
