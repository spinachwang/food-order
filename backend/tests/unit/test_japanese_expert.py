"""F018 — 日料专家专属契约测试.

涵盖 [spec/features/F018-japanese.md §2 / §6] 验收点:

- cuisine_id / display_name / 继承 `BaseCuisineExpert`
- 关键词覆盖：日料 / 日本料理 / 寿司 / 刺身 / 拉面（至少出现于 prompt 片段）
- 与西式快餐（F020）的边界：本 Node 推正餐日料；便利店日式便当归 F020
- §6 测试计划：
  - 用户输入"想吃寿司" → 关键词含"寿司"和"日料"
  - 集成：与西式快餐并行时不冲突（通过注册表 / build_prompt 路径验证）

不重复 F003 `test_base_contract.py` 已覆盖的内容（继承关系 / parse_output
通用 fallback / 全 14 注册表完整性）—— 那些属于通用契约。本文件只断言
**日料专属** 的行为约束，确保 §4 prompt 要点被实际写进代码。
"""

from __future__ import annotations

from decimal import Decimal

from app.agents.cuisines import CUISINE_REGISTRY, BaseCuisineExpert
from app.agents.cuisines.stubs.japanese import CUISINE_PROMPT_FRAGMENT, JapaneseExpert
from app.agents.state import CuisineExpertInput, UserPreferencesDict
from app.core.constants import CUISINE_IDS

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_input(user_message: str, allergies: list[str] | None = None) -> CuisineExpertInput:
    """构造一个最小可用的 `CuisineExpertInput`。

    F018 §6 验收点关注的是 user_message，preferences 用占位即可。
    """
    prefs: UserPreferencesDict = {
        "user_id": "u-f018",
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
# TestJapaneseBasicContract — F003 §3.1 必填属性 + F018 §2 cuisine_id
# ---------------------------------------------------------------------------


class TestJapaneseBasicContract:
    def test_japanese_expert_inherits_base(self) -> None:
        assert issubclass(JapaneseExpert, BaseCuisineExpert)

    def test_cuisine_id_is_japanese(self) -> None:
        # F018 §2 验收点：`cuisine_id="japanese"`
        assert JapaneseExpert.cuisine_id == "japanese"

    def test_display_name_is_riliao(self) -> None:
        # F018 §1 用户故事 + §2 验收要求"日料"作为显示名
        assert JapaneseExpert.display_name == "日料"

    def test_uses_unified_llm_model(self) -> None:
        # F003 §8.1 — 14 个菜系统一 `MiniMax-M3`
        assert JapaneseExpert.llm_model == "MiniMax-M3"

    def test_prompt_fragment_is_non_empty_string(self) -> None:
        # 必须存在菜系专属片段，否则不满足 F003 §3.1 的子类可选 override
        assert isinstance(JapaneseExpert.prompt_fragment, str)
        assert JapaneseExpert.prompt_fragment.strip()


# ---------------------------------------------------------------------------
# TestJapaneseInRegistry — F003 §3.2 注册表
# ---------------------------------------------------------------------------


class TestJapaneseInRegistry:
    def test_registered_in_cuisine_registry(self) -> None:
        assert "japanese" in CUISINE_REGISTRY
        assert CUISINE_REGISTRY["japanese"] is not None

    def test_registry_entry_has_matching_cuisine_id(self) -> None:
        expert = CUISINE_REGISTRY["japanese"]
        assert expert.cuisine_id == "japanese"
        assert expert.display_name == "日料"

    def test_registry_position_matches_cuisine_ids_spec_order(self) -> None:
        # F003 §3.2 / `CUISINE_IDS` 顺序：japanese 在第 9 位
        # （川 / 粤 / 鲁 / 苏 / 浙 / 闽 / 湘 / 徽 / 日料）
        assert CUISINE_IDS.index("japanese") == 8
        assert tuple(CUISINE_REGISTRY.keys())[8] == "japanese"


# ---------------------------------------------------------------------------
# TestJapanesePromptFragment — F018 §2 / §4 prompt 要点的实际落位
# ---------------------------------------------------------------------------


class TestJapanesePromptFragment:
    """验证 F018 §2/§4 关键提示已落到 `CUISINE_PROMPT_FRAGMENT` 字面量中。

    这些是**给 LLM 的字面规则**——它们只有在 prompt 片段里真正出现，
    才能引导模型输出符合 §2 §6 验收点的关键词。这就是 §6 可单测的
    唯一现实接口（不接 LLM）。
    """

    def test_fragment_lists_all_five_keyword_tokens(self) -> None:
        # F018 §2 验收：关键词覆盖 日料 / 日本料理 / 寿司 / 刺身 / 拉面
        # §4 prompt 关键词生成：包含"日料 / 日本料理"中的 1 个
        for token in ("日料", "日本料理", "寿司", "刺身", "拉面"):
            assert token in CUISINE_PROMPT_FRAGMENT, (
                f"F018 §2 要求关键词覆盖 {token!r}；必须出现在 prompt 片段中以引导 LLM 输出"
            )

    def test_fragment_lists_sushi_and_sashimi(self) -> None:
        # F018 §3 寿司 / 刺身：寿司、刺身、鳗鱼饭、亲子丼
        # §2 验收：关键词覆盖 寿司 / 刺身（三大代表之 2）
        for token in ("寿司", "刺身"):
            assert token in CUISINE_PROMPT_FRAGMENT, (
                f"F018 §2 + §3 要求 {token!r} 作为日料代表菜；必须出现在 prompt 片段中"
            )

    def test_fragment_lists_noodle_dishes(self) -> None:
        # F018 §3 面：拉面、乌冬、荞麦面
        # 至少 2 道面食作为关键词候选
        noodles = ("拉面", "乌冬", "荞麦面")
        present = [n for n in noodles if n in CUISINE_PROMPT_FRAGMENT]
        assert len(present) >= 2, (
            f"prompt 片段至少应列出 2 个 F018 §3 面食代表菜作为关键词候选；实际命中={present}"
        )

    def test_fragment_lists_fried_dishes(self) -> None:
        # F018 §3 炸物：天妇罗、可乐饼
        fried = ("天妇罗", "可乐饼")
        present = [d for d in fried if d in CUISINE_PROMPT_FRAGMENT]
        assert present, f"prompt 片段必须列出至少 1 个 F018 §3 炸物代表菜；实际命中={present}"

    def test_fragment_lists_setmeal_dishes(self) -> None:
        # F018 §3 套餐：鳗鱼饭、牛丼
        setmeal = ("鳗鱼饭", "牛丼", "亲子丼")
        present = [d for d in setmeal if d in CUISINE_PROMPT_FRAGMENT]
        assert present, (
            f"prompt 片段必须列出至少 1 个 F018 §3 套餐 / 丼饭代表菜；实际命中={present}"
        )

    def test_fragment_distinguishes_from_western_fastfood(self) -> None:
        # F018 §2 验收 + §4 prompt 要点：与西式快餐（F020）的边界
        # ——本 Node 推正餐日料；便利店日式便当归 F020
        # 必须显式说明这一边界（否则 LLM 会把"日式便当"推到本 Node）
        assert "西式快餐" in CUISINE_PROMPT_FRAGMENT, (
            "F018 §2 + §4 明确要求 prompt 片段含与西式快餐的边界；"
            "缺少会让 LLM 把便利店日式便当误推到日料专家"
        )
        # §4 prompt 要点必须含"便利店" / "便当"以明确边界场景
        assert any(token in CUISINE_PROMPT_FRAGMENT for token in ("便利店", "便当")), (
            "F018 §4 边界澄清必须显式提及便利店或便当场景"
        )

    def test_fragment_lists_signature_flavors(self) -> None:
        # F018 §1 + §4：日料特点：生鲜、刀工、季节感；寿司 / 刺身 / 拉面是三大代表
        # 关键词生成的风味词候选应当至少包含其一
        flavors = ("生鲜", "刀工", "季节感", "和风", "鲜味", "原味")
        present = [f for f in flavors if f in CUISINE_PROMPT_FRAGMENT]
        assert present, f"prompt 片段必须含至少一个 F018 §4 风味词；实际命中={present}"

    def test_fragment_warns_allergens(self) -> None:
        # F018 §4 过敏原注意：刺身 / 海鲜类含贝类、鱼过敏原；部分拉面含小麦 + 蛋
        # 至少命中 1 个过敏原提示词以引导 LLM 在 matched_allergies 中返回
        allergens = ("贝类", "鱼", "海鲜", "shellfish", "fish", "小麦", "麸质", "蛋")
        present = [a for a in allergens if a in CUISINE_PROMPT_FRAGMENT]
        assert present, f"prompt 片段必须含至少 1 个 F018 §4 过敏原提示词；实际命中={present}"

    def test_fragment_specifies_keyword_generation_rule(self) -> None:
        # F018 §4 关键词生成规则：包含"日料 / 日本料理"中的 1 个
        # + 1 个代表菜（"寿司"、"拉面"、"刺身"）
        # + 1 个风味词（"和风"、"生鲜"）
        # 显式规则必须落在片段中（否则 LLM 不会按规则生成）
        assert "关键词" in CUISINE_PROMPT_FRAGMENT
        assert "代表菜" in CUISINE_PROMPT_FRAGMENT
        assert "风味" in CUISINE_PROMPT_FRAGMENT

    def test_fragment_mentions_three_major_representatives(self) -> None:
        # F018 §4 prompt 要点：寿司 / 刺身 / 拉面是日料三大代表
        # 必须显式落到 prompt 以让 LLM 知道日料的辨识度
        for token in ("寿司", "刺身", "拉面"):
            assert token in CUISINE_PROMPT_FRAGMENT


# ---------------------------------------------------------------------------
# TestJapaneseBuildPrompt — F018 §6 行为验收：user_message → prompt 内容
# ---------------------------------------------------------------------------


class TestJapaneseBuildPrompt:
    """F018 §6 测试计划：用户输入"想吃寿司" / "想吃刺身" / "想吃拉面" → 关键词覆盖。

    不接 LLM 验证 LLM 行为，而是验证 prompt 模板确实提供了产生该
    行为所需的全部上下文（用户输入 + 菜系词 + 风味词 + 与西式快餐边界）。
    """

    def test_sushi_input_prompt_includes_sushi_and_riliao(self) -> None:
        """F018 §6 验收点：用户输入"想吃寿司"时，build_prompt 输出必须
        既含用户的原文又含菜系词"日料"，从而 LLM 可按规则产出含"寿司"
        和"日料"的关键词集。
        """
        prompt = JapaneseExpert().build_prompt(_build_input("想吃寿司"))

        # 用户原始输入被注入（F003 §4 模板必含 {message}）
        assert "想吃寿司" in prompt
        # F018 §2 菜系词：日料 / 日本料理 至少其一
        assert "日料" in prompt
        # §2 验收：与西式快餐的边界必须在 prompt 中
        assert "西式快餐" in prompt
        # §3 寿司 / 刺身代表菜至少出现一个（§4 三大代表）
        assert "寿司" in prompt

    def test_sashimi_input_prompt_carries_sashimi_term(self) -> None:
        """用户输入"想吃刺身"时，prompt 必须把"刺身"作为代表菜候选。"""
        prompt = JapaneseExpert().build_prompt(_build_input("想吃刺身"))

        assert "刺身" in prompt
        # §2 菜系词候选：日料 / 日本料理
        assert any(token in prompt for token in ("日料", "日本料理"))

    def test_ramen_input_prompt_carries_ramen_term(self) -> None:
        """用户输入"想吃拉面"时，prompt 必须把"拉面"作为代表菜候选（§4 三大代表）。"""
        prompt = JapaneseExpert().build_prompt(_build_input("想吃拉面"))

        assert "拉面" in prompt
        # §2 菜系词候选：日料 / 日本料理
        assert any(token in prompt for token in ("日料", "日本料理"))
        # §4 拉面过敏原：小麦 / 蛋
        assert any(token in prompt for token in ("小麦", "麸质", "蛋"))

    def test_convenience_store_input_pushes_to_western_fastfood(self) -> None:
        """用户输入"便利店便当"时，prompt 必须显式把便利店日式便当场景
        推给 F020 西式快餐专家——避免 LLM 把便利店便当误推到本 Node。
        """
        prompt = JapaneseExpert().build_prompt(_build_input("想吃便利店便当"))

        # §4 边界澄清：便利店便当归 F020 西式快餐
        assert "便利店" in prompt
        assert "西式快餐" in prompt

    def test_raw_fish_input_promotes_allergen_warning(self) -> None:
        """用户输入"刺身"（生鲜）时，prompt 必须把"鱼" / "海鲜" / "贝类"
        过敏原标签置入，让 LLM 在 matched_allergies 中正确返回。
        """
        prompt = JapaneseExpert().build_prompt(_build_input("想吃刺身"))

        # §4 过敏原注意：刺身 / 海鲜类含贝类、鱼过敏原
        assert any(token in prompt for token in ("鱼", "海鲜", "贝类", "shellfish", "fish"))

    def test_japanese_cuisine_term_input_includes_cuisine_alias(self) -> None:
        """用户输入"日本料理"时，prompt 必须把"日本料理"作为菜系词候选之一。"""
        prompt = JapaneseExpert().build_prompt(_build_input("想吃日本料理"))

        assert "日本料理" in prompt
        # §3 寿司 / 刺身 / 拉面 至少其一作为代表菜
        assert any(dish in prompt for dish in ("寿司", "刺身", "拉面"))


# ---------------------------------------------------------------------------
# TestJapaneseParallelSafety — F018 §6 集成：与西式快餐并行时不冲突
# ---------------------------------------------------------------------------


class TestJapaneseParallelSafety:
    """F018 §6 验收点：与西式快餐并行时不冲突。

    验证多菜系注册表 + build_prompt 的隔离性——日料 Node 不会因其它
    菜系的 prompt 片段被调用而改变自身行为。
    """

    def test_japanese_and_western_fastfood_coexist_in_registry(self) -> None:
        # 两个菜系 Node 都注册到统一 registry，顺序由 CUISINE_IDS 决定
        assert "japanese" in CUISINE_REGISTRY
        assert "western_fastfood" in CUISINE_REGISTRY
        # 各自的 prompt_fragment 互不污染
        from app.agents.cuisines.stubs.western_fastfood import WesternFastfoodExpert

        assert JapaneseExpert.prompt_fragment != WesternFastfoodExpert.prompt_fragment
        assert "日料" in JapaneseExpert.prompt_fragment
        assert "西式快餐" in WesternFastfoodExpert.prompt_fragment

    def test_japanese_prompt_does_not_leak_western_fastfood_signature(self) -> None:
        """日料 build_prompt 中只应在边界澄清句里出现"西式快餐"，不应让
        LLM 误以为推荐对象是西式快餐——通过输出不出现西式快餐专属
        代表菜验证。
        """
        prompt = JapaneseExpert().build_prompt(_build_input("想吃日料"))

        # 边界澄清需要"西式快餐"作为对照词，但西式快餐专属代表菜不应出现在日料 prompt 中
        from app.agents.cuisines.stubs.western_fastfood import (
            CUISINE_PROMPT_FRAGMENT as WF_FRAGMENT,
        )

        western_fastfood_signature_dishes = ("汉堡", "薯条", "炸鸡", "披萨")
        for dish in western_fastfood_signature_dishes:
            assert dish not in prompt, (
                f"日料 prompt 不应包含西式快餐代表菜 {dish!r}；否则 LLM 会把日料用户推到西式快餐"
            )
        # 西式快餐 fragment 里没有这些专属菜时此断言平凡成立，留作防回归
        assert any(d in WF_FRAGMENT for d in western_fastfood_signature_dishes)


# ---------------------------------------------------------------------------
# TestJapaneseParseOutput — F003 §3.3 日料 Node 自己的解析行为
# ---------------------------------------------------------------------------


class TestJapaneseParseOutput:
    """日料继承的 `BaseCuisineExpert.parse_output` 对日料专用字段。

    验证时使用日料领域的 representative JSON（寿司 / 刺身 / 拉面 关键词集合）。
    """

    def test_parse_happy_path_japanese_dishes(self) -> None:
        expert = JapaneseExpert()
        conclusion = "今天适合来份寿司"
        raw = (
            f'{{"conclusion":"{conclusion}",'
            '"keywords":["日料","寿司","刺身","拉面","和风"],'
            '"matched_allergies":[]}'
        )
        out = expert.parse_output(raw)

        assert out["cuisine_id"] == "japanese"
        # conclusion 是 LLM 自由文本，只要透传即可
        assert out["conclusion"] == conclusion
        # F018 §2 关键词覆盖：日料 + 寿司 + 刺身 + 拉面 都在
        assert "日料" in out["keywords"]
        assert "寿司" in out["keywords"]
        assert "刺身" in out["keywords"]
        assert "拉面" in out["keywords"]
        # §4 风味词：和风
        assert "和风" in out["keywords"]
        assert all(isinstance(k, str) for k in out["keywords"])

    def test_parse_happy_path_with_noodle_and_fried(self) -> None:
        """F018 §3 面 + §3 炸物：拉面 / 乌冬 / 天妇罗 / 可乐饼——若 LLM 输出
        全套日料代表菜，parse_output 必须透传不丢字段（让 summary agent 能聚合）。"""
        expert = JapaneseExpert()
        raw = (
            '{"conclusion":"今天推荐日料",'
            '"keywords":["日料","拉面","乌冬","天妇罗","可乐饼"],'
            '"matched_allergies":[]}'
        )
        out = expert.parse_output(raw)

        assert out["cuisine_id"] == "japanese"
        # F018 §2 关键词覆盖几项全在
        assert "日料" in out["keywords"]
        # §3 面食两类
        assert "拉面" in out["keywords"]
        assert "乌冬" in out["keywords"]
        # §3 炸物两类
        assert "天妇罗" in out["keywords"]
        assert "可乐饼" in out["keywords"]

    def test_parse_happy_path_with_allergens(self) -> None:
        """F018 §4 过敏原：刺身 / 海鲜含贝类、鱼——若 LLM 命中应透传到 matched_allergies。"""
        expert = JapaneseExpert()
        raw = (
            '{"conclusion":"今天推荐日料",'
            '"keywords":["日料","寿司"],'
            '"matched_allergies":["shellfish","fish"]}'
        )
        out = expert.parse_output(raw)

        assert out["cuisine_id"] == "japanese"
        assert "shellfish" in out["matched_allergies"]
        assert "fish" in out["matched_allergies"]

    def test_parse_invalid_json_falls_back(self) -> None:
        expert = JapaneseExpert()
        out = expert.parse_output("not json at all")

        assert out["cuisine_id"] == "japanese"
        assert out["conclusion"] == "暂不可推荐"
        assert out["keywords"] == []
        assert out["matched_allergies"] == []
