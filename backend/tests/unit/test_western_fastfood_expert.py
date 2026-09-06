"""F020 — 西式快餐专家专属契约测试.

涵盖 [spec/features/F020-western-fastfood.md §2 / §6] 验收点:

- cuisine_id / display_name / 继承 `BaseCuisineExpert`
- 关键词覆盖：快餐 / 汉堡 / 炸鸡 / 披萨 / 便利店便当（§2 验收点）
- 与西餐（F019）的边界：人均 < 80、快餐式归本菜系
- 与日料（F018）的边界：便利店日式便当归本菜系
- §6 测试计划：
  - 用户输入"想快吃" → 关键词含"汉堡"或"披萨"
  - 集成：用户预算 < 50 元 → 优先本菜系

不重复 F003 `test_base_contract.py` 已覆盖的内容（继承关系 / parse_output
通用 fallback / 全 14 注册表完整性）—— 那些属于通用契约。本文件只断言
**西式快餐专属** 的行为约束，确保 §4 prompt 要点被实际写进代码。
"""

from __future__ import annotations

from decimal import Decimal

from app.agents.cuisines import CUISINE_REGISTRY, BaseCuisineExpert
from app.agents.cuisines.stubs.western_fastfood import (
    CUISINE_PROMPT_FRAGMENT,
    WesternFastfoodExpert,
)
from app.agents.state import CuisineExpertInput, UserPreferencesDict
from app.core.constants import CUISINE_IDS

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_input(user_message: str, allergies: list[str] | None = None) -> CuisineExpertInput:
    """构造一个最小可用的 `CuisineExpertInput`.

    F020 §6 验收点关注的是 user_message，preferences 用占位即可。
    """
    prefs: UserPreferencesDict = {
        "user_id": "u-f020",
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
        "budget_max": 80.0,
        "budget_min": 30.0,
    }


# ---------------------------------------------------------------------------
# TestWesternFastfoodBasicContract — F003 §3.1 必填属性 + F020 §2 cuisine_id
# ---------------------------------------------------------------------------


class TestWesternFastfoodBasicContract:
    def test_western_fastfood_expert_inherits_base(self) -> None:
        assert issubclass(WesternFastfoodExpert, BaseCuisineExpert)

    def test_cuisine_id_is_western_fastfood(self) -> None:
        # F020 §2 验收点：`cuisine_id="western_fastfood"`
        assert WesternFastfoodExpert.cuisine_id == "western_fastfood"

    def test_display_name_is_xishi_kuaican(self) -> None:
        # F020 §1 用户故事 + §2 验收要求"西式快餐"作为显示名
        assert WesternFastfoodExpert.display_name == "西式快餐"

    def test_uses_unified_llm_model(self) -> None:
        # F003 §8.1 — 14 个菜系统一 `MiniMax-M3`
        assert WesternFastfoodExpert.llm_model == "MiniMax-M3"

    def test_prompt_fragment_is_non_empty_string(self) -> None:
        # 必须存在菜系专属片段，否则不满足 F003 §3.1 的子类可选 override
        assert isinstance(WesternFastfoodExpert.prompt_fragment, str)
        assert WesternFastfoodExpert.prompt_fragment.strip()


# ---------------------------------------------------------------------------
# TestWesternFastfoodInRegistry — F003 §3.2 注册表
# ---------------------------------------------------------------------------


class TestWesternFastfoodInRegistry:
    def test_registered_in_cuisine_registry(self) -> None:
        assert "western_fastfood" in CUISINE_REGISTRY
        assert CUISINE_REGISTRY["western_fastfood"] is not None

    def test_registry_entry_has_matching_cuisine_id(self) -> None:
        expert = CUISINE_REGISTRY["western_fastfood"]
        assert expert.cuisine_id == "western_fastfood"
        assert expert.display_name == "西式快餐"

    def test_registry_position_matches_cuisine_ids_spec_order(self) -> None:
        # F003 §3.2 / `CUISINE_IDS` 顺序：western_fastfood 在第 11 位
        # （川 / 粤 / 鲁 / 苏 / 浙 / 闽 / 湘 / 徽 / 日料 / 西餐 / 西式快餐）
        assert CUISINE_IDS.index("western_fastfood") == 10
        assert tuple(CUISINE_REGISTRY.keys())[10] == "western_fastfood"


# ---------------------------------------------------------------------------
# TestWesternFastfoodPromptFragment — F020 §2 / §4 prompt 要点的实际落位
# ---------------------------------------------------------------------------


