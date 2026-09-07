"""F022 — 中式快餐专家专属契约测试.

涵盖 [spec/features/F022-chinese-fastfood.md §2 / §6] 验收点:

- cuisine_id / display_name / 继承 `BaseCuisineExpert`
- 关键词覆盖：快餐 / 便当 / 黄焖鸡 / 沙县 / 兰州拉面（§2 验收点）
- 与鲁菜（F012）的边界：黄焖鸡起源山东但定位是快餐，归本菜系
- 与小吃（F023）/ 西式快餐（F020）的边界
- §6 测试计划:
  - "快吃饱" → 关键词含"黄焖鸡"或"沙县"

不重复 F003 `test_base_contract.py` 已覆盖的内容（继承关系 / parse_output
通用 fallback / 全 14 注册表完整性）—— 那些属于通用契约。本文件只断言
**中式快餐专属** 的行为约束，确保 §4 prompt 要点被实际写进代码。
"""

from __future__ import annotations

from decimal import Decimal

from app.agents.cuisines import CUISINE_REGISTRY, BaseCuisineExpert
from app.agents.cuisines.stubs.chinese_fastfood import (
    CUISINE_PROMPT_FRAGMENT,
    ChineseFastfoodExpert,
)
from app.agents.state import CuisineExpertInput, UserPreferencesDict
from app.core.constants import CUISINE_IDS

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_input(user_message: str, allergies: list[str] | None = None) -> CuisineExpertInput:
    """构造一个最小可用的 `CuisineExpertInput`.

    F022 §6 验收点关注的是 user_message，preferences 用占位即可。
    """
    prefs: UserPreferencesDict = {
        "user_id": "u-f022",
        "cuisine_weights": dict.fromkeys(CUISINE_IDS, 0.5),
        "allergies": allergies if allergies is not None else [],
        "spice_tolerance": 0,
        "temperature_preference": "room",
        "default_location": "国贸",
        "budget_lunch_min": Decimal("15.00"),
        "budget_lunch_max": Decimal("40.00"),
    }
    return {
        "user_message": user_message,
        "user_preferences": prefs,
        "location": None,
        "spice_tolerance": 0,
        "budget_max": 40.0,
        "budget_min": 15.0,
    }


# ---------------------------------------------------------------------------
# TestChineseFastfoodBasicContract — F003 §3.1 必填属性 + F022 §2 cuisine_id
# ---------------------------------------------------------------------------


class TestChineseFastfoodBasicContract:
    def test_chinese_fastfood_expert_inherits_base(self) -> None:
        assert issubclass(ChineseFastfoodExpert, BaseCuisineExpert)

    def test_cuisine_id_is_chinese_fastfood(self) -> None:
        # F022 §2 验收点：`cuisine_id="chinese_fastfood"`
        assert ChineseFastfoodExpert.cuisine_id == "chinese_fastfood"

    def test_display_name_is_zhongshikuaican(self) -> None:
        # F022 §1 用户故事 + §2 验收要求"中式快餐"作为显示名
        assert ChineseFastfoodExpert.display_name == "中式快餐"

    def test_uses_unified_llm_model(self) -> None:
        # F003 §8.1 — 14 个菜系统一 `MiniMax-M3`
        assert ChineseFastfoodExpert.llm_model == "MiniMax-M3"

    def test_prompt_fragment_is_non_empty_string(self) -> None:
        # 必须存在菜系专属片段，否则不满足 F003 §3.1 的子类可选 override
        assert isinstance(ChineseFastfoodExpert.prompt_fragment, str)
        assert ChineseFastfoodExpert.prompt_fragment.strip()


# ---------------------------------------------------------------------------
# TestChineseFastfoodInRegistry — F003 §3.2 注册表
# ---------------------------------------------------------------------------


