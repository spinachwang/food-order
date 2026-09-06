"""F023 — 小吃专家专属契约测试.

涵盖 [spec/features/F023-snacks.md §2 / §6] 验收点:

- cuisine_id / display_name / 继承 `BaseCuisineExpert`
- 关键词覆盖:小吃 / 街头 / 煎饼 / 烤串 / 麻辣烫(§2 验收点)
- 与中式快餐(F022)的边界:本 Node 推荐非正餐类小吃摊 / 街边店
- §6 测试计划:
  - 用户输入"想吃小吃" → 关键词含"小吃"或"麻辣烫"

不重复 F003 `test_base_contract.py` 已覆盖的内容(继承关系 / parse_output
通用 fallback / 全 14 注册表完整性)—— 那些属于通用契约。本文件只断言
**小吃专属** 的行为约束,确保 §4 prompt 要点被实际写进代码。
"""

from __future__ import annotations

from decimal import Decimal

from app.agents.cuisines import CUISINE_REGISTRY, BaseCuisineExpert
from app.agents.cuisines.stubs.snacks import CUISINE_PROMPT_FRAGMENT, SnacksExpert
from app.agents.state import CuisineExpertInput, UserPreferencesDict
from app.core.constants import CUISINE_IDS

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_input(
    user_message: str, allergies: list[str] | None = None
) -> CuisineExpertInput:
    """构造一个最小可用的 `CuisineExpertInput`."""
    prefs: UserPreferencesDict = {
        "user_id": "u-f023",
        "cuisine_weights": dict.fromkeys(CUISINE_IDS, 0.5),
        "allergies": allergies if allergies is not None else [],
        "spice_tolerance": 0,
        "temperature_preference": "room",
        "default_location": "国贸",
        "budget_lunch_min": Decimal("10.00"),
        "budget_lunch_max": Decimal("30.00"),
    }
    return {
        "user_message": user_message,
        "user_preferences": prefs,
        "location": None,
        "spice_tolerance": 0,
        "budget_max": 30.0,
        "budget_min": 10.0,
    }


# ---------------------------------------------------------------------------
# TestSnacksBasicContract — F003 §3.1 必填属性 + F023 §2 cuisine_id
# ---------------------------------------------------------------------------


class TestSnacksBasicContract:
    def test_snacks_expert_inherits_base(self) -> None:
        assert issubclass(SnacksExpert, BaseCuisineExpert)

    def test_cuisine_id_is_snacks(self) -> None:
        # F023 §2 验收点:`cuisine_id="snacks"`
        assert SnacksExpert.cuisine_id == "snacks"

    def test_display_name_is_xiaochi(self) -> None:
        # F023 §1 用户故事 + §2 验收要求"小吃"作为显示名
        assert SnacksExpert.display_name == "小吃"

    def test_uses_unified_llm_model(self) -> None:
        # F003 §8.1 — 14 个菜系统一 `MiniMax-M3`
        assert SnacksExpert.llm_model == "MiniMax-M3"

    def test_prompt_fragment_is_non_empty_string(self) -> None:
        assert isinstance(SnacksExpert.prompt_fragment, str)
        assert SnacksExpert.prompt_fragment.strip()


# ---------------------------------------------------------------------------
# TestSnacksInRegistry — F003 §3.2 注册表
# ---------------------------------------------------------------------------


class TestSnacksInRegistry:
    def test_registered_in_cuisine_registry(self) -> None:
        assert "snacks" in CUISINE_REGISTRY
        assert CUISINE_REGISTRY["snacks"] is not None

    def test_registry_entry_has_matching_cuisine_id(self) -> None:
        expert = CUISINE_REGISTRY["snacks"]
        assert expert.cuisine_id == "snacks"
        assert expert.display_name == "小吃"

    def test_registry_position_matches_cuisine_ids_spec_order(self) -> None:
        # F003 §3.2 / `CUISINE_IDS` 顺序:snacks 在第 13 位
        # (川 / 粤 / 鲁 / 苏 / 浙 / 闽 / 湘 / 徽 / 日料 / 西餐 / 西式快餐 /
        #  中式快餐 / 小吃 / 甜品饮品)
        assert CUISINE_IDS.index("snacks") == 12
        assert tuple(CUISINE_REGISTRY.keys())[12] == "snacks"


