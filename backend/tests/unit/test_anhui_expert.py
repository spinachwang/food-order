"""F017 — 徽菜专家专属契约测试.

涵盖 [spec/features/F017-anhui.md §2 / §6] 验收点:

- cuisine_id / display_name / 继承 `BaseCuisineExpert`
- 关键词覆盖：徽菜 / 安徽 / 徽州 / 臭鳜鱼（至少出现于 prompt 片段）
- 与川菜 / 湘菜的辣度区分：徽偏"咸鲜 + 重油"，无辣或微辣——prompt 必须澄清
- §6 测试计划：
  - 用户输入"徽州" → 关键词含"徽菜"
  - 集成：与川菜并行时不冲突（通过注册表 / build_prompt 路径验证）

不重复 F003 `test_base_contract.py` 已覆盖的内容（继承关系 / parse_output
通用 fallback / 全 14 注册表完整性）—— 那些属于通用契约。本文件只断言
**徽菜专属** 的行为约束，确保 §4 prompt 要点被实际写进代码。
"""
from __future__ import annotations

from decimal import Decimal

from app.agents.cuisines import CUISINE_REGISTRY, BaseCuisineExpert
from app.agents.cuisines.stubs.anhui import CUISINE_PROMPT_FRAGMENT, AnhuiExpert
from app.agents.state import CuisineExpertInput, UserPreferencesDict
from app.core.constants import CUISINE_IDS

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_input(
    user_message: str, allergies: list[str] | None = None
) -> CuisineExpertInput:
    """构造一个最小可用的 `CuisineExpertInput`。

    F017 §6 验收点关注的是 user_message，preferences 用占位即可。
    """
    prefs: UserPreferencesDict = {
        "user_id": "u-f017",
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
# TestAnhuiBasicContract — F003 §3.1 必填属性 + F017 §2 cuisine_id
# ---------------------------------------------------------------------------


class TestAnhuiBasicContract:
    def test_anhui_expert_inherits_base(self) -> None:
        assert issubclass(AnhuiExpert, BaseCuisineExpert)

    def test_cuisine_id_is_anhui(self) -> None:
        # F017 §2 验收点：`cuisine_id="anhui"`
        assert AnhuiExpert.cuisine_id == "anhui"

    def test_display_name_is_huicai(self) -> None:
        # F017 §1 用户故事 + §2 验收要求"徽菜"作为显示名
        assert AnhuiExpert.display_name == "徽菜"

    def test_uses_unified_llm_model(self) -> None:
        # F003 §8.1 — 14 个菜系统一 `MiniMax-M3`
        assert AnhuiExpert.llm_model == "MiniMax-M3"

    def test_prompt_fragment_is_non_empty_string(self) -> None:
        # 必须存在菜系专属片段，否则不满足 F003 §3.1 的子类可选 override
        assert isinstance(AnhuiExpert.prompt_fragment, str)
        assert AnhuiExpert.prompt_fragment.strip()


# ---------------------------------------------------------------------------
# TestAnhuiInRegistry — F003 §3.2 注册表
# ---------------------------------------------------------------------------


class TestAnhuiInRegistry:
    def test_registered_in_cuisine_registry(self) -> None:
        assert "anhui" in CUISINE_REGISTRY
        assert CUISINE_REGISTRY["anhui"] is not None

    def test_registry_entry_has_matching_cuisine_id(self) -> None:
        expert = CUISINE_REGISTRY["anhui"]
        assert expert.cuisine_id == "anhui"
        assert expert.display_name == "徽菜"

    def test_registry_position_matches_cuisine_ids_spec_order(self) -> None:
        # F003 §3.2 / `CUISINE_IDS` 顺序：anhui 在第 8 位
        # （川 / 粤 / 鲁 / 苏 / 浙 / 闽 / 湘 / 徽）
        assert CUISINE_IDS.index("anhui") == 7
        assert tuple(CUISINE_REGISTRY.keys())[7] == "anhui"


# ---------------------------------------------------------------------------
# TestAnhuiPromptFragment — F017 §2 / §4 prompt 要点的实际落位
# ---------------------------------------------------------------------------


class TestAnhuiPromptFragment:
    """验证 F017 §2/§4 关键提示已落到 `CUISINE_PROMPT_FRAGMENT` 字面量中。

    这些是**给 LLM 的字面规则**——它们只有在 prompt 片段里真正出现，
    才能引导模型输出符合 §2 §6 验收点的关键词。这就是 §6 可单测的
    唯一现实接口（不接 LLM）。
    """

    def test_fragment_lists_all_four_cuisine_terms(self) -> None:
        # F017 §2 验收：关键词覆盖 徽菜 / 安徽 / 徽州 / 臭鳜鱼
        # §4 prompt 关键词生成：包含"徽菜 / 安徽 / 徽州"中的 1-2 个
        for token in ("徽菜", "安徽", "徽州"):
            assert token in CUISINE_PROMPT_FRAGMENT, (
                f"F017 §2 要求关键词覆盖 {token!r}；必须出现在 prompt 片段中以引导 LLM 输出"
            )

    def test_fragment_lists_signature_chouguiyu(self) -> None:
        # F017 §2 验收：关键词覆盖"臭鳜鱼"——§3 经典菜的代表
        # §4 prompt 关键词生成：1 个代表菜（"臭鳜鱼"）
        assert "臭鳜鱼" in CUISINE_PROMPT_FRAGMENT, (
            "F017 §2 + §4 要求关键词覆盖 '臭鳜鱼'；必须作为经典代表菜出现在 prompt 片段中"
        )

    def test_fragment_lists_representative_dishes(self) -> None:
        # F017 §3 经典：臭鳜鱼 / 毛豆腐 / 火腿炖甲鱼 / 徽州毛豆腐 / 问政山笋
        # 至少要有 3 道作为关键词候选
        classics = (
            "臭鳜鱼",
            "毛豆腐",
            "火腿炖甲鱼",
            "徽州毛豆腐",
            "问政山笋",
        )
        present = [d for d in classics if d in CUISINE_PROMPT_FRAGMENT]
        assert len(present) >= 3, (
            f"prompt 片段至少应列出 3 个 F017 §3 经典代表菜作为关键词候选；"
            f"实际命中={present}"
        )

    def test_fragment_lists_lambei_dishes(self) -> None:
        # F017 §3 腊味：徽州腊肉 / 刀板香
        # §4 prompt 关键词生成：1 个代表菜（腊味也是候选）
        lambei = ("徽州腊肉", "刀板香", "腊肉")
        present = [d for d in lambei if d in CUISINE_PROMPT_FRAGMENT]
        assert present, (
            f"prompt 片段必须列出至少 1 个 F017 §3 腊味代表菜；实际命中={present}"
        )

    def test_fragment_distinguishes_from_sichuan_and_hunan(self) -> None:
        # F017 §2 验收：与川菜 / 湘菜的辣度区分——徽偏"咸鲜 + 重油"，无辣或微辣
        # §4 prompt 要点必须显式说明这两条边界（否则 LLM 会把"重口味"一律推川湘）
        assert "川菜" in CUISINE_PROMPT_FRAGMENT, (
            "F017 §2 + §4 明确要求 prompt 片段含与川菜的辣度区分；"
            "缺少会让 LLM 把'重油'用户推到川"
        )
        assert "湘菜" in CUISINE_PROMPT_FRAGMENT, (
            "F017 §2 + §4 明确要求 prompt 片段含与湘菜的辣度区分；"
            "缺少会让 LLM 把'腊味'用户推到湘"
        )
        # §4 徽的"咸鲜"标签必须显式呈现
        assert "咸鲜" in CUISINE_PROMPT_FRAGMENT
        # §4 川的"麻辣"对照
        assert "麻辣" in CUISINE_PROMPT_FRAGMENT
        # §4 湘的"香辣"对照（湘偏香辣腊味 vs 徽偏山珍腊味）
        assert "香辣" in CUISINE_PROMPT_FRAGMENT

    def test_fragment_mentions_signature_flavors(self) -> None:
        # F017 §1 + §4：徽菜特点为重油、重色、擅用火腿与山珍，徽州山区特色
        # 关键词生成的风味词候选应当至少包含其一
        flavors = ("重油", "重色", "腊香", "山珍", "咸鲜")
        present = [f for f in flavors if f in CUISINE_PROMPT_FRAGMENT]
        assert present, (
            f"prompt 片段必须含至少一个 F017 §4 风味词；实际命中={present}"
        )

    def test_fragment_warns_allergens(self) -> None:
        # F017 §4 过敏原注意：徽菜常用火腿、腊肉；忌 pork 不常见但需注意
        # 至少命中 1 个过敏原提示词以引导 LLM 在 matched_allergies 中返回
        allergens = ("火腿", "腊肉", "腊", "pork", "酒")
        present = [a for a in allergens if a in CUISINE_PROMPT_FRAGMENT]
        assert present, (
            f"prompt 片段必须含至少 1 个 F017 §4 过敏原提示词；实际命中={present}"
        )

    def test_fragment_specifies_keyword_generation_rule(self) -> None:
        # F017 §4 关键词生成规则：包含"徽菜 / 安徽 / 徽州"中的 1-2 个 +
        # 1 个代表菜（"臭鳜鱼"）
        # 显式规则必须落在片段中（否则 LLM 不会按规则生成）
        assert "关键词" in CUISINE_PROMPT_FRAGMENT
        assert "代表菜" in CUISINE_PROMPT_FRAGMENT

    def test_fragment_mentions_huizhou_mountain_feature(self) -> None:
        # F017 §1 + §4：徽州山区特色——必须显式落到 prompt 以让 LLM 知道
        # 徽菜与浙菜的差异（徽偏"重油重色"，浙偏"清鲜"）
        assert "徽州" in CUISINE_PROMPT_FRAGMENT
        assert "山珍" in CUISINE_PROMPT_FRAGMENT or "山区" in CUISINE_PROMPT_FRAGMENT


# ---------------------------------------------------------------------------
# TestAnhuiBuildPrompt — F017 §6 行为验收：user_message → prompt 内容
# ---------------------------------------------------------------------------


class TestAnhuiBuildPrompt:
    """F017 §6 测试计划：用户输入"徽州" / "徽菜" / "臭鳜鱼" → 关键词覆盖。

    不接 LLM 验证 LLM 行为，而是验证 prompt 模板确实提供了产生该
    行为所需的全部上下文（用户输入 + 菜系词 + 风味词 + 与川湘区分）。
    """

    def test_huizhou_input_prompt_includes_huicai(self) -> None:
        """F017 §6 验收点：用户输入"徽州"时，build_prompt 输出必须
        既含用户的原文又含菜系词"徽菜"，从而 LLM 可按规则产出含"徽菜"
        的关键词集。
        """
        prompt = AnhuiExpert().build_prompt(_build_input("想吃徽州菜"))

        # 用户原始输入被注入（F003 §4 模板必含 {message}）
        assert "想吃徽州菜" in prompt
        # F017 §2 菜系词：徽菜 / 安徽 / 徽州 至少其一
        assert "徽菜" in prompt
        # §2 验收：与川菜 / 湘菜的辣度区分必须在 prompt 中
        assert "川菜" in prompt
        assert "湘菜" in prompt
        # §4 风味词候选：咸鲜（让徽菜与川湘明确区分）
        assert "咸鲜" in prompt

    def test_huicai_input_prompt_carries_huicai_term(self) -> None:
        """用户输入"徽菜"时，prompt 必须把"徽菜"作为菜系词候选。"""
        prompt = AnhuiExpert().build_prompt(_build_input("想吃徽菜"))

        assert "徽菜" in prompt
        # §3 经典代表菜至少出现一个（臭鳜鱼是 §4 关键词生成指定菜）
        assert "臭鳜鱼" in prompt

    def test_anhui_input_prompt_carries_anhui_term(self) -> None:
        """用户输入"安徽菜"时，prompt 必须把"安徽"作为菜系词候选之一。"""
        prompt = AnhuiExpert().build_prompt(_build_input("想吃安徽菜"))

        assert "安徽" in prompt
        assert "徽菜" in prompt
        # §3 经典代表菜至少出现一个
        assert any(
            dish in prompt
            for dish in ("臭鳜鱼", "毛豆腐", "火腿炖甲鱼", "问政山笋")
        )

    def test_chouguiyu_input_promotes_signature_dish(self) -> None:
        """用户输入"臭鳜鱼"时，prompt 必须把"臭鳜鱼"作为代表菜候选（§4 规则）。"""
        prompt = AnhuiExpert().build_prompt(_build_input("想吃臭鳜鱼"))

        assert "臭鳜鱼" in prompt
        # §4 关键词生成：包含"徽菜 / 安徽 / 徽州"中的 1-2 个
        assert any(token in prompt for token in ("徽菜", "安徽", "徽州"))

    def test_xianxian_input_promotes_huizhou(self) -> None:
        """用户输入"咸鲜"时，prompt 必须把"咸鲜"作为徽的差异化风味词，
        并显式标注与川"麻辣"、湘"香辣"的边界，让 LLM 优先推徽而非川湘。
        """
        prompt = AnhuiExpert().build_prompt(_build_input("想吃咸鲜口味"))

        assert "咸鲜" in prompt
        # §4 prompt 要点：徽咸鲜 vs 川麻辣 vs 湘香辣——必须显式说明
        assert "麻辣" in prompt
        assert "香辣" in prompt
        # §2 菜系词必须出现以让 LLM 知道用哪个 cuisine_id 输出
        assert any(token in prompt for token in ("徽菜", "安徽", "徽州"))


# ---------------------------------------------------------------------------
# TestAnhuiParallelSafety — F017 §6 集成：与川菜并行时不冲突
# ---------------------------------------------------------------------------


class TestAnhuiParallelSafety:
    """F017 §6 验收点：与川菜并行时不冲突。

    验证多菜系注册表 + build_prompt 的隔离性——徽菜 Node 不会因其它
    菜系的 prompt 片段被调用而改变自身行为。
    """

    def test_anhui_and_sichuan_coexist_in_registry(self) -> None:
        # 两个菜系 Node 都注册到统一 registry，顺序由 CUISINE_IDS 决定
        assert "anhui" in CUISINE_REGISTRY
        assert "sichuan" in CUISINE_REGISTRY
        # 各自的 prompt_fragment 互不污染
        from app.agents.cuisines.stubs.sichuan import SichuanExpert

        assert AnhuiExpert.prompt_fragment != SichuanExpert.prompt_fragment
        assert "徽菜" in AnhuiExpert.prompt_fragment
        assert "川菜" in SichuanExpert.prompt_fragment

    def test_anhui_prompt_does_not_leak_sichuan_terms(self) -> None:
        """徽菜 build_prompt 中只应在边界澄清句里出现"川菜"，不应让
        LLM 误以为推荐对象是川菜——通过输出不出现川菜专属代表菜验证。
        """
        prompt = AnhuiExpert().build_prompt(_build_input("想吃徽菜"))

        # 边界澄清需要"川菜"作为对照词，但川菜专属代表菜不应出现在徽菜 prompt 中
        from app.agents.cuisines.stubs.sichuan import (
            CUISINE_PROMPT_FRAGMENT as SICHUAN_FRAGMENT,
        )

        sichuan_signature_dishes = ("麻婆豆腐", "回锅肉", "水煮鱼")
        for dish in sichuan_signature_dishes:
            assert dish not in prompt, (
                f"徽菜 prompt 不应包含川菜代表菜 {dish!r}；"
                f"否则 LLM 会把徽菜用户推到川"
            )
        # 川菜 fragment 里没有这些专属菜时此断言平凡成立，留作防回归
        assert any(d in SICHUAN_FRAGMENT for d in sichuan_signature_dishes)


# ---------------------------------------------------------------------------
# TestAnhuiParseOutput — F003 §3.3 徽菜 Node 自己的解析行为
# ---------------------------------------------------------------------------


class TestAnhuiParseOutput:
    """徽菜继承的 `BaseCuisineExpert.parse_output` 对徽菜专用字段。

    验证时使用徽菜领域的 representative JSON（臭鳜鱼 / 徽菜 / 咸鲜 关键词集合）。
    """

    def test_parse_happy_path_anhui_dishes(self) -> None:
        expert = AnhuiExpert()
        conclusion = "今天适合来份臭鳜鱼"
        raw = (
            f'{{"conclusion":"{conclusion}",'
            '"keywords":["徽菜","臭鳜鱼","徽州","腊肉","咸鲜"],'
            '"matched_allergies":[]}'
        )
        out = expert.parse_output(raw)

        assert out["cuisine_id"] == "anhui"
        # conclusion 是 LLM 自由文本，只要透传即可
        assert out["conclusion"] == conclusion
        # F017 §2 关键词覆盖：徽菜 + 臭鳜鱼 都在
        assert "徽菜" in out["keywords"]
        assert "臭鳜鱼" in out["keywords"]
        # §4 关键词生成：徽州
        assert "徽州" in out["keywords"]
        # §3 腊味代表菜
        assert "腊肉" in out["keywords"]
        # §4 风味词：咸鲜
        assert "咸鲜" in out["keywords"]
        assert all(isinstance(k, str) for k in out["keywords"])

    def test_parse_happy_path_with_lambei_subgroup(self) -> None:
        """F017 §3 腊味：徽州腊肉 / 刀板香——若 LLM 输出全套腊味，
        parse_output 必须透传不丢字段（让 summary agent 能聚合）。"""
        expert = AnhuiExpert()
        raw = (
            '{"conclusion":"今天推荐徽菜",'
            '"keywords":["徽菜","徽州腊肉","刀板香","徽州"],'
            '"matched_allergies":[]}'
        )
        out = expert.parse_output(raw)

        assert out["cuisine_id"] == "anhui"
        # F017 §2 关键词覆盖几项全在
        assert "徽菜" in out["keywords"]
        assert "徽州" in out["keywords"]
        # §3 腊味两类全在
        assert "徽州腊肉" in out["keywords"]
        assert "刀板香" in out["keywords"]

    def test_parse_happy_path_with_allergens(self) -> None:
        """F017 §4 过敏原：火腿 / 腊肉——若 LLM 命中应透传到 matched_allergies。"""
        expert = AnhuiExpert()
        raw = (
            '{"conclusion":"今天推荐徽菜",'
            '"keywords":["徽菜","臭鳜鱼"],'
            '"matched_allergies":["pork"]}'
        )
        out = expert.parse_output(raw)

        assert out["cuisine_id"] == "anhui"
        assert "pork" in out["matched_allergies"]

    def test_parse_invalid_json_falls_back(self) -> None:
        expert = AnhuiExpert()
        out = expert.parse_output("not json at all")

        assert out["cuisine_id"] == "anhui"
        assert out["conclusion"] == "暂不可推荐"
        assert out["keywords"] == []
        assert out["matched_allergies"] == []