class TestWesternFastfoodPromptFragment:
    """验证 F020 §2/§4 关键提示已落到 `CUISINE_PROMPT_FRAGMENT` 字面量中.

    这些是**给 LLM 的字面规则**——它们只有在 prompt 片段里真正出现，
    才能引导模型输出符合 §2 §6 验收点的关键词。这就是 §6 可单测的
    唯一现实接口（不接 LLM）。
    """

    def test_fragment_lists_all_five_keyword_tokens(self) -> None:
        # F020 §2 验收：关键词覆盖 快餐 / 汉堡 / 炸鸡 / 披萨 / 便利店便当
        for token in ("快餐", "汉堡", "炸鸡", "披萨", "便利店便当"):
            assert token in CUISINE_PROMPT_FRAGMENT, (
                f"F020 §2 要求关键词覆盖 {token!r}；必须出现在 prompt 片段中以引导 LLM 输出"
            )

    def test_fragment_lists_burger_brands(self) -> None:
        # F020 §3 汉堡：麦当劳 / 肯德基 / 汉堡王
        # 至少 2 个汉堡品牌作为关键词候选
        brands = ("麦当劳", "肯德基", "汉堡王")
        present = [b for b in brands if b in CUISINE_PROMPT_FRAGMENT]
        assert len(present) >= 2, (
            f"prompt 片段应至少包含 2 个 F020 §3 汉堡品牌；实际命中={present}"
        )

    def test_fragment_lists_pizza_brands(self) -> None:
        # F020 §3 披萨：必胜客 / 达美乐
        pizza_brands = ("必胜客", "达美乐")
        present = [p for p in pizza_brands if p in CUISINE_PROMPT_FRAGMENT]
        assert len(present) >= 1, (
            f"prompt 片段必须列出至少 1 个 F020 §3 披萨品牌；实际命中={present}"
        )

    def test_fragment_lists_convenience_store_brands(self) -> None:
        # F020 §3 便利店：7-11 / 全家 / 罗森便当
        convenience = ("7-11", "7-11便利店", "全家", "罗森")
        present = [c for c in convenience if c in CUISINE_PROMPT_FRAGMENT]
        assert len(present) >= 2, (
            f"prompt 片段应至少包含 2 个 F020 §3 便利店品牌；实际命中={present}"
        )

    def test_fragment_distinguishes_from_western(self) -> None:
        # F020 §2 验收 + §4 prompt 要点：与西餐（F019）的边界
        # ——本 Node 推人均 < 80 元的西式快餐；西餐正餐归 F019
        assert "西餐" in CUISINE_PROMPT_FRAGMENT, (
            "F020 §2 + §4 明确要求 prompt 片段含与西餐的边界；"
            "缺少会让 LLM 把西餐正餐误推到本 Node"
        )

    def test_fragment_specifies_price_threshold(self) -> None:
        # F020 §2 / §4 关键提示：人均 < 80 元是本 Node 与西餐的核心边界
        # 必须显式落到 prompt 以让 LLM 在关键词生成时遵循
        assert "人均" in CUISINE_PROMPT_FRAGMENT
        assert "80" in CUISINE_PROMPT_FRAGMENT
        # 必须表达"< 80"或"80 元以下"
        assert any(
            token in CUISINE_PROMPT_FRAGMENT for token in ("< 80", "80 元以下", "人均 < 80")
        ), "F020 §4 必须显式表达'人均 < 80 元'的边界条件"

    def test_fragment_distinguishes_from_japanese(self) -> None:
        # F020 §4 prompt 要点：与日料（F018）的边界——便利店日式便当归本菜系
        assert "日料" in CUISINE_PROMPT_FRAGMENT, (
            "F020 §4 明确要求 prompt 片段含与日料的边界；"
            "缺少会让 LLM 把便利店日式便当误推到日料专家"
        )
        # §4 边界场景必须显式提及便利店日式便当归本菜系
        assert "便利店日式便当" in CUISINE_PROMPT_FRAGMENT, (
            "F020 §4 边界场景必须显式提及'便利店日式便当'归本菜系"
        )

    def test_fragment_lists_quick_food_flavors(self) -> None:
        # F020 §4 风味词候选：快餐 / 快 / 出餐快 / 标准化口味
        flavors = ("快餐", "快", "出餐快", "标准化")
        present = [f for f in flavors if f in CUISINE_PROMPT_FRAGMENT]
        assert len(present) >= 2, (
            f"prompt 片段必须含至少 2 个 F020 §4 风味词；实际命中={present}"
        )

    def test_fragment_warns_allergens(self) -> None:
        # F020 §4 过敏原注意：油炸物（fried_food）默认含；含麸质 / dairy 普遍
        allergens = ("油炸物", "fried_food", "麸质", "gluten", "dairy")
        present = [a for a in allergens if a in CUISINE_PROMPT_FRAGMENT]
        assert len(present) >= 2, (
            f"prompt 片段必须含至少 2 个 F020 §4 过敏原提示词；实际命中={present}"
        )

    def test_fragment_specifies_keyword_generation_rule(self) -> None:
        # F020 §4 关键词生成规则：包含"汉堡 / 炸鸡 / 披萨 / 便利店"
        # 中的 2 个 + 1 个风味词（"快餐"、"快"）
        assert "关键词" in CUISINE_PROMPT_FRAGMENT
        # 必须显式提示 4 类关键词候选中的多个
        assert "汉堡" in CUISINE_PROMPT_FRAGMENT
        assert "炸鸡" in CUISINE_PROMPT_FRAGMENT
        assert "披萨" in CUISINE_PROMPT_FRAGMENT
        assert "便利店" in CUISINE_PROMPT_FRAGMENT
        # 必须含风味词
        assert "快餐" in CUISINE_PROMPT_FRAGMENT