# ---------------------------------------------------------------------------
# TestSnacksPromptFragment — F023 §2 / §4 prompt 要点的实际落位
# ---------------------------------------------------------------------------


class TestSnacksPromptFragment:
    """验证 F023 §2/§4 关键提示已落到 `CUISINE_PROMPT_FRAGMENT` 字面量中."""

    def test_fragment_lists_all_five_keyword_tokens(self) -> None:
        # F023 §2 验收:关键词覆盖 小吃 / 街头 / 煎饼 / 烤串 / 麻辣烫
        for token in ("小吃", "街头", "煎饼", "烤串", "麻辣烫"):
            assert token in CUISINE_PROMPT_FRAGMENT, (
                f"F023 §2 要求关键词覆盖 {token!r}; 必须出现在 prompt 片段中以引导 LLM 输出"
            )

    def test_fragment_lists_northern_dishes(self) -> None:
        # F023 §3 北方:煎饼 / 烤冷面 / 肉夹馍 / 凉皮
        northern = ("煎饼", "烤冷面", "肉夹馍", "凉皮")
        present = [d for d in northern if d in CUISINE_PROMPT_FRAGMENT]
        assert "煎饼" in present, "F023 §3 必须包含'煎饼'作为北方小吃代表"
        assert len(present) >= 3, (
            f"F023 §3 北方小吃至少列 3 个;实际命中={present}"
        )

    def test_fragment_lists_sichuan_chongqing_dishes(self) -> None:
        # F023 §3 川渝:麻辣烫 / 钵钵鸡 / 串串 / 烤脑花
        sichuan = ("麻辣烫", "钵钵鸡", "串串", "烤脑花")
        present = [d for d in sichuan if d in CUISINE_PROMPT_FRAGMENT]
        assert "麻辣烫" in present, "F023 §3 必须包含'麻辣烫'作为川渝小吃代表"
        assert len(present) >= 2, (
            f"F023 §3 川渝小吃至少列 2 个;实际命中={present}"
        )

    def test_fragment_lists_kanto_dishes(self) -> None:
        # F023 §3 关东:关东煮
        assert "关东煮" in CUISINE_PROMPT_FRAGMENT, (
            "F023 §3 必须包含'关东煮'作为关东小吃代表"
        )

    def test_fragment_lists_grill_dishes(self) -> None:
        # F023 §3 烧烤:烤串 / 烤翅 / 烤面筋
        grill = ("烤串", "烤翅", "烤面筋")
        present = [d for d in grill if d in CUISINE_PROMPT_FRAGMENT]
        assert "烤串" in present, "F023 §3 必须包含'烤串'作为烧烤代表"
        assert len(present) >= 2, (
            f"F023 §3 烧烤类至少列 2 个;实际命中={present}"
        )

    def test_fragment_specifies_price_range(self) -> None:
        # F023 §4 关键提示:人均 10-30 元
        assert "人均" in CUISINE_PROMPT_FRAGMENT
        assert "10" in CUISINE_PROMPT_FRAGMENT
        assert "30" in CUISINE_PROMPT_FRAGMENT
        assert any(
            token in CUISINE_PROMPT_FRAGMENT
            for token in ("10-30", "10 - 30", "10 到 30")
        ), "F023 §4 必须显式表达'人均 10-30 元'的价格区间"

    def test_fragment_distinguishes_from_chinese_fastfood(self) -> None:
        # F023 §2 验收 + §4 prompt 要点:与中式快餐(F022)的边界
        # ——本 Node 推荐非正餐类小吃摊 / 街边店; 中式快餐有座位 / 标准菜单
        assert "中式快餐" in CUISINE_PROMPT_FRAGMENT, (
            "F023 §2 + §4 边界必须显式提及'中式快餐'以防 LLM 把小吃摊误推 F022"
        )

    def test_fragment_specifies_street_food_nature(self) -> None:
        # F023 §4 关键提示:小吃特点——街头 / 摊位 / 非正餐
        assert "街头" in CUISINE_PROMPT_FRAGMENT
        # 必须显式表达"非正餐"或类似边界澄清
        assert any(
            token in CUISINE_PROMPT_FRAGMENT for token in ("非正餐", "摊位", "档口")
        ), "F023 §4 必须显式表达小吃'街头 / 摊位 / 非正餐'的特点"

    def test_fragment_specifies_keyword_generation_rule(self) -> None:
        # F023 §4 关键词生成规则:包含"小吃 / 街头"中的 1 个
        # + 1 个代表菜("煎饼"、"麻辣烫")
        assert "关键词" in CUISINE_PROMPT_FRAGMENT
        assert "小吃" in CUISINE_PROMPT_FRAGMENT
        assert "街头" in CUISINE_PROMPT_FRAGMENT
        assert "代表菜" in CUISINE_PROMPT_FRAGMENT
        # 至少 1 个代表菜("煎饼" / "麻辣烫")
        assert any(dish in CUISINE_PROMPT_FRAGMENT for dish in ("煎饼", "麻辣烫"))