class TestChineseFastfoodInRegistry:
    def test_registered_in_cuisine_registry(self) -> None:
        assert "chinese_fastfood" in CUISINE_REGISTRY
        assert CUISINE_REGISTRY["chinese_fastfood"] is not None

    def test_registry_entry_has_matching_cuisine_id(self) -> None:
        expert = CUISINE_REGISTRY["chinese_fastfood"]
        assert expert.cuisine_id == "chinese_fastfood"
        assert expert.display_name == "中式快餐"

    def test_registry_position_matches_cuisine_ids_spec_order(self) -> None:
        # F003 §3.2 / `CUISINE_IDS` 顺序：chinese_fastfood 在第 12 位
        # （川 / 粤 / 鲁 / 苏 / 浙 / 闽 / 湘 / 徽 / 日料 / 西餐 / 西式快餐 / 中式快餐）
        assert CUISINE_IDS.index("chinese_fastfood") == 11
        assert tuple(CUISINE_REGISTRY.keys())[11] == "chinese_fastfood"


# ---------------------------------------------------------------------------
# TestChineseFastfoodPromptFragment — F022 §2 / §4 prompt 要点的实际落位
# ---------------------------------------------------------------------------


class TestChineseFastfoodPromptFragment:
    """验证 F022 §2/§4 关键提示已落到 `CUISINE_PROMPT_FRAGMENT` 字面量中.

    这些是**给 LLM 的字面规则**——它们只有在 prompt 片段里真正出现，
    才能引导模型输出符合 §2 §6 验收点的关键词。这就是 §6 可单测的
    唯一现实接口（不接 LLM）。
    """

    def test_fragment_lists_all_required_keyword_tokens(self) -> None:
        # F022 §2 验收：关键词覆盖 快餐 / 便当 / 黄焖鸡 / 沙县 / 兰州拉面
        for token in ("快餐", "便当", "黄焖鸡", "沙县", "兰州拉面"):
            assert token in CUISINE_PROMPT_FRAGMENT, (
                f"F022 §2 要求关键词覆盖 {token!r}；必须出现在 prompt 片段中以引导 LLM 输出"
            )

    def test_fragment_lists_huangmen_dishes(self) -> None:
        # F022 §3 黄焖类：黄焖鸡米饭、黄焖猪脚
        huangmen = ("黄焖鸡米饭", "黄焖猪脚", "黄焖鸡")
        present = [s for s in huangmen if s in CUISINE_PROMPT_FRAGMENT]
        assert "黄焖鸡" in present, "F022 §3 必须包含'黄焖鸡'作为中式快餐代表"
        assert len(present) >= 2, (
            f"prompt 片段应至少包含 2 个 F022 §3 黄焖品类；实际命中={present}"
        )

    def test_fragment_lists_shaxian_dishes(self) -> None:
        # F022 §3 沙县：沙县拌面、蒸饺、炖罐
        shaxian = ("沙县拌面", "蒸饺", "炖罐")
        present = [s for s in shaxian if s in CUISINE_PROMPT_FRAGMENT]
        assert "沙县" in CUISINE_PROMPT_FRAGMENT
        assert len(present) >= 2, (
            f"prompt 片段应至少包含 2 个 F022 §3 沙县代表；实际命中={present}"
        )

    def test_fragment_lists_noodle_dishes(self) -> None:
        # F022 §3 拉面：兰州拉面、安徽板面
        noodles = ("兰州拉面", "安徽板面")
        present = [s for s in noodles if s in CUISINE_PROMPT_FRAGMENT]
        assert "兰州拉面" in present, "F022 §3 必须包含'兰州拉面'"
        assert len(present) >= 2, (
            f"prompt 片段应至少包含 2 个 F022 §3 拉面代表；实际命中={present}"
        )

    def test_fragment_lists_simple_meal_dishes(self) -> None:
        # F022 §3 简餐：隆江猪脚饭、台湾卤肉饭、广式煲仔饭
        simple_meals = ("隆江猪脚饭", "台湾卤肉饭", "广式煲仔饭", "猪脚饭")
        present = [s for s in simple_meals if s in CUISINE_PROMPT_FRAGMENT]
        assert "猪脚饭" in present, "F022 §3 必须包含'猪脚饭'"
        assert len(present) >= 2, (
            f"prompt 片段应至少包含 2 个 F022 §3 简餐代表；实际命中={present}"
        )

    def test_fragment_distinguishes_from_shandong_cuisine(self) -> None:
        # F022 §2 + §4 与鲁菜（F012）的边界：黄焖鸡起源山东但定位是快餐，归本菜系
        assert "鲁菜" in CUISINE_PROMPT_FRAGMENT, (
            "F022 §2 + §4 明确要求 prompt 片段含与鲁菜的边界；"
            "缺少会让 LLM 把快餐式黄焖鸡误推到鲁菜专家"
        )
        # §4 必须显式提到黄焖鸡的归属
        assert "黄焖鸡" in CUISINE_PROMPT_FRAGMENT
        assert "山东" in CUISINE_PROMPT_FRAGMENT, (
            "F022 §4 边界场景必须显式提及'山东'作为黄焖鸡起源"
        )

    def test_fragment_distinguishes_from_snacks(self) -> None:
        # F022 §4 与小吃（F023）的边界：简餐类归本菜系；纯小吃归 F023
        assert "小吃" in CUISINE_PROMPT_FRAGMENT or "F023" in CUISINE_PROMPT_FRAGMENT, (
            "F022 §4 边界场景必须显式提及小吃（F023）作为对照"
        )

    def test_fragment_distinguishes_from_western_fastfood(self) -> None:
        # F022 §4 与西式快餐（F020）的边界：不要推汉堡/薯条/炸鸡/披萨
        assert "西式快餐" in CUISINE_PROMPT_FRAGMENT, (
            "F022 §4 边界场景必须显式提及西式快餐（F020）以避免误推"
        )

    def test_fragment_specifies_price_threshold(self) -> None:
        # F022 §4 关键提示：人均 15-40 元
        assert "人均" in CUISINE_PROMPT_FRAGMENT
        # 必须显式表达人均区间
        assert "15" in CUISINE_PROMPT_FRAGMENT
        assert "40" in CUISINE_PROMPT_FRAGMENT

    def test_fragment_specifies_rating_threshold(self) -> None:
        # F022 §4 关键提示：评分 ≥ 3.5
        assert "评分" in CUISINE_PROMPT_FRAGMENT
        assert "3.5" in CUISINE_PROMPT_FRAGMENT
        assert "≥ 3.5" in CUISINE_PROMPT_FRAGMENT, (
            "F022 §4 必须显式表达'评分 ≥ 3.5'的餐厅筛选条件"
        )

    def test_fragment_specifies_quick_service_property(self) -> None:
        # F022 §4 中式快餐特点：出餐快、标准化口味
        assert "出餐快" in CUISINE_PROMPT_FRAGMENT, (
            "F022 §4 中式快餐特点必须含'出餐快'"
        )

    def test_fragment_warns_allergens(self) -> None:
        # F022 §4 过敏原注意：酱油 / 味精 / 花生 / 麸质
        allergens = ("酱油", "味精", "花生", "麸质", "soy", "MSG")
        present = [a for a in allergens if a in CUISINE_PROMPT_FRAGMENT]
        assert len(present) >= 3, (
            f"prompt 片段必须含至少 3 个 F022 §4 过敏原提示词；实际命中={present}"
        )

    def test_fragment_specifies_keyword_generation_rule(self) -> None:
        # F022 §4 关键词生成规则：包含"黄焖鸡 / 沙县 / 兰州拉面 / 猪脚饭"中的 1-2 个
        # + 1 个风味词（"快餐"、"快"、"出餐快"、"酱香"）
        assert "关键词" in CUISINE_PROMPT_FRAGMENT
        # 必须显式列出 4 个候选关键词
        for token in ("黄焖鸡", "沙县", "兰州拉面", "猪脚饭"):
            assert token in CUISINE_PROMPT_FRAGMENT
        # 必须含至少 1 个风味词
        assert any(
            token in CUISINE_PROMPT_FRAGMENT for token in ("快餐", "快", "出餐快", "酱香")
        ), "F022 §4 必须显式列出至少 1 个风味词"


