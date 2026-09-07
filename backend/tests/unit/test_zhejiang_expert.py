"""F014 — 浙菜专家专属契约测试.

涵盖 [spec/features/F014-zhejiang.md §2 / §6] 验收点:

- cuisine_id / display_name / 继承 `BaseCuisineExpert`
- 关键词覆盖：浙菜 / 浙江 / 杭帮 / 宁波 / 温州（至少出现于 prompt 片段）
- 与苏菜区别：浙更"鲜"，苏更"甜"——prompt 必须澄清
- 与粤菜区别：清淡江浙 vs 广式海鲜
- §6 测试计划：用户输入"江浙清淡" → 关键词含"浙菜"或"杭帮"
  （通过 prompt 注入路径验证——不接 LLM，验 build_prompt 上下文）

不重复 F003 `test_base_contract.py` 已覆盖的内容（继承关系 / parse_output
通用 fallback / 全 14 注册表完整性）—— 那些属于通用契约。本文件只断言
**浙菜专属** 的行为约束，确保 §4 prompt 要点被实际写进代码。
"""
from __future__ import annotations

from decimal import Decimal

from app.agents.cuisines import CUISINE_REGISTRY, BaseCuisineExpert
from app.agents.cuisines.stubs.zhejiang import CUISINE_PROMPT_FRAGMENT, ZhejiangExpert
from app.agents.state import CuisineExpertInput, UserPreferencesDict
from app.core.constants import CUISINE_IDS

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_input(user_message: str, allergies: list[str] | None = None) -> CuisineExpertInput:
    """构造一个最小可用的 `CuisineExpertInput`。

    F014 §6 验收点关注的是 user_message，preferences 用占位即可。
    """
    prefs: UserPreferencesDict = {
        "user_id": "u-f014",
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
# TestZhejiangBasicContract — F003 §3.1 必填属性 + F014 §2 cuisine_id
# ---------------------------------------------------------------------------


class TestZhejiangBasicContract:
    def test_zhejiang_expert_inherits_base(self) -> None:
        assert issubclass(ZhejiangExpert, BaseCuisineExpert)

    def test_cuisine_id_is_zhejiang(self) -> None:
        # F014 §2 验收点：`cuisine_id="zhejiang"`
        assert ZhejiangExpert.cuisine_id == "zhejiang"

    def test_display_name_is_zhecai(self) -> None:
        # F014 §1 用户故事 + §2 验收要求"浙菜"作为显示名
        assert ZhejiangExpert.display_name == "浙菜"

    def test_uses_unified_llm_model(self) -> None:
        # F003 §8.1 — 14 个菜系统一 `MiniMax-M3`
        assert ZhejiangExpert.llm_model == "MiniMax-M3"

    def test_prompt_fragment_is_non_empty_string(self) -> None:
        # 必须存在菜系专属片段，否则不满足 F003 §3.1 的子类可选 override
        assert isinstance(ZhejiangExpert.prompt_fragment, str)
        assert ZhejiangExpert.prompt_fragment.strip()


# ---------------------------------------------------------------------------
# TestZhejiangInRegistry — F003 §3.2 注册表
# ---------------------------------------------------------------------------


class TestZhejiangInRegistry:
    def test_registered_in_cuisine_registry(self) -> None:
        assert "zhejiang" in CUISINE_REGISTRY
        assert CUISINE_REGISTRY["zhejiang"] is not None

    def test_registry_entry_has_matching_cuisine_id(self) -> None:
        expert = CUISINE_REGISTRY["zhejiang"]
        assert expert.cuisine_id == "zhejiang"
        assert expert.display_name == "浙菜"

    def test_registry_position_matches_cuisine_ids_spec_order(self) -> None:
        # F003 §3.2 / `CUISINE_IDS` 顺序：zhejiang 在第 5 位（川/粤/鲁/苏/浙）
        assert CUISINE_IDS.index("zhejiang") == 4
        assert tuple(CUISINE_REGISTRY.keys())[4] == "zhejiang"


# ---------------------------------------------------------------------------
# TestZhejiangPromptFragment — F014 §2 / §4 prompt 要点的实际落位
# ---------------------------------------------------------------------------


class TestZhejiangPromptFragment:
    """验证 F014 §2/§4 关键提示已落到 `CUISINE_PROMPT_FRAGMENT` 字面量中。

    这些是**给 LLM 的字面规则**——它们只有在 prompt 片段里真正出现，
    才能引导模型输出符合 §2 §6 验收点的关键词。这就是 §6 可单测的
    唯一现实接口（不接 LLM）。
    """

    def test_fragment_lists_all_five_cuisine_terms(self) -> None:
        # F014 §2 验收：关键词覆盖 浙菜 / 浙江 / 杭帮 / 宁波 / 温州
        # §4 prompt 关键词生成：菜系词（浙/浙江/杭帮/浙菜/宁波/温州）中 1-2 个
        for token in ("浙菜", "浙江", "杭帮", "宁波", "温州"):
            assert token in CUISINE_PROMPT_FRAGMENT, (
                f"F014 §2 要求关键词覆盖 {token!r}；必须出现在 prompt 片段中以引导 LLM 输出"
            )

    def test_fragment_lists_qingxian_flavor_token(self) -> None:
        # F014 §2 验收：与苏菜 / 粤菜的"清淡"区分
        # §4 prompt 关键词生成：含 1 个风味词（"清鲜"）
        assert "清鲜" in CUISINE_PROMPT_FRAGMENT

    def test_fragment_lists_hangbang_representative_dishes(self) -> None:
        # F014 §3 杭帮：西湖醋鱼 / 东坡肉 / 龙井虾仁 / 宋嫂鱼羹
        # 至少要有 2 道作为关键词候选
        hangbang = ("西湖醋鱼", "东坡肉", "龙井虾仁", "宋嫂鱼羹")
        present = [d for d in hangbang if d in CUISINE_PROMPT_FRAGMENT]
        assert len(present) >= 2, (
            f"prompt 片段至少应列出 2 个 F014 §3 杭帮代表菜作为关键词候选；"
            f"实际命中={present}"
        )

    def test_fragment_lists_ningbo_representative_dishes(self) -> None:
        # F014 §3 宁波：宁波汤圆 / 雪菜黄鱼（红烧肉与苏菜重叠，仅列余下）
        # §2 验收要求覆盖"宁波"——若 prompt 不给宁波代表菜，
        # LLM 只能泛泛输出"宁波菜"
        ningbo = ("宁波汤圆", "雪菜黄鱼")
        present = [d for d in ningbo if d in CUISINE_PROMPT_FRAGMENT]
        assert present, (
            f"prompt 片段必须列出至少 1 个 F014 §3 宁波代表菜以支持 §2 '宁波' "
            f"关键词；实际命中={present}"
        )

    def test_fragment_lists_wenzhou_representative_dishes(self) -> None:
        # F014 §3 温州：鱼丸 / 三丝敲鱼
        # §2 验收要求覆盖"温州"
        wenzhou = ("鱼丸", "三丝敲鱼")
        present = [d for d in wenzhou if d in CUISINE_PROMPT_FRAGMENT]
        assert present, (
            f"prompt 片段必须列出至少 1 个 F014 §3 温州代表菜以支持 §2 '温州' "
            f"关键词；实际命中={present}"
        )

    def test_fragment_distinguishes_from_suzhou(self) -> None:
        # F014 §2 验收：与苏菜的清淡区分
        # §4 关键提示：浙更"鲜"，苏更"甜"
        assert "苏菜" in CUISINE_PROMPT_FRAGMENT, (
            "F014 §4 明确要求 prompt 片段含与苏菜的区别；"
            "缺少会让 LLM 把'清淡'误推为苏菜"
        )
        # 同时需说明浙偏"鲜"、苏偏"甜"的差异化方向
        # （粗粒度：出现"鲜"字即视为提示了浙的清鲜属性）
        assert "鲜" in CUISINE_PROMPT_FRAGMENT

    def test_fragment_distinguishes_from_cantonese(self) -> None:
        # F014 §2 验收：与粤菜的清淡区分
        # §4 prompt 要点：浙更江浙本土，粤更广式海鲜
        assert "粤菜" in CUISINE_PROMPT_FRAGMENT, (
            "F014 §4 明确要求 prompt 片段含与粤菜的区别；"
            "缺少会让 LLM 把'清淡'误推为粤菜"
        )

    def test_fragment_mentions_signature_flavors(self) -> None:
        # F014 §1 + §4：浙菜特点为清鲜、细巧、注重原味
        # 关键词生成的风味词候选应当至少包含其一
        flavors = ("清鲜", "细巧", "原汁原味", "嫩滑")
        present = [f for f in flavors if f in CUISINE_PROMPT_FRAGMENT]
        assert present, f"prompt 片段必须含至少一个 F014 §4 风味词；实际命中={present}"

    def test_fragment_warns_allergens(self) -> None:
        # F014 §4 过敏原注意：浙菜多用黄酒；少数含虾仁 / 蟹
        # 至少命中 1 个过敏原提示词以引导 LLM 在 matched_allergies 中返回
        allergens = ("黄酒", "虾", "蟹", "shellfish", "fish")
        present = [a for a in allergens if a in CUISINE_PROMPT_FRAGMENT]
        assert present, (
            f"prompt 片段必须含至少 1 个 F014 §4 过敏原提示词；实际命中={present}"
        )

    def test_fragment_specifies_keyword_generation_rule(self) -> None:
        # F014 §4 关键词生成规则：菜系词（浙菜 / 浙江 / 杭帮 / 宁波 / 温州）
        # 中 1-2 个 + 1 个代表菜 + 1 个风味词（"清鲜"）
        # 显式规则必须落在片段中（否则 LLM 不会按规则生成）
        # 粗粒度：片段必须同时含"关键词"与"风味"二字以提示规则结构
        assert "关键词" in CUISINE_PROMPT_FRAGMENT
        assert "风味" in CUISINE_PROMPT_FRAGMENT


# ---------------------------------------------------------------------------
# TestZhejiangBuildPrompt — F014 §6 行为验收：user_message → prompt 内容
# ---------------------------------------------------------------------------


class TestZhejiangBuildPrompt:
    """F014 §6 测试计划：用户输入"江浙清淡" → 关键词含"浙菜"或"杭帮"。

    不接 LLM 验证 LLM 行为，而是验证 prompt 模板确实提供了产生该
    行为所需的全部上下文（用户输入 + 菜系词 + 风味词 + 苏菜/粤菜区别澄清）。
    """

    def test_jiangzhe_qingdan_input_prompt_includes_zhecai_or_hangbang(self) -> None:
        """F014 §6 验收点：用户输入"江浙清淡"时，build_prompt 输出必须既含
        用户的"江浙清淡"原文又含菜系词"浙菜"或"杭帮"，同时含与苏菜/粤菜的
        区分澄清，从而 LLM 可按规则产出含"浙菜 / 杭帮"的关键词集。
        """
        prompt = ZhejiangExpert().build_prompt(_build_input("想吃江浙清淡"))

        # 用户原始输入被注入（F003 §4 模板必含 {message}）
        assert "江浙清淡" in prompt
        # F014 §2 菜系词：浙菜 / 浙江 / 杭帮 / 宁波 / 温州 至少其一
        assert any(token in prompt for token in ("浙菜", "浙江", "杭帮"))
        # F014 §4 与苏菜的区别澄清：必须在 prompt 中（否则 LLM 不知往苏还是浙推）
        assert "苏菜" in prompt
        # F014 §4 与粤菜的区别澄清：必须在 prompt 中
        assert "粤菜" in prompt
        # F014 §4 风味词候选：清鲜 / 细巧 / 原汁原味
        assert any(token in prompt for token in ("清鲜", "细巧", "原汁原味"))

    def test_hangbang_input_prompt_carries_hangbang_term(self) -> None:
        """用户输入"杭帮菜"时，prompt 必须把"杭帮"作为菜系词候选。"""
        prompt = ZhejiangExpert().build_prompt(_build_input("想吃杭帮菜"))

        assert "杭帮" in prompt
        # §3 杭帮代表菜至少出现一个
        assert any(dish in prompt for dish in ("西湖醋鱼", "东坡肉", "龙井虾仁", "宋嫂鱼羹"))

    def test_ningbo_input_prompt_carries_ningbo_term(self) -> None:
        """用户输入"宁波菜"时，prompt 必须把"宁波"作为菜系词候选。"""
        prompt = ZhejiangExpert().build_prompt(_build_input("想吃宁波菜"))

        assert "宁波" in prompt
        # §3 宁波代表菜至少出现一个
        assert any(dish in prompt for dish in ("宁波汤圆", "雪菜黄鱼"))

    def test_wenzhou_input_prompt_carries_wenzhou_term(self) -> None:
        """用户输入"温州菜"时，prompt 必须把"温州"作为菜系词候选。"""
        prompt = ZhejiangExpert().build_prompt(_build_input("想吃温州菜"))

        assert "温州" in prompt
        # §3 温州代表菜至少出现一个
        assert any(dish in prompt for dish in ("鱼丸", "三丝敲鱼"))


# ---------------------------------------------------------------------------
# TestZhejiangParseOutput — F003 §3.3 浙菜 Node 自己的解析行为
# ---------------------------------------------------------------------------


class TestZhejiangParseOutput:
    """浙菜继承的 `BaseCuisineExpert.parse_output` 对浙菜专用字段。

    验证时使用浙菜领域的 representative JSON（杭帮 / 宁波 / 温州 关键词集合）。
    """

    def test_parse_happy_path_hangbang_dishes(self) -> None:
        expert = ZhejiangExpert()
        conclusion = "今天适合来份西湖醋鱼"
        raw = (
            f'{{"conclusion":"{conclusion}",'
            '"keywords":["浙菜","西湖醋鱼","东坡肉","清鲜"],'
            '"matched_allergies":[]}'
        )
        out = expert.parse_output(raw)

        assert out["cuisine_id"] == "zhejiang"
        # conclusion 是 LLM 自由文本，只要透传即可
        assert out["conclusion"] == conclusion
        # F014 §2 关键词覆盖：浙菜 在
        assert "浙菜" in out["keywords"]
        # §3 杭帮代表菜
        assert "西湖醋鱼" in out["keywords"]
        assert "东坡肉" in out["keywords"]
        assert "清鲜" in out["keywords"]
        assert all(isinstance(k, str) for k in out["keywords"])

    def test_parse_happy_path_with_regional_subcuisines(self) -> None:
        """F014 §3 杭帮 + 宁波 + 温州 三派都出现于 LLM 输出时，parse_output
        必须透传不丢字段（让 summary agent 能按需聚合）。"""
        expert = ZhejiangExpert()
        raw = (
            '{"conclusion":"今天推荐浙菜",'
            '"keywords":["浙菜","杭帮","宁波","温州","龙井虾仁"],'
            '"matched_allergies":[]}'
        )
        out = expert.parse_output(raw)

        assert out["cuisine_id"] == "zhejiang"
        # F014 §2 关键词覆盖五项全在
        assert "浙菜" in out["keywords"]
        assert "杭帮" in out["keywords"]
        assert "宁波" in out["keywords"]
        assert "温州" in out["keywords"]

    def test_parse_happy_path_with_allergens(self) -> None:
        """F014 §4 过敏原：黄酒 / 虾 / 蟹——若 LLM 命中应透传到 matched_allergies。"""
        expert = ZhejiangExpert()
        raw = (
            '{"conclusion":"今天推荐浙菜",'
            '"keywords":["浙菜","龙井虾仁"],'
            '"matched_allergies":["shellfish","fish"]}'
        )
        out = expert.parse_output(raw)

        assert out["cuisine_id"] == "zhejiang"
        assert "shellfish" in out["matched_allergies"]
        assert "fish" in out["matched_allergies"]

    def test_parse_invalid_json_falls_back(self) -> None:
        expert = ZhejiangExpert()
        out = expert.parse_output("not json at all")

        assert out["cuisine_id"] == "zhejiang"
        assert out["conclusion"] == "暂不可推荐"
        assert out["keywords"] == []
        assert out["matched_allergies"] == []
