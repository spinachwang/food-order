"""F016 — 湘菜专家专属契约测试.

涵盖 [spec/features/F016-hunan.md §2 / §6] 验收点:

- cuisine_id / display_name / 继承 `BaseCuisineExpert`
- 关键词覆盖：湘菜 / 湖南 / 剁椒 / 腊味（至少出现于 prompt 片段）
- 与川菜区别：湘偏"香辣"，川偏"麻辣"——prompt 必须澄清
- §6 测试计划：
  - 用户输入"想吃辣的" → 同时被本 Node 与 F010 命中
    （验证 prompt 片段中"辣"字与"香辣"显式提示俱在，不排斥川）
  - 用户输入"香辣" → 优先本 Node（验证 prompt 片段显式标注
    "香辣"为湘的差异化风味词）

不重复 F003 `test_base_contract.py` 已覆盖的内容（继承关系 / parse_output
通用 fallback / 全 14 注册表完整性）—— 那些属于通用契约。本文件只断言
**湘菜专属** 的行为约束，确保 §4 prompt 要点被实际写进代码。
"""
from __future__ import annotations

from decimal import Decimal

from app.agents.cuisines import CUISINE_REGISTRY, BaseCuisineExpert
from app.agents.cuisines.stubs.hunan import CUISINE_PROMPT_FRAGMENT, HunanExpert
from app.agents.state import CuisineExpertInput, UserPreferencesDict
from app.core.constants import CUISINE_IDS

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_input(user_message: str, allergies: list[str] | None = None) -> CuisineExpertInput:
    """构造一个最小可用的 `CuisineExpertInput`。

    F016 §6 验收点关注的是 user_message，preferences 用占位即可。
    """
    prefs: UserPreferencesDict = {
        "user_id": "u-f016",
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
# TestHunanBasicContract — F003 §3.1 必填属性 + F016 §2 cuisine_id
# ---------------------------------------------------------------------------


class TestHunanBasicContract:
    def test_hunan_expert_inherits_base(self) -> None:
        assert issubclass(HunanExpert, BaseCuisineExpert)

    def test_cuisine_id_is_hunan(self) -> None:
        # F016 §2 验收点：`cuisine_id="hunan"`
        assert HunanExpert.cuisine_id == "hunan"

    def test_display_name_is_xiangcai(self) -> None:
        # F016 §1 用户故事 + §2 验收要求"湘菜"作为显示名
        assert HunanExpert.display_name == "湘菜"

    def test_uses_unified_llm_model(self) -> None:
        # F003 §8.1 — 14 个菜系统一 `MiniMax-M3`
        assert HunanExpert.llm_model == "MiniMax-M3"

    def test_prompt_fragment_is_non_empty_string(self) -> None:
        # 必须存在菜系专属片段，否则不满足 F003 §3.1 的子类可选 override
        assert isinstance(HunanExpert.prompt_fragment, str)
        assert HunanExpert.prompt_fragment.strip()


# ---------------------------------------------------------------------------
# TestHunanInRegistry — F003 §3.2 注册表
# ---------------------------------------------------------------------------


class TestHunanInRegistry:
    def test_registered_in_cuisine_registry(self) -> None:
        assert "hunan" in CUISINE_REGISTRY
        assert CUISINE_REGISTRY["hunan"] is not None

    def test_registry_entry_has_matching_cuisine_id(self) -> None:
        expert = CUISINE_REGISTRY["hunan"]
        assert expert.cuisine_id == "hunan"
        assert expert.display_name == "湘菜"

    def test_registry_position_matches_cuisine_ids_spec_order(self) -> None:
        # F003 §3.2 / `CUISINE_IDS` 顺序：hunan 在第 7 位
        # （川 / 粤 / 鲁 / 苏 / 浙 / 闽 / 湘）
        assert CUISINE_IDS.index("hunan") == 6
        assert tuple(CUISINE_REGISTRY.keys())[6] == "hunan"


# ---------------------------------------------------------------------------
# TestHunanPromptFragment — F016 §2 / §4 prompt 要点的实际落位
# ---------------------------------------------------------------------------


class TestHunanPromptFragment:
    """验证 F016 §2/§4 关键提示已落到 `CUISINE_PROMPT_FRAGMENT` 字面量中。

    这些是**给 LLM 的字面规则**——它们只有在 prompt 片段里真正出现，
    才能引导模型输出符合 §2 §6 验收点的关键词。这就是 §6 可单测的
    唯一现实接口（不接 LLM）。
    """

    def test_fragment_lists_all_four_cuisine_terms(self) -> None:
        # F016 §2 验收：关键词覆盖 湘菜 / 湖南 / 剁椒 / 腊味
        # §4 prompt 关键词生成：包含"湘菜 / 湖南"中的 1 个
        for token in ("湘菜", "湖南", "剁椒", "腊味"):
            assert token in CUISINE_PROMPT_FRAGMENT, (
                f"F016 §2 要求关键词覆盖 {token!r}；必须出现在 prompt 片段中以引导 LLM 输出"
            )

    def test_fragment_lists_signature_duojiaoyutou(self) -> None:
        # F016 §2 验收 + §4 prompt 关键词生成："剁椒鱼头"作为代表菜
        assert "剁椒鱼头" in CUISINE_PROMPT_FRAGMENT, (
            "F016 §4 要求关键词生成含'剁椒鱼头'作为代表菜；"
            "缺失会让 LLM 无法稳定输出剁椒关键词"
        )

    def test_fragment_lists_representative_dishes(self) -> None:
        # F016 §3 经典：剁椒鱼头 / 毛氏红烧肉 / 湘西外婆菜 / 农家小炒肉
        # 至少要有 3 道作为关键词候选
        classics = (
            "剁椒鱼头",
            "毛氏红烧肉",
            "湘西外婆菜",
            "农家小炒肉",
        )
        present = [d for d in classics if d in CUISINE_PROMPT_FRAGMENT]
        assert len(present) >= 3, (
            f"prompt 片段至少应列出 3 个 F016 §3 经典代表菜作为关键词候选；"
            f"实际命中={present}"
        )

    def test_fragment_lists_lambei_dishes(self) -> None:
        # F016 §3 腊味：腊肉 / 腊鱼 / 腊鸡
        # §2 验收要求覆盖"腊味"——若 prompt 不给具体腊味代表菜，
        # LLM 只能泛泛输出"腊味"
        lambei = ("腊肉", "腊鱼", "腊鸡")
        present = [d for d in lambei if d in CUISINE_PROMPT_FRAGMENT]
        assert present, (
            f"prompt 片段必须列出至少 1 个 F016 §3 腊味代表菜以支持 §2 '腊味' "
            f"关键词；实际命中={present}"
        )

    def test_fragment_distinguishes_from_sichuan(self) -> None:
        # F016 §2 验收 + §4 prompt 要点：与川菜区别——湘偏"香辣"，川偏"麻辣"
        # §4 明确要求 prompt 必须显式说明这一区分
        assert "川菜" in CUISINE_PROMPT_FRAGMENT, (
            "F016 §2 + §4 明确要求 prompt 片段含与川菜的辣度区分；"
            "缺少会让 LLM 不知把'辣'字用户推到川还是湘"
        )
        # §4 湘的"香辣"标签必须显式呈现
        assert "香辣" in CUISINE_PROMPT_FRAGMENT
        # §4 川的"麻辣"对照也应在 prompt 中以使边界清晰
        assert "麻辣" in CUISINE_PROMPT_FRAGMENT

    def test_fragment_mentions_signature_flavors(self) -> None:
        # F016 §1 + §4：湘菜特点为香辣为主、擅用腊味 / 剁椒、乡土气息浓
        # 关键词生成的风味词候选应当至少包含其一
        flavors = ("香辣", "腊味", "酸辣", "浓郁")
        present = [f for f in flavors if f in CUISINE_PROMPT_FRAGMENT]
        assert present, (
            f"prompt 片段必须含至少一个 F016 §4 风味词；实际命中={present}"
        )

    def test_fragment_warns_allergens(self) -> None:
        # F016 §4 过敏原注意：腊味常用烟熏；少数含花生
        # 至少命中 1 个过敏原提示词以引导 LLM 在 matched_allergies 中返回
        allergens = ("腊", "烟熏", "花生", "peanut", "soy", "辣椒")
        present = [a for a in allergens if a in CUISINE_PROMPT_FRAGMENT]
        assert present, (
            f"prompt 片段必须含至少 1 个 F016 §4 过敏原提示词；实际命中={present}"
        )

    def test_fragment_specifies_keyword_generation_rule(self) -> None:
        # F016 §4 关键词生成规则：包含"湘菜 / 湖南"中的 1 个 +
        # 1 个代表菜（"剁椒鱼头"、"腊味"）+ 1 个风味词（"香辣"）
        # 显式规则必须落在片段中（否则 LLM 不会按规则生成）
        assert "关键词" in CUISINE_PROMPT_FRAGMENT
        assert "风味" in CUISINE_PROMPT_FRAGMENT


# ---------------------------------------------------------------------------
# TestHunanBuildPrompt — F016 §6 行为验收：user_message → prompt 内容
# ---------------------------------------------------------------------------


class TestHunanBuildPrompt:
    """F016 §6 测试计划：用户输入"想吃辣的" / "香辣" → 关键词覆盖。

    不接 LLM 验证 LLM 行为，而是验证 prompt 模板确实提供了产生该
    行为所需的全部上下文（用户输入 + 菜系词 + 风味词 + 与川菜区分）。
    """

    def test_spicy_input_prompt_includes_both_cuisines(self) -> None:
        """F016 §6 验收点 1：用户输入"想吃辣的"时，build_prompt 输出必须
        既含用户的原文又含菜系词"湘菜"，同时含与川菜的辣度区分澄清，
        从而 LLM 不会被锁死在单一菜系上——湘与川都有资格被推。
        """
        prompt = HunanExpert().build_prompt(_build_input("想吃辣的"))

        # 用户原始输入被注入（F003 §4 模板必含 {message}）
        assert "想吃辣的" in prompt
        # F016 §2 菜系词：湘菜 / 湖南 至少其一
        assert any(token in prompt for token in ("湘菜", "湖南"))
        # §2 验收：与川菜的辣度区分必须在 prompt 中
        assert "川菜" in prompt
        # §4 风味词候选：香辣（让 F016 与 F010 都能命中"辣"字场景）
        assert "香辣" in prompt

    def test_xiangla_input_prompt_promotes_xiang(self) -> None:
        """F016 §6 验收点 2：用户输入"香辣"时，prompt 必须把"香辣"作为
        湘的差异化风味词显式标注，使 LLM 优先推湘而非川（§4 规则）。
        """
        prompt = HunanExpert().build_prompt(_build_input("想吃香辣"))

        assert "香辣" in prompt
        # §4 prompt 要点：说"香辣"则优先湘——必须显式说明湘香辣 vs 川麻辣
        assert "麻辣" in prompt
        # §2 菜系词必须出现以让 LLM 知道用哪个 cuisine_id 输出
        assert any(token in prompt for token in ("湘菜", "湖南"))

    def test_xiangcai_input_prompt_carries_xiangcai_term(self) -> None:
        """用户输入"湘菜"时，prompt 必须把"湘菜"作为菜系词候选。"""
        prompt = HunanExpert().build_prompt(_build_input("想吃湘菜"))

        assert "湘菜" in prompt
        # §3 经典代表菜至少出现一个（剁椒鱼头是 §4 关键词生成指定菜）
        assert "剁椒鱼头" in prompt

    def test_hunan_input_prompt_carries_hunan_term(self) -> None:
        """用户输入"湖南菜"时，prompt 必须把"湖南"作为菜系词候选。"""
        prompt = HunanExpert().build_prompt(_build_input("想吃湖南菜"))

        assert "湖南" in prompt
        # §3 经典代表菜至少出现一个
        assert any(
            dish in prompt
            for dish in ("剁椒鱼头", "毛氏红烧肉", "湘西外婆菜", "农家小炒肉")
        )

    def test_duojiao_input_prompt_promotes_duojiaoyutou(self) -> None:
        """用户输入"剁椒"时，prompt 必须把"剁椒鱼头"作为代表菜候选（§4 规则）。"""
        prompt = HunanExpert().build_prompt(_build_input("想吃剁椒"))

        assert "剁椒" in prompt
        assert "剁椒鱼头" in prompt

    def test_lambei_input_prompt_carries_lambei_dishes(self) -> None:
        """用户输入"腊味"时，prompt 必须含腊味代表菜（§3 腊味类）。"""
        prompt = HunanExpert().build_prompt(_build_input("想吃腊味"))

        assert "腊味" in prompt
        # §3 腊味代表菜至少出现一个（腊肉 / 腊鱼 / 腊鸡）
        assert any(dish in prompt for dish in ("腊肉", "腊鱼", "腊鸡"))


# ---------------------------------------------------------------------------
# TestHunanParseOutput — F003 §3.3 湘菜 Node 自己的解析行为
# ---------------------------------------------------------------------------


class TestHunanParseOutput:
    """湘菜继承的 `BaseCuisineExpert.parse_output` 对湘菜专用字段。

    验证时使用湘菜领域的 representative JSON（剁椒鱼头 / 腊味 / 香辣 关键词集合）。
    """

    def test_parse_happy_path_hunan_dishes(self) -> None:
        expert = HunanExpert()
        conclusion = "今天适合来份剁椒鱼头"
        raw = (
            f'{{"conclusion":"{conclusion}",'
            '"keywords":["湘菜","剁椒鱼头","腊肉","香辣","毛氏红烧肉"],'
            '"matched_allergies":[]}'
        )
        out = expert.parse_output(raw)

        assert out["cuisine_id"] == "hunan"
        # conclusion 是 LLM 自由文本，只要透传即可
        assert out["conclusion"] == conclusion
        # F016 §2 关键词覆盖：湘菜 在
        assert "湘菜" in out["keywords"]
        # §4 关键词生成指定代表菜：剁椒鱼头 / 腊味
        assert "剁椒鱼头" in out["keywords"]
        assert "腊肉" in out["keywords"]
        # §4 风味词：香辣
        assert "香辣" in out["keywords"]
        # §3 经典代表菜
        assert "毛氏红烧肉" in out["keywords"]
        assert all(isinstance(k, str) for k in out["keywords"])

    def test_parse_happy_path_with_lambei_subgroup(self) -> None:
        """F016 §3 腊味：腊肉 / 腊鱼 / 腊鸡——若 LLM 输出全套腊味，
        parse_output 必须透传不丢字段（让 summary agent 能聚合）。"""
        expert = HunanExpert()
        raw = (
            '{"conclusion":"今天推荐湘菜",'
            '"keywords":["湘菜","湖南","腊肉","腊鱼","腊鸡"],'
            '"matched_allergies":[]}'
        )
        out = expert.parse_output(raw)

        assert out["cuisine_id"] == "hunan"
        # F016 §2 关键词覆盖几项全在
        assert "湘菜" in out["keywords"]
        assert "湖南" in out["keywords"]
        # §3 腊味三类全在
        assert "腊肉" in out["keywords"]
        assert "腊鱼" in out["keywords"]
        assert "腊鸡" in out["keywords"]

    def test_parse_happy_path_with_allergens(self) -> None:
        """F016 §4 过敏原：腊味烟熏 / 花生——若 LLM 命中应透传到 matched_allergies。"""
        expert = HunanExpert()
        raw = (
            '{"conclusion":"今天推荐湘菜",'
            '"keywords":["湘菜","剁椒鱼头"],'
            '"matched_allergies":["peanut","soy"]}'
        )
        out = expert.parse_output(raw)

        assert out["cuisine_id"] == "hunan"
        assert "peanut" in out["matched_allergies"]
        assert "soy" in out["matched_allergies"]

    def test_parse_invalid_json_falls_back(self) -> None:
        expert = HunanExpert()
        out = expert.parse_output("not json at all")

        assert out["cuisine_id"] == "hunan"
        assert out["conclusion"] == "暂不可推荐"
        assert out["keywords"] == []
        assert out["matched_allergies"] == []