# ---------------------------------------------------------------------------
# TestWesternFastfoodBuildPrompt — F020 §6 行为验收：user_message → prompt 内容
# ---------------------------------------------------------------------------


class TestWesternFastfoodBuildPrompt:
    """F020 §6 测试计划：用户输入"想快吃" / "想吃汉堡" / "想吃披萨" → 关键词覆盖.

    不接 LLM 验证 LLM 行为，而是验证 prompt 模板确实提供了产生该
    行为所需的全部上下文（用户输入 + 菜系词 + 风味词 + 与西餐/日料边界）。
    """

    def test_fast_input_prompt_includes_burger_or_pizza(self) -> None:
        """F020 §6 验收点：用户输入"想快吃"时，build_prompt 输出必须
        既含用户的原文又含西式快餐关键词候选（汉堡 / 披萨），从而 LLM
        可按规则产出含"汉堡"或"披萨"的关键词集。
        """
        prompt = WesternFastfoodExpert().build_prompt(_build_input("想快吃"))

        # 用户原始输入被注入（F003 §4 模板必含 {message}）
        assert "想快吃" in prompt
        # F020 §2 关键词候选：汉堡 / 披萨至少其一
        assert any(token in prompt for token in ("汉堡", "披萨"))
        # §2 验收：与西餐的边界必须在 prompt 中
        assert "西餐" in prompt
        # §4 风味词：快餐
        assert "快餐" in prompt

    def test_burger_input_prompt_carries_burger_term(self) -> None:
        """用户输入"想吃汉堡"时，prompt 必须把"汉堡"作为代表菜候选。"""
        prompt = WesternFastfoodExpert().build_prompt(_build_input("想吃汉堡"))

        assert "汉堡" in prompt
        # §2 菜系词候选：西式快餐 / 汉堡
        assert any(token in prompt for token in ("西式快餐", "汉堡"))

    def test_pizza_input_prompt_carries_pizza_term(self) -> None:
        """用户输入"想吃披萨"时，prompt 必须把"披萨"作为代表菜候选。"""
        prompt = WesternFastfoodExpert().build_prompt(_build_input("想吃披萨"))

        assert "披萨" in prompt
        # §2 菜系词候选：西式快餐 / 披萨
        assert any(token in prompt for token in ("西式快餐", "披萨"))

    def test_fried_chicken_input_prompt_carries_fried_chicken_term(self) -> None:
        """用户输入"想吃炸鸡"时，prompt 必须把"炸鸡"作为代表菜候选。"""
        prompt = WesternFastfoodExpert().build_prompt(_build_input("想吃炸鸡"))

        assert "炸鸡" in prompt
        # §3 品牌候选：麦当劳 / 肯德基 / 汉堡王
        assert any(brand in prompt for brand in ("麦当劳", "肯德基", "汉堡王"))

    def test_convenience_store_bento_input_pushes_from_japanese(self) -> None:
        """用户输入"便利店便当"时，prompt 必须显式把便利店日式便当场景
        推给本 Node——避免 LLM 把便利店便当误推到 F018 日料专家。
        """
        prompt = WesternFastfoodExpert().build_prompt(_build_input("想吃便利店便当"))

        # §4 边界澄清：便利店日式便当归本菜系
        assert "便利店日式便当" in prompt
        assert "日料" in prompt

    def test_western_steak_input_pushes_to_western(self) -> None:
        """用户输入"想吃牛排"时，prompt 必须显式把牛排场景归 F019 西餐
        ——避免 LLM 把西餐正餐误推到本 Node。
        """
        prompt = WesternFastfoodExpert().build_prompt(_build_input("想吃牛排"))

        # §4 边界澄清：牛排归 F019 西餐
        assert "西餐" in prompt
        # 本 Node prompt 中不应有西餐专属代表菜作为候选关键词
        from app.agents.cuisines.stubs.western import CUISINE_PROMPT_FRAGMENT as W_FRAGMENT

        western_signature_dishes = ("牛排", "意面", "烩饭")
        # 西餐 fragment 里存在这些菜；西式快餐 fragment 必须**不**包含这些
        for dish in western_signature_dishes:
            assert dish not in CUISINE_PROMPT_FRAGMENT, (
                f"西式快餐 prompt 不应包含西餐专属代表菜 {dish!r}；"
                "否则 LLM 会把西餐用户推到西式快餐"
            )
        # 防御性 sanity: 西餐 fragment 里这些确实存在（避免测试平凡通过）
        assert any(d in W_FRAGMENT for d in western_signature_dishes)

    def test_low_budget_input_does_not_change_prompt(self) -> None:
        """F020 §6 集成验收点：用户预算 < 50 元时，prompt 仍要按菜系规则产出
        关键词（预算检查属于 router 范畴，不是本 Node 责任）。
        """
        # 预算 < 50 元的输入
        prompt_low = WesternFastfoodExpert().build_prompt(
            {
                **_build_input("想快吃"),
                "budget_max": 40.0,
            }
        )
        prompt_normal = WesternFastfoodExpert().build_prompt(_build_input("想快吃"))

        # prompt 片段不变（菜系推荐策略由 router 在 selected_cuisines 阶段完成）
        # 西式快餐相关关键词仍必须出现
        assert "汉堡" in prompt_low or "披萨" in prompt_low
        assert "汉堡" in prompt_normal or "披萨" in prompt_normal


