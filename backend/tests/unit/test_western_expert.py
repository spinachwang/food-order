"""F019 — 西餐专家专属契约测试.

涵盖 [spec/features/F019-western.md §2 / §6] 验收点:

- cuisine_id / display_name / 继承 `BaseCuisineExpert`
- 关键词覆盖：西餐 / 意餐 / 牛排 / 披萨（§2 验收点）
- 与西式快餐（F020）的边界：本 Node 推人均 ≥ 80 元的正餐西餐厅
- §6 测试计划:
  - 用户输入"想吃牛排" → 关键词含"牛排"和"西餐"
  - 集成：与西式快餐并行时不冲突

不重复 F003 `test_base_contract.py` 已覆盖的内容（继承关系 / parse_output
通用 fallback / 全 14 注册表完整性）—— 那些属于通用契约。本文件只断言
**西餐专属** 的行为约束，确保 §4 prompt 要点被实际写进代码。
"""

from __future__ import annotations

from decimal import Decimal

from app.agents.cuisines import CUISINE_REGISTRY, BaseCuisineExpert
from app.agents.cuisines.stubs.western import CUISINE_PROMPT_FRAGMENT, WesternExpert
from app.agents.state import CuisineExpertInput, UserPreferencesDict
from app.core.constants import CUISINE_IDS

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_input(user_message: str, allergies: list[str] | None = None) -> CuisineExpertInput:
    """构造一个最小可用的 `CuisineExpertInput`.

    F019 §6 验收点关注的是 user_message，preferences 用占位即可。
    """
    prefs: UserPreferencesDict = {
        "user_id": "u-f019",
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
# TestWesternBasicContract — F003 §3.1 必填属性 + F019 §2 cuisine_id
# ---------------------------------------------------------------------------


class TestWesternBasicContract:
    def test_western_expert_inherits_base(self) -> None:
        assert issubclass(WesternExpert, BaseCuisineExpert)

    def test_cuisine_id_is_western(self) -> None:
        # F019 §2 验收点：`cuisine_id="western"`
        assert WesternExpert.cuisine_id == "western"

    def test_display_name_is_xican(self) -> None:
        # F019 §1 用户故事 + §2 验收要求"西餐"作为显示名
        assert WesternExpert.display_name == "西餐"

    def test_uses_unified_llm_model(self) -> None:
        # F003 §8.1 — 14 个菜系统一 `MiniMax-M3`
        assert WesternExpert.llm_model == "MiniMax-M3"

    def test_prompt_fragment_is_non_empty_string(self) -> None:
        # 必须存在菜系专属片段，否则不满足 F003 §3.1 的子类可选 override
        assert isinstance(WesternExpert.prompt_fragment, str)
        assert WesternExpert.prompt_fragment.strip()


# ---------------------------------------------------------------------------
# TestWesternInRegistry — F003 §3.2 注册表
# ---------------------------------------------------------------------------


class TestWesternInRegistry:
    def test_registered_in_cuisine_registry(self) -> None:
        assert "western" in CUISINE_REGISTRY
        assert CUISINE_REGISTRY["western"] is not None

    def test_registry_entry_has_matching_cuisine_id(self) -> None:
        expert = CUISINE_REGISTRY["western"]
        assert expert.cuisine_id == "western"
        assert expert.display_name == "西餐"

    def test_registry_position_matches_cuisine_ids_spec_order(self) -> None:
        # F003 §3.2 / `CUISINE_IDS` 顺序：western 在第 10 位
        # （川 / 粤 / 鲁 / 苏 / 浙 / 闽 / 湘 / 徽 / 日料 / 西餐）
        assert CUISINE_IDS.index("western") == 9
        assert tuple(CUISINE_REGISTRY.keys())[9] == "western"


# ---------------------------------------------------------------------------
# TestWesternPromptFragment — F019 §2 / §4 prompt 要点的实际落位
# ---------------------------------------------------------------------------


class TestWesternPromptFragment:
    """验证 F019 §2/§4 关键提示已落到 `CUISINE_PROMPT_FRAGMENT` 字面量中.

    这些是**给 LLM 的字面规则**——它们只有在 prompt 片段里真正出现，
    才能引导模型输出符合 §2 §6 验收点的关键词。这就是 §6 可单测的
    唯一现实接口（不接 LLM）。
    """

    def test_fragment_lists_all_four_keyword_tokens(self) -> None:
        # F019 §2 验收：关键词覆盖 西餐 / 意餐 / 牛排 / 披萨
        for token in ("西餐", "意餐", "牛排", "披萨"):
            assert token in CUISINE_PROMPT_FRAGMENT, (
                f"F019 §2 要求关键词覆盖 {token!r}；必须出现在 prompt 片段中以引导 LLM 输出"
            )

    def test_fragment_lists_signature_steak_dishes(self) -> None:
        # F019 §3 牛排：菲力 / 西冷 / 肋眼 / 战斧
        # 至少 2 个牛排品类作为关键词候选
        steaks = ("菲力", "西冷", "肋眼", "战斧", "牛排")
        present = [s for s in steaks if s in CUISINE_PROMPT_FRAGMENT]
        assert "牛排" in present, "F019 §3 必须包含'牛排'作为西餐代表"
        assert len(present) >= 3, (
            f"prompt 片段应至少包含 3 个 F019 §3 牛排品类；实际命中={present}"
        )

    def test_fragment_lists_italian_pasta_and_risotto(self) -> None:
        # F019 §3 意面：意面、烩饭、意式烩饭
        italian = ("意面", "烩饭")
        for token in italian:
            assert token in CUISINE_PROMPT_FRAGMENT, (
                f"F019 §3 + §2 要求 {token!r} 作为西餐代表菜；必须出现在 prompt 片段中"
            )

    def test_fragment_lists_pizza_styling(self) -> None:
        # F019 §3 披萨：意式披萨、薄底披萨
        # 至少 1 个披萨款式作为关键词候选
        pizzas = ("意式披萨", "薄底披萨", "意式", "薄底")
        present = [p for p in pizzas if p in CUISINE_PROMPT_FRAGMENT]
        assert present, f"prompt 片段必须列出至少 1 个 F019 §3 披萨款式；实际命中={present}"

    def test_fragment_lists_salad_dishes(self) -> None:
        # F019 §3 沙拉：凯撒沙拉、尼斯沙拉
        salads = ("凯撒沙拉", "尼斯沙拉")
        present = [s for s in salads if s in CUISINE_PROMPT_FRAGMENT]
        assert present, f"prompt 片段必须列出至少 1 个 F019 §3 沙拉代表菜；实际命中={present}"

    def test_fragment_distinguishes_from_western_fastfood(self) -> None:
        # F019 §2 验收 + §4 prompt 要点：与西式快餐（F020）的边界
        # ——本 Node 推人均 ≥ 80 元的正餐西餐厅；人均 < 80、快餐式披萨归 F020
        assert "西式快餐" in CUISINE_PROMPT_FRAGMENT, (
            "F019 §2 + §4 明确要求 prompt 片段含与西式快餐的边界；"
            "缺少会让 LLM 把快餐式披萨误推到西餐专家"
        )
        # §4 边界场景必须显式提及必胜客欢乐餐厅
        assert "必胜客欢乐餐厅" in CUISINE_PROMPT_FRAGMENT, (
            "F019 §4 边界场景必须显式提及'必胜客欢乐餐厅'以引导 LLM 把快餐式披萨归 F020"
        )

    def test_fragment_specifies_price_threshold(self) -> None:
        # F019 §2 / §4 关键提示：人均 ≥ 80 元是本 Node 与西式快餐的核心边界
        # 必须显式落到 prompt 以让 LLM 在关键词生成时遵循
        assert "人均" in CUISINE_PROMPT_FRAGMENT
        assert "80" in CUISINE_PROMPT_FRAGMENT
        # 至少表达"≥ 80"或"80 元及以上"
        assert any(
            token in CUISINE_PROMPT_FRAGMENT for token in ("≥ 80", "80 元", "人均 ≥ 80")
        ), "F019 §4 必须显式表达'人均 ≥ 80 元'的边界条件"

    def test_fragment_specifies_rating_threshold(self) -> None:
        # F019 §4 关键提示：餐厅筛选 —— 评分 ≥ 4.0
        assert "评分" in CUISINE_PROMPT_FRAGMENT
        assert "4.0" in CUISINE_PROMPT_FRAGMENT
        # 必须显式表达 "≥ 4.0" 的筛选条件
        assert "≥ 4.0" in CUISINE_PROMPT_FRAGMENT, (
            "F019 §4 必须显式表达'评分 ≥ 4.0'的餐厅筛选条件"
        )

    def test_fragment_lists_signature_flavors(self) -> None:
        # F019 §4 风味词候选：奶香 / 番茄 / 香草 / 黑胡椒 / 烧烤
        flavors = ("奶香", "番茄", "香草", "黑胡椒", "烧烤", "黄油", "红酒")
        present = [f for f in flavors if f in CUISINE_PROMPT_FRAGMENT]
        assert len(present) >= 3, (
            f"prompt 片段必须含至少 3 个 F019 §4 风味词；实际命中={present}"
        )

    def test_fragment_warns_allergens(self) -> None:
        # F019 §4 过敏原注意：奶制品 / 麸质 / 坚果
        allergens = ("奶制品", "dairy", "麸质", "gluten", "坚果", "nuts")
        present = [a for a in allergens if a in CUISINE_PROMPT_FRAGMENT]
        assert len(present) >= 2, (
            f"prompt 片段必须含至少 2 个 F019 §4 过敏原提示词；实际命中={present}"
        )

    def test_fragment_specifies_keyword_generation_rule(self) -> None:
        # F019 §4 关键词生成规则：包含"西餐 / 意餐"中的 1 个
        # + 1 个代表菜（"牛排"、"意面"）
        # + 1 个风味词（"奶香"、"番茄"、"香草"）
        assert "关键词" in CUISINE_PROMPT_FRAGMENT
        assert "代表菜" in CUISINE_PROMPT_FRAGMENT
        assert "风味" in CUISINE_PROMPT_FRAGMENT

    def test_fragment_covers_italian_and_french_cuisine(self) -> None:
        # F019 §4 范围：意式、法式、美式西餐聚合
        # 必须显式覆盖至少 2 种西餐细分以体现聚合范围
        cuisine_subtypes = ("意式", "法式", "美式")
        present = [c for c in cuisine_subtypes if c in CUISINE_PROMPT_FRAGMENT]
        assert len(present) >= 2, (
            f"prompt 片段应至少覆盖 2 种 F019 §4 西餐细分（意式/法式/美式）；实际命中={present}"
        )


# ---------------------------------------------------------------------------
# TestWesternBuildPrompt — F019 §6 行为验收：user_message → prompt 内容
# ---------------------------------------------------------------------------


class TestWesternBuildPrompt:
    """F019 §6 测试计划：用户输入"想吃牛排" / "想吃披萨" / "想吃意面" → 关键词覆盖.

    不接 LLM 验证 LLM 行为，而是验证 prompt 模板确实提供了产生该
    行为所需的全部上下文（用户输入 + 菜系词 + 风味词 + 与西式快餐边界）。
    """

    def test_steak_input_prompt_includes_steak_and_xican(self) -> None:
        """F019 §6 验收点：用户输入"想吃牛排"时，build_prompt 输出必须
        既含用户的原文又含菜系词"西餐"，从而 LLM 可按规则产出含"牛排"
        和"西餐"的关键词集。
        """
        prompt = WesternExpert().build_prompt(_build_input("想吃牛排"))

        # 用户原始输入被注入（F003 §4 模板必含 {message}）
        assert "想吃牛排" in prompt
        # F019 §2 菜系词：西餐 / 意餐 至少其一
        assert "西餐" in prompt
        # §2 验收：与西式快餐的边界必须在 prompt 中
        assert "西式快餐" in prompt
        # §3 牛排 / 披萨代表菜至少出现一个（§2 验收点）
        assert "牛排" in prompt

    def test_pizza_input_prompt_carries_pizza_term(self) -> None:
        """用户输入"想吃披萨"时，prompt 必须把"披萨"作为代表菜候选。"""
        prompt = WesternExpert().build_prompt(_build_input("想吃披萨"))

        assert "披萨" in prompt
        # §2 菜系词候选：西餐 / 意餐
        assert any(token in prompt for token in ("西餐", "意餐", "意式"))

    def test_pasta_input_prompt_carries_pasta_term(self) -> None:
        """用户输入"想吃意面"时，prompt 必须把"意面"作为代表菜候选。"""
        prompt = WesternExpert().build_prompt(_build_input("想吃意面"))

        assert "意面" in prompt
        # §2 菜系词候选：西餐 / 意餐
        assert any(token in prompt for token in ("西餐", "意餐", "意式"))

    def test_fastfood_pizza_input_pushes_to_western_fastfood(self) -> None:
        """用户输入"必胜客欢乐餐厅"时，prompt 必须显式把快餐式披萨场景
        推给 F020 西式快餐专家——避免 LLM 把快餐式披萨误推到本 Node。
        """
        prompt = WesternExpert().build_prompt(_build_input("想吃必胜客欢乐餐厅"))

        # §4 边界澄清：必胜客欢乐餐厅归 F020 西式快餐
        assert "必胜客欢乐餐厅" in prompt
        assert "西式快餐" in prompt

    def test_dairy_input_promotes_allergen_warning(self) -> None:
        """用户输入"奶制品"时，prompt 必须把 dairy / gluten / nuts
        过敏原标签置入，让 LLM 在 matched_allergies 中正确返回。
        """
        prompt = WesternExpert().build_prompt(_build_input("想吃奶香意面"))

        # §4 过敏原注意：奶制品 / 麸质 / 坚果
        assert any(token in prompt for token in ("奶制品", "dairy"))
        assert any(token in prompt for token in ("麸质", "gluten"))

    def test_italian_cuisine_term_input_includes_cuisine_alias(self) -> None:
        """用户输入"意餐"时，prompt 必须把"意餐"作为菜系词候选之一。"""
        prompt = WesternExpert().build_prompt(_build_input("想吃意餐"))

        assert "意餐" in prompt
        # §3 牛排 / 意面 / 披萨 至少其一作为代表菜
        assert any(dish in prompt for dish in ("牛排", "意面", "披萨", "烩饭"))

    def test_french_cuisine_term_input_includes_french_alias(self) -> None:
        """用户输入"法餐"时，prompt 必须把"法式"作为细分菜系候选之一。"""
        prompt = WesternExpert().build_prompt(_build_input("想吃法餐"))

        assert "法式" in prompt
        assert "西餐" in prompt


# ---------------------------------------------------------------------------
# TestWesternParallelSafety — F019 §6 集成：与西式快餐并行时不冲突
# ---------------------------------------------------------------------------


class TestWesternParallelSafety:
    """F019 §6 验收点：与西式快餐并行时不冲突。

    验证多菜系注册表 + build_prompt 的隔离性——西餐 Node 不会因其它
    菜系的 prompt 片段被调用而改变自身行为。
    """

    def test_western_and_western_fastfood_coexist_in_registry(self) -> None:
        # 两个菜系 Node 都注册到统一 registry，顺序由 CUISINE_IDS 决定
        assert "western" in CUISINE_REGISTRY
        assert "western_fastfood" in CUISINE_REGISTRY
        # 各自的 prompt_fragment 互不污染
        from app.agents.cuisines.stubs.western_fastfood import WesternFastfoodExpert

        assert WesternExpert.prompt_fragment != WesternFastfoodExpert.prompt_fragment
        assert "西餐" in WesternExpert.prompt_fragment
        assert "西式快餐" in WesternFastfoodExpert.prompt_fragment

    def test_western_prompt_does_not_leak_western_fastfood_signature(self) -> None:
        """西餐 build_prompt 中只应在边界澄清句里出现"西式快餐"，不应让
        LLM 误以为推荐对象是西式快餐——通过输出不出现西式快餐专属
        代表菜验证。
        """
        prompt = WesternExpert().build_prompt(_build_input("想吃西餐"))

        # 边界澄清需要"西式快餐"作为对照词，但西式快餐专属代表菜不应出现在西餐 prompt 中
        from app.agents.cuisines.stubs.western_fastfood import (
            CUISINE_PROMPT_FRAGMENT as WF_FRAGMENT,
        )

        western_fastfood_signature_dishes = ("汉堡", "薯条", "炸鸡")
        for dish in western_fastfood_signature_dishes:
            assert dish not in prompt, (
                f"西餐 prompt 不应包含西式快餐代表菜 {dish!r}；否则 LLM 会把西餐用户推到西式快餐"
            )
        # 西式快餐 fragment 里没有这些专属菜时此断言平凡成立，留作防回归
        assert any(d in WF_FRAGMENT for d in western_fastfood_signature_dishes)


# ---------------------------------------------------------------------------
# TestWesternParseOutput — F003 §3.3 西餐 Node 自己的解析行为
# ---------------------------------------------------------------------------


class TestWesternParseOutput:
    """西餐继承的 `BaseCuisineExpert.parse_output` 对西餐专用字段。

    验证时使用西餐领域的 representative JSON（牛排 / 意面 / 披萨 关键词集合）。
    """

    def test_parse_happy_path_western_dishes(self) -> None:
        expert = WesternExpert()
        conclusion = "今天适合来份牛排"
        raw = (
            f'{{"conclusion":"{conclusion}",'
            '"keywords":["西餐","牛排","意面","披萨","奶香"],'
            '"matched_allergies":[]}'
        )
        out = expert.parse_output(raw)

        assert out["cuisine_id"] == "western"
        # conclusion 是 LLM 自由文本，只要透传即可
        assert out["conclusion"] == conclusion
        # F019 §2 关键词覆盖：西餐 + 牛排 + 披萨 都在
        assert "西餐" in out["keywords"]
        assert "牛排" in out["keywords"]
        assert "披萨" in out["keywords"]
        # §3 意面作为代表菜
        assert "意面" in out["keywords"]
        # §4 风味词：奶香
        assert "奶香" in out["keywords"]
        assert all(isinstance(k, str) for k in out["keywords"])

    def test_parse_happy_path_with_pasta_and_salad(self) -> None:
        """F019 §3 意面 + §3 沙拉：意面 / 烩饭 / 凯撒沙拉 / 尼斯沙拉——若 LLM 输出
        全套西餐代表菜，parse_output 必须透传不丢字段（让 summary agent 能聚合）。
        """
        expert = WesternExpert()
        raw = (
            '{"conclusion":"今天推荐西餐",'
            '"keywords":["西餐","意面","烩饭","凯撒沙拉","番茄"],'
            '"matched_allergies":[]}'
        )
        out = expert.parse_output(raw)

        assert out["cuisine_id"] == "western"
        # F019 §2 关键词覆盖：西餐
        assert "西餐" in out["keywords"]
        # §3 意面 + 烩饭
        assert "意面" in out["keywords"]
        assert "烩饭" in out["keywords"]
        # §3 沙拉
        assert "凯撒沙拉" in out["keywords"]
        # §4 风味词：番茄
        assert "番茄" in out["keywords"]

    def test_parse_happy_path_with_allergens(self) -> None:
        """F019 §4 过敏原：奶制品 / 麸质 / 坚果——若 LLM 命中应透传到 matched_allergies。"""
        expert = WesternExpert()
        raw = (
            '{"conclusion":"今天推荐西餐",'
            '"keywords":["西餐","牛排"],'
            '"matched_allergies":["dairy","gluten","nuts"]}'
        )
        out = expert.parse_output(raw)

        assert out["cuisine_id"] == "western"
        assert "dairy" in out["matched_allergies"]
        assert "gluten" in out["matched_allergies"]
        assert "nuts" in out["matched_allergies"]

    def test_parse_invalid_json_falls_back(self) -> None:
        expert = WesternExpert()
        out = expert.parse_output("not json at all")

        assert out["cuisine_id"] == "western"
        assert out["conclusion"] == "暂不可推荐"
        assert out["keywords"] == []
        assert out["matched_allergies"] == []