# ---------------------------------------------------------------------------
# TestSnacksBuildPrompt — F023 §6 行为验收:user_message → prompt 内容
# ---------------------------------------------------------------------------


class TestSnacksBuildPrompt:
    """F023 §6 测试计划:用户输入"想吃小吃" / "想吃煎饼" / "想吃麻辣烫" → 关键词覆盖."""

    def test_snacks_input_prompt_includes_keyword_tokens(self) -> None:
        """F023 §6 验收点:用户输入"想吃小吃"时, build_prompt 必须含菜系词
        "小吃" 和代表菜候选."""
        prompt = SnacksExpert().build_prompt(_build_input("想吃小吃"))

        # 用户原始输入被注入
        assert "想吃小吃" in prompt
        # §2 菜系词:小吃
        assert "小吃" in prompt
        # §3 至少一个代表菜(煎饼 / 麻辣烫)
        assert any(dish in prompt for dish in ("煎饼", "麻辣烫"))

    def test_jianbing_input_prompt_carries_northern_dish(self) -> None:
        """用户输入"想吃煎饼"时, prompt 必须把"煎饼"作为代表菜候选."""
        prompt = SnacksExpert().build_prompt(_build_input("想吃煎饼"))

        assert "煎饼" in prompt
        # §3 北方小吃至少其一
        assert any(dish in prompt for dish in ("烤冷面", "肉夹馍", "凉皮"))

    def test_malatang_input_prompt_carries_sichuan_dish(self) -> None:
        """用户输入"想吃麻辣烫"时, prompt 必须把"麻辣烫"作为代表菜候选."""
        prompt = SnacksExpert().build_prompt(_build_input("想吃麻辣烫"))

        assert "麻辣烫" in prompt
        # §3 川渝小吃至少其一
        assert any(dish in prompt for dish in ("钵钵鸡", "串串", "烤脑花"))

    def test_kaochuan_input_prompt_carries_grill_dish(self) -> None:
        """用户输入"想吃烤串"时, prompt 必须把"烤串"作为烧烤代表."""
        prompt = SnacksExpert().build_prompt(_build_input("想吃烤串"))

        assert "烤串" in prompt
        assert "烧烤" in prompt or "烤" in prompt

    def test_street_food_input_promotes_boundary_warning(self) -> None:
        """用户输入"想吃街头小吃"时, prompt 必须显式表达"街头 / 摊位 / 非正餐"
        的特点, 引导 LLM 不要推到正餐菜系."""
        prompt = SnacksExpert().build_prompt(_build_input("想吃街头小吃"))

        assert "街头" in prompt
        # §4 边界澄清:与中式快餐(F022)的边界
        assert "中式快餐" in prompt

    def test_chinese_fastfood_input_pushes_to_snacks(self) -> None:
        """用户输入"黄焖鸡米饭"时, prompt 必须显式把中式快餐场景归 F022
        ——避免 LLM 把黄焖鸡米饭误推到本 Node.

        校验点:1) 用户输入原样回显; 2) prompt fragment 中式快餐(F022)
        边界澄清句落到 prompt; 3) 本 Node 的代表菜列表不含中式快餐代表.
        """
        prompt = SnacksExpert().build_prompt(_build_input("想吃黄焖鸡米饭"))

        # 用户输入原样回显(F003 §4 模板必含 {message})
        assert "想吃黄焖鸡米饭" in prompt
        # §4 边界澄清:中式快餐(F022)归快餐 Node, 本 Node 主推非正餐小吃摊
        assert "中式快餐" in prompt
        # 本 Node 的代表菜品列表(cuisine_extras 段)不含中式快餐代表菜
        # ——确保 LLM 不会把用户输入误推到本 Node 的推荐集合.
        assert "黄焖鸡米饭" not in CUISINE_PROMPT_FRAGMENT
        assert "沙县拌面" not in CUISINE_PROMPT_FRAGMENT