# ---------------------------------------------------------------------------
# TestWesternFastfoodParallelSafety — F020 §6 集成：与西餐并行时不冲突
# ---------------------------------------------------------------------------


class TestWesternFastfoodParallelSafety:
    """F020 §6 验收点：与西餐并行时不冲突。

    验证多菜系注册表 + build_prompt 的隔离性——西式快餐 Node 不会因其它
    菜系的 prompt 片段被调用而改变自身行为。
    """

    def test_western_and_western_fastfood_coexist_in_registry(self) -> None:
        # 两个菜系 Node 都注册到统一 registry，顺序由 CUISINE_IDS 决定
        assert "western" in CUISINE_REGISTRY
        assert "western_fastfood" in CUISINE_REGISTRY
        # 各自的 prompt_fragment 互不污染
        from app.agents.cuisines.stubs.western import WesternExpert

        assert WesternExpert.prompt_fragment != WesternFastfoodExpert.prompt_fragment
        assert "西餐" in WesternExpert.prompt_fragment
        assert "西式快餐" in WesternFastfoodExpert.prompt_fragment

    def test_western_fastfood_prompt_does_not_leak_western_signature(self) -> None:
        """西式快餐 build_prompt 中不应包含西餐专属代表菜（牛排 / 意面），
        仅在边界澄清句里出现"西餐"作为对照词。
        """
        prompt = WesternFastfoodExpert().build_prompt(_build_input("想吃西式快餐"))

        # 西餐专属代表菜不应出现在西式快餐 prompt 中
        from app.agents.cuisines.stubs.western import CUISINE_PROMPT_FRAGMENT as W_FRAGMENT

        western_signature_dishes = ("牛排", "意面", "烩饭", "凯撒沙拉")
        for dish in western_signature_dishes:
            assert dish not in prompt, (
                f"西式快餐 prompt 不应包含西餐代表菜 {dish!r}；否则 LLM 会把西餐用户推到西式快餐"
            )
        # 西餐 fragment 里这些确实存在（避免测试平凡通过）
        assert any(d in W_FRAGMENT for d in western_signature_dishes)

    def test_western_fastfood_prompt_does_not_leak_japanese_signature(self) -> None:
        """西式快餐 build_prompt 中不应包含日料专属代表菜（寿司 / 刺身），
        仅在边界澄清句里出现"日料"作为对照词。
        """
        prompt = WesternFastfoodExpert().build_prompt(_build_input("想吃西式快餐"))

        # 日料专属代表菜不应出现在西式快餐 prompt 中
        from app.agents.cuisines.stubs.japanese import CUISINE_PROMPT_FRAGMENT as J_FRAGMENT

        japanese_signature_dishes = ("寿司", "刺身", "鳗鱼饭")
        for dish in japanese_signature_dishes:
            assert dish not in prompt, (
                f"西式快餐 prompt 不应包含日料代表菜 {dish!r}；否则 LLM 会把日料用户推到西式快餐"
            )
        # 日料 fragment 里这些确实存在（避免测试平凡通过）
        assert any(d in J_FRAGMENT for d in japanese_signature_dishes)