# ---------------------------------------------------------------------------
# TestChineseFastfoodBuildPrompt — F022 §6 行为验收：user_message → prompt 内容
# ---------------------------------------------------------------------------


class TestChineseFastfoodBuildPrompt:
    """F022 §6 测试计划：用户输入"快吃饱" / "想吃黄焖鸡" / "想点沙县" → 关键词覆盖.

    不接 LLM 验证 LLM 行为，而是验证 prompt 模板确实提供了产生该
    行为所需的全部上下文（用户输入 + 菜系词 + 风味词 + 与鲁菜边界）。
    """

    def test_huangmenji_input_prompt_includes_huangmenji_and_kuaican(self) -> None:
        """F022 §6 验收点：用户输入"想吃黄焖鸡"时，build_prompt 输出必须
        既含用户的原文又含菜系词"黄焖鸡"，从而 LLM 可按规则产出含
        "黄焖鸡"的关键词集。
        """
        prompt = ChineseFastfoodExpert().build_prompt(_build_input("想吃黄焖鸡"))

        # 用户原始输入被注入（F003 §4 模板必含 {message}）
        assert "想吃黄焖鸡" in prompt
        # F022 §2 菜系词：快餐
        assert "快餐" in prompt
        # §3 黄焖鸡作为代表菜
        assert "黄焖鸡" in prompt
        # §2 验收：与鲁菜的边界必须在 prompt 中
        assert "鲁菜" in prompt

    def test_shaxian_input_prompt_carries_shaxian_term(self) -> None:
        """用户输入"想吃沙县"时，prompt 必须把"沙县"作为代表菜候选。"""
        prompt = ChineseFastfoodExpert().build_prompt(_build_input("想吃沙县拌面"))

        assert "沙县" in prompt
        assert "拌面" in prompt

    def test_lanzhou_noodle_input_prompt_carries_noodle_term(self) -> None:
        """用户输入"兰州拉面"时，prompt 必须把"兰州拉面"作为代表菜候选。"""
        prompt = ChineseFastfoodExpert().build_prompt(_build_input("想吃兰州拉面"))

        assert "兰州拉面" in prompt
        assert "拉面" in prompt

    def test_kuaican_chi_input_includes_kuaican_term(self) -> None:
        """F022 §6 主用例：用户输入"快吃饱"时，prompt 必须含"黄焖鸡"或
        "沙县"作为推荐候选。
        """
        prompt = ChineseFastfoodExpert().build_prompt(_build_input("快吃饱"))

        # §6 用例：关键词含"黄焖鸡"或"沙县"
        assert "黄焖鸡" in prompt or "沙县" in prompt
        # §4 风味词
        assert "快餐" in prompt

    def test_zhu_jiao_fan_input_pushes_to_simple_meal(self) -> None:
        """用户输入"想吃猪脚饭"时，prompt 必须把"猪脚饭"作为代表菜候选。"""
        prompt = ChineseFastfoodExpert().build_prompt(_build_input("想吃隆江猪脚饭"))

        assert "猪脚饭" in prompt
        assert "隆江猪脚饭" in prompt or "隆江" in prompt

    def test_peanut_allergy_promotes_allergen_warning(self) -> None:
        """用户输入"花生过敏"时，prompt 必须把花生 / 麸质 / 酱油
        过敏原标签置入，让 LLM 在 matched_allergies 中正确返回。
        """
        prompt = ChineseFastfoodExpert().build_prompt(
            _build_input("想吃隆江猪脚饭", allergies=["peanut"])
        )

        # §4 过敏原注意：花生 / 麸质 / 酱油
        assert "花生" in prompt

    def test_lurou_fan_input_includes_signature_dish(self) -> None:
        """用户输入"台湾卤肉饭"时，prompt 必须把"卤肉饭"作为代表菜候选。"""
        prompt = ChineseFastfoodExpert().build_prompt(_build_input("想吃台湾卤肉饭"))

        assert "卤肉饭" in prompt
        assert "台湾卤肉饭" in prompt

    def test_baozaifan_input_includes_signature_dish(self) -> None:
        """用户输入"煲仔饭"时，prompt 必须把"煲仔饭"作为代表菜候选。"""
        prompt = ChineseFastfoodExpert().build_prompt(_build_input("想吃广式煲仔饭"))

        assert "煲仔饭" in prompt


