"""F013 — 苏菜专家专属契约测试.

涵盖 [spec/features/F013-suzhou.md §2 / §6] 验收点:

- cuisine_id / display_name / 继承 `BaseCuisineExpert`
- 关键词覆盖：苏菜 / 江苏 / 苏帮 / 淮扬（至少出现于 prompt 片段）
- 与浙菜区别：苏更"甜"，浙更"鲜"——prompt 必须澄清
- 与粤菜区别：广式 + 海鲜 vs 江淮河鲜 + 刀工
- §6 测试计划：用户输入"精致清淡偏甜" → 关键词含"苏菜"或"淮扬"
  （通过 prompt 注入路径验证——不接 LLM，验 build_prompt 上下文）

不重复 F003 `test_base_contract.py` 已覆盖的内容（继承关系 / parse_output
通用 fallback / 全 14 注册表完整性）—— 那些属于通用契约。本文件只断言
**苏菜专属** 的行为约束，确保 §4 prompt 要点被实际写进代码。
"""

from __future__ import annotations

from decimal import Decimal

from app.agents.cuisines import CUISINE_REGISTRY, BaseCuisineExpert
from app.agents.cuisines.stubs.suzhou import CUISINE_PROMPT_FRAGMENT, SuzhouExpert
from app.agents.state import CuisineExpertInput, UserPreferencesDict
from app.core.constants import CUISINE_IDS

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_input(user_message: str, allergies: list[str] | None = None) -> CuisineExpertInput:
    """构造一个最小可用的 `CuisineExpertInput`。

    F013 §6 验收点关注的是 user_message，preferences 用占位即可。
    """
    prefs: UserPreferencesDict = {
        "user_id": "u-f013",
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
# TestSuzhouBasicContract — F003 §3.1 必填属性 + F013 §2 cuisine_id
# ---------------------------------------------------------------------------


class TestSuzhouBasicContract:
    def test_suzhou_expert_inherits_base(self) -> None:
        assert issubclass(SuzhouExpert, BaseCuisineExpert)

    def test_cuisine_id_is_suzhou(self) -> None:
        # F013 §2 验收点：`cuisine_id="suzhou"`
        assert SuzhouExpert.cuisine_id == "suzhou"

    def test_display_name_is_sucai(self) -> None:
        # F013 §1 用户故事 + §2 验收要求"苏菜"作为显示名
        assert SuzhouExpert.display_name == "苏菜"

    def test_uses_unified_llm_model(self) -> None:
        # F003 §8.1 — 14 个菜系统一 `MiniMax-M3`
        assert SuzhouExpert.llm_model == "MiniMax-M3"

    def test_prompt_fragment_is_non_empty_string(self) -> None:
        # 必须存在菜系专属片段，否则不满足 F003 §3.1 的子类可选 override
        assert isinstance(SuzhouExpert.prompt_fragment, str)
        assert SuzhouExpert.prompt_fragment.strip()


# ---------------------------------------------------------------------------
# TestSuzhouInRegistry — F003 §3.2 注册表
# ---------------------------------------------------------------------------


class TestSuzhouInRegistry:
    def test_registered_in_cuisine_registry(self) -> None:
        assert "suzhou" in CUISINE_REGISTRY
        assert CUISINE_REGISTRY["suzhou"] is not None

    def test_registry_entry_has_matching_cuisine_id(self) -> None:
        expert = CUISINE_REGISTRY["suzhou"]
        assert expert.cuisine_id == "suzhou"
        assert expert.display_name == "苏菜"

    def test_registry_position_matches_cuisine_ids_spec_order(self) -> None:
        # F003 §3.2 / `CUISINE_IDS` 顺序：suzhou 在第 4 位（川/粤/鲁/苏）
        assert CUISINE_IDS.index("suzhou") == 3
        assert tuple(CUISINE_REGISTRY.keys())[3] == "suzhou"


# ---------------------------------------------------------------------------
# TestSuzhouPromptFragment — F013 §2 / §4 prompt 要点的实际落位
# ---------------------------------------------------------------------------


class TestSuzhouPromptFragment:
    """验证 F013 §2/§4 关键提示已落到 `CUISINE_PROMPT_FRAGMENT` 字面量中。

    这些是**给 LLM 的字面规则**——它们只有在 prompt 片段里真正出现，
    才能引导模型输出符合 §2 §6 验收点的关键词。这就是 §6 可单测的
    唯一现实接口（不接 LLM）。
    """

    def test_fragment_lists_all_four_cuisine_terms(self) -> None:
        # F013 §2 验收：关键词覆盖 苏菜 / 江苏 / 苏帮 / 淮扬
        # §4 prompt 关键词生成：菜系词（苏菜 / 江苏 / 苏帮 / 淮扬）中 1-2 个
        for token in ("苏菜", "江苏", "苏帮", "淮扬"):
            assert token in CUISINE_PROMPT_FRAGMENT, (
                f"F013 §2 要求关键词覆盖 {token!r}；必须出现在 prompt 片段中以引导 LLM 输出"
            )

    def test_fragment_lists_representative_dishes(self) -> None:
        # F013 §3 经典：松鼠鳜鱼 / 蟹粉狮子头 / 响油鳝糊 / 盐水鸭
        # 淮扬代表：蟹黄汤包 / 文楼干贝 / 扬州炒饭
        # 至少要有 3 道作为关键词候选
        classics = ("松鼠鳜鱼", "蟹粉狮子头", "响油鳝糊", "盐水鸭", "蟹黄汤包", "扬州炒饭")
        present = [d for d in classics if d in CUISINE_PROMPT_FRAGMENT]
        assert len(present) >= 3, (
            f"prompt 片段至少应列出 3 个 F013 §3 代表菜作为关键词候选；实际命中={present}"
        )

    def test_fragment_distinguishes_from_zhejiang(self) -> None:
        # F013 §4：与浙菜区别——苏更"甜"，浙更"鲜"。
        # 这是 §2 验收"与浙菜的精致区分"的实现位。
        assert "浙菜" in CUISINE_PROMPT_FRAGMENT, (
            "F013 §4 明确要求 prompt 片段含与浙菜的区别；缺少会让 LLM 把'清淡偏甜'误推为浙菜"
        )
        # 同时需说明苏偏甜、浙偏清淡的差异化方向
        assert "甜" in CUISINE_PROMPT_FRAGMENT
        # 苏的"甜"必须显式呈现，不能只让浙独占"鲜"
        # （粗粒度：出现"甜"字即视为提示了苏的甜鲜属性）

    def test_fragment_distinguishes_from_cantonese(self) -> None:
        # F013 §4：与粤菜区别——粤更广式 + 海鲜；苏更江淮河鲜 + 刀工。
        assert "粤菜" in CUISINE_PROMPT_FRAGMENT, "F013 §4 明确要求 prompt 片段含与粤菜的区别"

    def test_fragment_mentions_signature_flavors(self) -> None:
        # F013 §1 + §4：苏菜特点为精致、偏甜、刀工讲究、原汁原味
        # 关键词生成的风味词候选应当至少包含其一
        flavors = ("精致", "微甜", "刀工", "原汁原味")
        present = [f for f in flavors if f in CUISINE_PROMPT_FRAGMENT]
        assert present, f"prompt 片段必须含至少一个 F013 §4 风味词；实际命中={present}"

    def test_fragment_warns_allergens(self) -> None:
        # F013 §4 过敏原注意：蟹粉 / 鱼圆 / 河鲜——忌 shellfish / fish 者需避
        # 至少命中 1 个过敏原提示词以引导 LLM 在 matched_allergies 中返回
        allergens = ("蟹粉", "鱼圆", "河鲜", "shellfish", "fish")
        present = [a for a in allergens if a in CUISINE_PROMPT_FRAGMENT]
        assert present, f"prompt 片段必须含至少 1 个 F013 §4 过敏原提示词；实际命中={present}"


# ---------------------------------------------------------------------------
# TestSuzhouBuildPrompt — F013 §6 行为验收：user_message → prompt 内容
# ---------------------------------------------------------------------------


class TestSuzhouBuildPrompt:
    """F013 §6 测试计划：用户输入"精致清淡偏甜" → 关键词含"苏菜"或"淮扬"。

    不接 LLM 验证 LLM 行为，而是验证 prompt 模板确实提供了产生该
    行为所需的全部上下文（用户输入 + 菜系词 + 风味词 + 浙菜区别澄清）。
    """

    def test_qingdan_piantian_input_prompt_includes_sucai_or_huaiyang(self) -> None:
        """F013 §6 验收点：用户输入"精致清淡偏甜"时，build_prompt 输出
        必须既含用户的"精致 / 清淡 / 偏甜"原文又含菜系词"苏菜"或"淮扬"，
        同时含与浙菜的区分澄清，从而 LLM 可按规则产出含"苏菜 / 淮扬"
        的关键词集。
        """
        prompt = SuzhouExpert().build_prompt(_build_input("精致清淡偏甜"))

        # 用户原始输入被注入（F003 §4 模板必含 {message}）
        assert "精致清淡偏甜" in prompt
        # F013 §2 菜系词：苏菜 / 江苏 / 苏帮 / 淮扬 至少其一
        assert any(token in prompt for token in ("苏菜", "江苏", "苏帮", "淮扬"))
        # F013 §4 与浙菜的区别澄清：必须在 prompt 中（否则 LLM 不知往苏还是浙推）
        assert "浙菜" in prompt
        # F013 §4 风味词候选：精致 / 微甜 / 刀工
        assert any(token in prompt for token in ("精致", "微甜", "刀工"))

    def test_jiangsu_input_prompt_carries_jiangsu_term(self) -> None:
        """用户输入"江苏菜"时，prompt 必须把"江苏"作为菜系词候选之一。"""
        prompt = SuzhouExpert().build_prompt(_build_input("想吃江苏菜"))

        assert "江苏" in prompt
        assert "苏菜" in prompt
        # §3 淮扬代表菜至少出现一个
        assert any(dish in prompt for dish in ("蟹黄汤包", "文楼干贝", "扬州炒饭"))

    def test_huaiyang_input_prompt_carries_huaiyang_term(self) -> None:
        """用户输入"淮扬菜"时，prompt 必须把"淮扬"作为菜系词候选。"""
        prompt = SuzhouExpert().build_prompt(_build_input("想吃淮扬菜"))

        assert "淮扬" in prompt
        # §3 淮扬代表菜至少出现一个
        assert any(dish in prompt for dish in ("蟹黄汤包", "文楼干贝", "扬州炒饭"))


# ---------------------------------------------------------------------------
# TestSuzhouParseOutput — F003 §3.3 苏菜 Node 自己的解析行为
# ---------------------------------------------------------------------------


class TestSuzhouParseOutput:
    """苏菜继承的 `BaseCuisineExpert.parse_output` 对苏菜专用字段。

    验证时使用苏菜领域的 representative JSON（苏帮 / 淮扬 关键词集合）。
    """

    def test_parse_happy_path_sucai_dishes(self) -> None:
        expert = SuzhouExpert()
        conclusion = "今天适合来份松鼠鳜鱼"
        raw = (
            f'{{"conclusion":"{conclusion}",'
            '"keywords":["苏菜","松鼠鳜鱼","蟹粉狮子头","淮扬","精致"],'
            '"matched_allergies":[]}'
        )
        out = expert.parse_output(raw)

        assert out["cuisine_id"] == "suzhou"
        # conclusion 是 LLM 自由文本，只要透传即可
        assert out["conclusion"] == conclusion
        # F013 §2 关键词覆盖：苏菜 / 淮扬 都在
        assert "苏菜" in out["keywords"]
        assert "淮扬" in out["keywords"]
        # §3 代表菜
        assert "松鼠鳜鱼" in out["keywords"]
        assert "蟹粉狮子头" in out["keywords"]
        assert all(isinstance(k, str) for k in out["keywords"])

    def test_parse_happy_path_with_allergens(self) -> None:
        """F013 §4 过敏原：蟹粉 / 鱼圆——若 LLM 命中应透传到 matched_allergies。"""
        expert = SuzhouExpert()
        raw = (
            '{"conclusion":"今天推荐苏菜",'
            '"keywords":["苏菜","蟹粉狮子头","蟹黄汤包"],'
            '"matched_allergies":["shellfish","fish"]}'
        )
        out = expert.parse_output(raw)

        assert out["cuisine_id"] == "suzhou"
        assert "shellfish" in out["matched_allergies"]
        assert "fish" in out["matched_allergies"]

    def test_parse_invalid_json_falls_back(self) -> None:
        expert = SuzhouExpert()
        out = expert.parse_output("not json at all")

        assert out["cuisine_id"] == "suzhou"
        assert out["conclusion"] == "暂不可推荐"
        assert out["keywords"] == []
        assert out["matched_allergies"] == []