# ---------------------------------------------------------------------------
# TestSnacksParallelSafety — F023 §6 集成:与中式快餐(F022)并行不冲突
# ---------------------------------------------------------------------------


class TestSnacksParallelSafety:
    """F023 §6 集成:与中式快餐并行不冲突.

    验证多菜系注册表 + build_prompt 的隔离性——小吃 Node 不会因其它
    菜系的 prompt 片段被调用而改变自身行为。
    """

    def test_snacks_and_chinese_fastfood_coexist_in_registry(self) -> None:
        # 两个菜系 Node 都注册到统一 registry, 顺序由 CUISINE_IDS 决定
        assert "snacks" in CUISINE_REGISTRY
        assert "chinese_fastfood" in CUISINE_REGISTRY
        # 各自的 prompt_fragment 互不污染
        from app.agents.cuisines.stubs.chinese_fastfood import ChineseFastfoodExpert

        assert SnacksExpert.prompt_fragment != ChineseFastfoodExpert.prompt_fragment
        assert "小吃" in SnacksExpert.prompt_fragment
        assert "中式快餐" in ChineseFastfoodExpert.prompt_fragment

    def test_snacks_prompt_does_not_leak_chinese_fastfood_signature(self) -> None:
        """小吃 build_prompt 中只应在边界澄清句里出现"中式快餐", 不应让
        LLM 误以为推荐对象是中式快餐——通过输出不出现中式快餐专属
        代表菜验证."""
        prompt = SnacksExpert().build_prompt(_build_input("想吃小吃"))

        # 中式快餐专属代表菜不应出现在小吃 prompt 中
        chinese_fastfood_signature = ("黄焖鸡米饭", "沙县拌面", "兰州拉面", "猪脚饭")
        for dish in chinese_fastfood_signature:
            assert dish not in prompt, (
                f"小吃 prompt 不应包含中式快餐代表菜 {dish!r}; "
                "否则 LLM 会把小吃用户推到中式快餐"
            )


# ---------------------------------------------------------------------------
# TestSnacksParseOutput — F003 §3.3 小吃 Node 自己的解析行为
# ---------------------------------------------------------------------------


class TestSnacksParseOutput:
    """小吃继承的 `BaseCuisineExpert.parse_output` 对小吃专用字段."""

    def test_parse_happy_path_snacks_dishes(self) -> None:
        expert = SnacksExpert()
        conclusion = "今天适合来份煎饼"
        raw = (
            f'{{"conclusion":"{conclusion}",'
            '"keywords":["小吃","煎饼","麻辣烫","街头"],'
            '"matched_allergies":[]}'
        )
        out = expert.parse_output(raw)

        assert out["cuisine_id"] == "snacks"
        assert out["conclusion"] == conclusion
        # F023 §2 关键词覆盖:小吃 + 煎饼 + 麻辣烫
        assert "小吃" in out["keywords"]
        assert "煎饼" in out["keywords"]
        assert "麻辣烫" in out["keywords"]
        # §4 风味词:街头
        assert "街头" in out["keywords"]
        assert all(isinstance(k, str) for k in out["keywords"])

    def test_parse_happy_path_kanto_and_grill(self) -> None:
        """F023 §3 关东 + §3 烧烤:关东煮 / 烤串 / 烤翅."""
        expert = SnacksExpert()
        raw = (
            '{"conclusion":"今天推荐小吃",'
            '"keywords":["小吃","关东煮","烤串","烤翅"],'
            '"matched_allergies":[]}'
        )
        out = expert.parse_output(raw)

        assert out["cuisine_id"] == "snacks"
        # F023 §2 关键词覆盖:小吃
        assert "小吃" in out["keywords"]
        # §3 关东:关东煮
        assert "关东煮" in out["keywords"]
        # §3 烧烤:烤串 / 烤翅
        assert "烤串" in out["keywords"]
        assert "烤翅" in out["keywords"]

    def test_parse_invalid_json_falls_back(self) -> None:
        expert = SnacksExpert()
        out = expert.parse_output("not json at all")

        assert out["cuisine_id"] == "snacks"
        assert out["conclusion"] == "暂不可推荐"
        assert out["keywords"] == []
        assert out["matched_allergies"] == []