# ---------------------------------------------------------------------------
# TestChineseFastfoodParallelSafety — F022 §2 集成：与鲁菜/小吃并行时不冲突
# ---------------------------------------------------------------------------


class TestChineseFastfoodParallelSafety:
    """F022 §2 验收点：与鲁菜（F012）/ 小吃（F023）/ 西式快餐（F020）并行时不冲突。

    验证多菜系注册表 + build_prompt 的隔离性——中式快餐 Node 不会因其它
    菜系的 prompt 片段被调用而改变自身行为。
    """

    def test_chinese_fastfood_and_shandong_coexist_in_registry(self) -> None:
        # F022 与 F012 边界：两个菜系 Node 都注册到统一 registry
        assert "chinese_fastfood" in CUISINE_REGISTRY
        assert "shandong" in CUISINE_REGISTRY
        # 各自的 prompt_fragment 互不污染
        from app.agents.cuisines.stubs.shandong import ShandongExpert

        assert ChineseFastfoodExpert.prompt_fragment != ShandongExpert.prompt_fragment
        assert "中式快餐" in ChineseFastfoodExpert.prompt_fragment
        assert "鲁菜" in ChineseFastfoodExpert.prompt_fragment  # 边界澄清

    def test_chinese_fastfood_and_snacks_coexist_in_registry(self) -> None:
        # F022 与 F023 边界：两个菜系 Node 都注册到统一 registry
        assert "chinese_fastfood" in CUISINE_REGISTRY
        assert "snacks" in CUISINE_REGISTRY
        from app.agents.cuisines.stubs.snacks import SnacksExpert

        assert ChineseFastfoodExpert.prompt_fragment != SnacksExpert.prompt_fragment

    def test_chinese_fastfood_and_western_fastfood_coexist_in_registry(self) -> None:
        # F022 与 F020 边界：两个菜系 Node 都注册到统一 registry
        assert "chinese_fastfood" in CUISINE_REGISTRY
        assert "western_fastfood" in CUISINE_REGISTRY
        from app.agents.cuisines.stubs.western_fastfood import WesternFastfoodExpert

        assert ChineseFastfoodExpert.prompt_fragment != WesternFastfoodExpert.prompt_fragment
        assert "中式快餐" in ChineseFastfoodExpert.prompt_fragment
        assert "西式快餐" in ChineseFastfoodExpert.prompt_fragment  # 边界澄清

    def test_chinese_fastfood_prompt_does_not_leak_western_fastfood_signature(self) -> None:
        """中式快餐 build_prompt 不应包含西式快餐专属代表菜——通过输出
        不出现汉堡/薯条/炸鸡/披萨验证。
        """
        prompt = ChineseFastfoodExpert().build_prompt(_build_input("想吃快餐"))

        # 中式快餐专属代表菜应在中式快餐 prompt 中
        assert any(token in prompt for token in ("黄焖鸡", "沙县", "兰州拉面", "猪脚饭"))
        # 西式快餐专属代表菜不应出现在中式快餐 prompt 中
        western_fastfood_signature = ("汉堡", "薯条", "炸鸡")
        for dish in western_fastfood_signature:
            assert dish not in prompt, (
                f"中式快餐 prompt 不应包含西式快餐代表菜 {dish!r}；否则 LLM 会把中式快餐用户推到西式快餐"
            )

    def test_chinese_fastfood_prompt_carries_brand_or_chain_keywords(self) -> None:
        """中式快餐 Node 推连锁快餐店，prompt 必须含"连锁"或"档口"作为餐厅类型提示。"""
        prompt = ChineseFastfoodExpert().build_prompt(_build_input("想吃快餐"))

        assert "连锁" in prompt or "档口" in prompt, (
            "F022 §4 中式快餐定位为连锁档口式快餐店；prompt 必须体现"
        )