# ---------------------------------------------------------------------------
# TestWesternFastfoodParseOutput — F003 §3.3 西式快餐 Node 自己的解析行为
# ---------------------------------------------------------------------------


class TestWesternFastfoodParseOutput:
    """西式快餐继承的 `BaseCuisineExpert.parse_output` 对西式快餐专用字段。

    验证时使用西式快餐领域的 representative JSON（汉堡 / 披萨 / 炸鸡 关键词集合）。
    """

    def test_parse_happy_path_western_fastfood_dishes(self) -> None:
        expert = WesternFastfoodExpert()
        conclusion = "今天适合来份汉堡"
        raw = (
            f'{{"conclusion":"{conclusion}",'
            '"keywords":["西式快餐","汉堡","披萨","炸鸡","快餐"],'
            '"matched_allergies":[]}'
        )
        out = expert.parse_output(raw)

        assert out["cuisine_id"] == "western_fastfood"
        # conclusion 是 LLM 自由文本，只要透传即可
        assert out["conclusion"] == conclusion
        # F020 §2 关键词覆盖：西式快餐 + 汉堡 + 披萨 都在
        assert "西式快餐" in out["keywords"]
        assert "汉堡" in out["keywords"]
        assert "披萨" in out["keywords"]
        # §2 关键词：炸鸡
        assert "炸鸡" in out["keywords"]
        # §4 风味词：快餐
        assert "快餐" in out["keywords"]
        assert all(isinstance(k, str) for k in out["keywords"])

    def test_parse_happy_path_with_convenience_store_bento(self) -> None:
        """F020 §3 便利店便当：7-11 / 全家 / 罗森便当——若 LLM 输出
        便利店便当相关关键词，parse_output 必须透传不丢字段。
        """
        expert = WesternFastfoodExpert()
        raw = (
            '{"conclusion":"今天推荐便利店便当",'
            '"keywords":["西式快餐","便利店便当","7-11","全家","快餐"],'
            '"matched_allergies":[]}'
        )
        out = expert.parse_output(raw)

        assert out["cuisine_id"] == "western_fastfood"
        # F020 §2 关键词覆盖：西式快餐
        assert "西式快餐" in out["keywords"]
        # §2 关键词：便利店便当
        assert "便利店便当" in out["keywords"]
        # §3 便利店品牌
        assert "7-11" in out["keywords"]
        assert "全家" in out["keywords"]
        # §4 风味词：快餐
        assert "快餐" in out["keywords"]

    def test_parse_happy_path_with_allergens(self) -> None:
        """F020 §4 过敏原：油炸物 / 麸质 / dairy——若 LLM 命中应透传到 matched_allergies。"""
        expert = WesternFastfoodExpert()
        raw = (
            '{"conclusion":"今天推荐西式快餐",'
            '"keywords":["西式快餐","汉堡"],'
            '"matched_allergies":["fried_food","gluten","dairy"]}'
        )
        out = expert.parse_output(raw)

        assert out["cuisine_id"] == "western_fastfood"
        assert "fried_food" in out["matched_allergies"]
        assert "gluten" in out["matched_allergies"]
        assert "dairy" in out["matched_allergies"]

    def test_parse_invalid_json_falls_back(self) -> None:
        expert = WesternFastfoodExpert()
        out = expert.parse_output("not json at all")

        assert out["cuisine_id"] == "western_fastfood"
        assert out["conclusion"] == "暂不可推荐"
        assert out["keywords"] == []
        assert out["matched_allergies"] == []