# ---------------------------------------------------------------------------
# TestChineseFastfoodParseOutput — F003 §3.3 中式快餐 Node 自己的解析行为
# ---------------------------------------------------------------------------


class TestChineseFastfoodParseOutput:
    """中式快餐继承的 `BaseCuisineExpert.parse_output` 对中式快餐专用字段。

    验证时使用中式快餐领域的 representative JSON（黄焖鸡 / 沙县 / 兰州拉面 关键词集合）。
    """

    def test_parse_happy_path_chinese_fastfood_dishes(self) -> None:
        expert = ChineseFastfoodExpert()
        conclusion = "今天适合来份黄焖鸡米饭"
        raw = (
            f'{{"conclusion":"{conclusion}",'
            '"keywords":["中式快餐","黄焖鸡","沙县拌面","兰州拉面","快餐"],'
            '"matched_allergies":[]}'
        )
        out = expert.parse_output(raw)

        assert out["cuisine_id"] == "chinese_fastfood"
        # conclusion 是 LLM 自由文本，只要透传即可
        assert out["conclusion"] == conclusion
        # F022 §2 关键词覆盖：快餐 + 黄焖鸡 + 沙县 + 兰州拉面
        assert "中式快餐" in out["keywords"]
        assert "黄焖鸡" in out["keywords"]
        assert "沙县拌面" in out["keywords"]
        assert "兰州拉面" in out["keywords"]
        # §4 风味词：快餐
        assert "快餐" in out["keywords"]
        assert all(isinstance(k, str) for k in out["keywords"])

    def test_parse_happy_path_with_zhujiaofan(self) -> None:
        """F022 §3 简餐：隆江猪脚饭、台湾卤肉饭、广式煲仔饭——若 LLM 输出
        全套简餐代表菜，parse_output 必须透传不丢字段。
        """
        expert = ChineseFastfoodExpert()
        raw = (
            '{"conclusion":"今天推荐中式快餐",'
            '"keywords":["中式快餐","隆江猪脚饭","台湾卤肉饭","广式煲仔饭","酱香"],'
            '"matched_allergies":[]}'
        )
        out = expert.parse_output(raw)

        assert out["cuisine_id"] == "chinese_fastfood"
        # F022 §2 关键词覆盖：快餐
        assert "中式快餐" in out["keywords"]
        # §3 简餐
        assert "隆江猪脚饭" in out["keywords"]
        assert "台湾卤肉饭" in out["keywords"]
        assert "广式煲仔饭" in out["keywords"]
        # §4 风味词：酱香
        assert "酱香" in out["keywords"]

    def test_parse_happy_path_with_allergens(self) -> None:
        """F022 §4 过敏原：酱油 / 味精 / 花生 / 麸质——若 LLM 命中应透传到 matched_allergies。"""
        expert = ChineseFastfoodExpert()
        raw = (
            '{"conclusion":"今天推荐中式快餐",'
            '"keywords":["中式快餐","猪脚饭"],'
            '"matched_allergies":["peanut","gluten","soy"]}'
        )
        out = expert.parse_output(raw)

        assert out["cuisine_id"] == "chinese_fastfood"
        assert "peanut" in out["matched_allergies"]
        assert "gluten" in out["matched_allergies"]
        assert "soy" in out["matched_allergies"]

    def test_parse_invalid_json_falls_back(self) -> None:
        expert = ChineseFastfoodExpert()
        out = expert.parse_output("not json at all")

        assert out["cuisine_id"] == "chinese_fastfood"
        assert out["conclusion"] == "暂不可推荐"
        assert out["keywords"] == []
        assert out["matched_allergies"] == []
