"""F024 — 甜品饮品专家专属契约测试.

涵盖 [spec/features/F024-dessert-drinks.md §2 / §6] 验收点:

- cuisine_id / display_name / 继承 `BaseCuisineExpert`
- 关键词覆盖：奶茶 / 咖啡 / 甜品 / 蛋糕 / 冰淇淋（§2 验收点）
- 品牌覆盖：喜茶 / 奈雪 / 蜜雪冰城 / 茶百道 / 星巴克 / Manner / 瑞幸 / Tims / 哈根达斯
- 人均 15-60 元 + 评分 ≥ 4.0 餐厅筛选
- 边界：咖啡 / 奶茶类不分中西；蛋糕 / 冰淇淋归此；与中式快餐不冲突
- 过敏原：奶制品 / 坚果 / 麸质 / 蛋
- §6 测试计划:
  - 用户输入"想喝奶茶" → 关键词含"奶茶"
  - 集成：作为"下午茶"备选可与正餐菜系并行推荐

不重复 F003 `test_base_contract.py` 已覆盖的内容（继承关系 / parse_output
通用 fallback / 全 14 注册表完整性）—— 那些属于通用契约。本文件只断言
**甜品饮品专属** 的行为约束，确保 §4 prompt 要点被实际写进代码。
"""

from __future__ import annotations

from decimal import Decimal

from app.agents.cuisines import CUISINE_REGISTRY, BaseCuisineExpert
from app.agents.cuisines.stubs.dessert_drinks import (
    CUISINE_PROMPT_FRAGMENT,
    DessertDrinksExpert,
)
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
        "user_id": "u-f024",
        "cuisine_weights": dict.fromkeys(CUISINE_IDS, 0.5),
        "allergies": allergies if allergies is not None else [],
        "spice_tolerance": 0,
        "temperature_preference": "room",
        "default_location": "国贸",
        "budget_lunch_min": Decimal("30.00"),
        "budget_lunch_max": Decimal("60.00"),
    }
    return {
        "user_message": user_message,
        "user_preferences": prefs,
        "location": None,
        "spice_tolerance": 0,
        "budget_max": 60.0,
        "budget_min": 30.0,
    }


# ---------------------------------------------------------------------------
# TestDessertDrinksBasicContract — F003 §3.1 必填属性 + F024 §2 cuisine_id
# ---------------------------------------------------------------------------


class TestDessertDrinksBasicContract:
    def test_dessert_drinks_expert_inherits_base(self) -> None:
        assert issubclass(DessertDrinksExpert, BaseCuisineExpert)

    def test_cuisine_id_is_dessert_drinks(self) -> None:
        # F024 §2 验收点：`cuisine_id="dessert_drinks"`
        assert DessertDrinksExpert.cuisine_id == "dessert_drinks"

    def test_display_name_is_tianpin_yinpin(self) -> None:
        # F024 §1 用户故事 + §2 验收要求"甜品饮品"作为显示名
        assert DessertDrinksExpert.display_name == "甜品饮品"

    def test_uses_unified_llm_model(self) -> None:
        # F003 §8.1 — 14 个菜系统一 `MiniMax-M3`
        assert DessertDrinksExpert.llm_model == "MiniMax-M3"

    def test_prompt_fragment_is_non_empty_string(self) -> None:
        assert isinstance(DessertDrinksExpert.prompt_fragment, str)
        assert DessertDrinksExpert.prompt_fragment.strip()


# ---------------------------------------------------------------------------
# TestDessertDrinksInRegistry — F003 §3.2 注册表
# ---------------------------------------------------------------------------


class TestDessertDrinksInRegistry:
    def test_registered_in_cuisine_registry(self) -> None:
        assert "dessert_drinks" in CUISINE_REGISTRY
        assert CUISINE_REGISTRY["dessert_drinks"] is not None

    def test_registry_entry_has_matching_cuisine_id(self) -> None:
        expert = CUISINE_REGISTRY["dessert_drinks"]
        assert expert.cuisine_id == "dessert_drinks"
        assert expert.display_name == "甜品饮品"

    def test_registry_position_matches_cuisine_ids_spec_order(self) -> None:
        # F003 §3.2 / `CUISINE_IDS` 顺序：dessert_drinks 在第 14 位（末位）
        # （川 / 粤 / 鲁 / 苏 / 浙 / 闽 / 湘 / 徽 / 日料 / 西餐 / 西式快餐 /
        #   中式快餐 / 小吃 / 甜品饮品）
        assert CUISINE_IDS.index("dessert_drinks") == 13
        assert tuple(CUISINE_REGISTRY.keys())[13] == "dessert_drinks"


# ---------------------------------------------------------------------------
# TestDessertDrinksPromptFragment — F024 §2 / §4 prompt 要点的实际落位
# ---------------------------------------------------------------------------


class TestDessertDrinksPromptFragment:
    """验证 F024 §2/§4 关键提示已落到 `CUISINE_PROMPT_FRAGMENT` 字面量中.

    这些是**给 LLM 的字面规则**——它们只有在 prompt 片段里真正出现,
    才能引导模型输出符合 §2 §6 验收点的关键词。
    """

    def test_fragment_lists_all_five_keyword_tokens(self) -> None:
        # F024 §2 验收：关键词覆盖 奶茶 / 咖啡 / 甜品 / 蛋糕 / 冰淇淋
        for token in ("奶茶", "咖啡", "甜品", "蛋糕", "冰淇淋"):
            assert token in CUISINE_PROMPT_FRAGMENT, (
                f"F024 §2 要求关键词覆盖 {token!r}；必须出现在 prompt 片段中以引导 LLM 输出"
            )

    def test_fragment_lists_milk_tea_brands(self) -> None:
        # F024 §3 奶茶品牌：喜茶 / 奈雪 / 蜜雪冰城 / 茶百道
        brands = ("喜茶", "奈雪", "蜜雪冰城", "茶百道")
        present = [b for b in brands if b in CUISINE_PROMPT_FRAGMENT]
        assert len(present) >= 2, (
            f"F024 §3 奶茶品牌至少列 2 个；实际命中={present}"
        )

    def test_fragment_lists_coffee_brands(self) -> None:
        # F024 §3 咖啡品牌：星巴克 / Manner / 瑞幸 / Tims
        brands = ("星巴克", "Manner", "瑞幸", "Tims")
        present = [b for b in brands if b in CUISINE_PROMPT_FRAGMENT]
        assert len(present) >= 2, (
            f"F024 §3 咖啡品牌至少列 2 个；实际命中={present}"
        )

    def test_fragment_lists_ice_cream_brands(self) -> None:
        # F024 §3 冰淇淋品牌：哈根达斯
        assert "哈根达斯" in CUISINE_PROMPT_FRAGMENT, (
            "F024 §3 冰淇淋代表品牌必须出现'哈根达斯'"
        )

    def test_fragment_lists_dessert_dishes(self) -> None:
        # F024 §3 甜品：蛋糕 / 泡芙 / 马卡龙
        desserts = ("蛋糕", "泡芙", "马卡龙")
        present = [d for d in desserts if d in CUISINE_PROMPT_FRAGMENT]
        assert "蛋糕" in present, "F024 §3 必须包含'蛋糕'作为甜品代表"
        assert len(present) >= 2, (
            f"F024 §3 甜品至少列 2 个；实际命中={present}"
        )

    def test_fragment_specifies_price_range(self) -> None:
        # F024 §4 关键提示：人均 15-60 元
        assert "人均" in CUISINE_PROMPT_FRAGMENT
        assert "15" in CUISINE_PROMPT_FRAGMENT
        assert "60" in CUISINE_PROMPT_FRAGMENT
        assert any(
            token in CUISINE_PROMPT_FRAGMENT
            for token in ("15-60", "15 - 60", "15 到 60")
        ), "F024 §4 必须显式表达'人均 15-60 元'的价格区间"

    def test_fragment_specifies_rating_threshold(self) -> None:
        # F024 §4 餐厅筛选：评分 ≥ 4.0
        assert "评分" in CUISINE_PROMPT_FRAGMENT
        assert "4.0" in CUISINE_PROMPT_FRAGMENT
        assert "≥ 4.0" in CUISINE_PROMPT_FRAGMENT, (
            "F024 §4 必须显式表达'评分 ≥ 4.0'的餐厅筛选条件"
        )

    def test_fragment_lists_signature_flavors(self) -> None:
        # F024 §4 风味词候选：甜 / 下午茶
        flavors = ("甜", "下午茶")
        present = [f for f in flavors if f in CUISINE_PROMPT_FRAGMENT]
        assert len(present) >= 2, (
            f"F024 §4 必须列'甜'与'下午茶'作为风味词；实际命中={present}"
        )

    def test_fragment_warns_allergens(self) -> None:
        # F024 §4 过敏原注意：奶制品 / 坚果 / 麸质 / 蛋
        allergens = ("奶制品", "dairy", "坚果", "坚果", "麸质", "gluten", "蛋", "egg")
        present = [a for a in allergens if a in CUISINE_PROMPT_FRAGMENT]
        assert len(present) >= 4, (
            f"F024 §4 必须列 4 类过敏原（奶制品/坚果/麸质/蛋）；实际命中={present}"
        )

    def test_fragment_specifies_keyword_generation_rule(self) -> None:
        # F024 §4 关键词生成规则：包含"奶茶/咖啡/甜品/蛋糕"中 1-2 个
        # + 1 个风味词（"甜"、"下午茶"）
        assert "关键词" in CUISINE_PROMPT_FRAGMENT
        assert any(
            token in CUISINE_PROMPT_FRAGMENT for token in ("奶茶", "咖啡", "甜品", "蛋糕")
        )
        assert any(flavor in CUISINE_PROMPT_FRAGMENT for flavor in ("甜", "下午茶"))

    def test_fragment_distinguishes_from_western_fastfood(self) -> None:
        # F024 §4 边界：咖啡 / 奶茶类不分中西——本 Node 同样承接星巴克 / 瑞幸
        # 等西式连锁，与 F020 西式快餐（汉堡 / 薯条）边界
        assert "西式快餐" in CUISINE_PROMPT_FRAGMENT, (
            "F024 §4 边界必须显式提及'西式快餐'以防 LLM 把咖啡归 F020"
        )

    def test_fragment_distinguishes_from_chinese_fastfood(self) -> None:
        # F024 §4 边界：与中式快餐（F022）边界——快餐店卖奶茶/咖啡仍归 F024
        assert "中式快餐" in CUISINE_PROMPT_FRAGMENT, (
            "F024 §4 边界必须显式提及'中式快餐'以防 LLM 把奶茶误推 F022"
        )


# ---------------------------------------------------------------------------
# TestDessertDrinksBuildPrompt — F024 §6 行为验收：user_message → prompt 内容
# ---------------------------------------------------------------------------


class TestDessertDrinksBuildPrompt:
    """F024 §6 测试计划：用户输入"想喝奶茶"/"想吃蛋糕"/"下午茶" → 关键词覆盖."""

    def test_milk_tea_input_prompt_includes_brands(self) -> None:
        """F024 §6 验收点：用户输入"想喝奶茶"时，build_prompt 必须含奶茶品牌."""
        prompt = DessertDrinksExpert().build_prompt(_build_input("想喝奶茶"))

        # 用户原始输入被注入
        assert "想喝奶茶" in prompt
        # §2 菜系词：奶茶
        assert "奶茶" in prompt
        # §3 至少一个奶茶品牌作为候选
        assert any(brand in prompt for brand in ("喜茶", "奈雪", "蜜雪冰城", "茶百道"))

    def test_coffee_input_prompt_includes_brands(self) -> None:
        """用户输入"想喝咖啡"时，prompt 必须含咖啡品牌."""
        prompt = DessertDrinksExpert().build_prompt(_build_input("想喝咖啡"))

        assert "咖啡" in prompt
        assert any(brand in prompt for brand in ("星巴克", "Manner", "瑞幸", "Tims"))

    def test_cake_input_prompt_carries_cake_term(self) -> None:
        """用户输入"想吃蛋糕"时，prompt 必须把"蛋糕"作为代表菜候选."""
        prompt = DessertDrinksExpert().build_prompt(_build_input("想吃蛋糕"))

        assert "蛋糕" in prompt
        # §4 风味词：甜
        assert "甜" in prompt

    def test_ice_cream_input_prompt_carries_brand(self) -> None:
        """用户输入"想吃冰淇淋"时，prompt 必须含冰淇淋代表品牌."""
        prompt = DessertDrinksExpert().build_prompt(_build_input("想吃冰淇淋"))

        assert "冰淇淋" in prompt
        assert "哈根达斯" in prompt

    def test_afternoon_tea_input_promotes_xiawucha_flavor(self) -> None:
        """用户输入"想下午茶"时，prompt 必须显式提及"下午茶"作为风味词."""
        prompt = DessertDrinksExpert().build_prompt(_build_input("想下午茶"))

        assert "下午茶" in prompt

    def test_dairy_allergy_input_promotes_allergen_warning(self) -> None:
        """用户输入"奶过敏"时，prompt 必须把 dairy / 麸质 / 坚果 / 蛋
        过敏原标签置入,让 LLM 在 matched_allergies 中正确返回."""
        prompt = DessertDrinksExpert().build_prompt(_build_input("我奶过敏"))

        # §4 过敏原注意：奶制品 / 坚果 / 麸质 / 蛋
        assert any(token in prompt for token in ("奶制品", "dairy"))
        assert any(token in prompt for token in ("坚果", "nuts"))
        assert any(token in prompt for token in ("麸质", "gluten"))
        assert any(token in prompt for token in ("蛋", "egg"))

    def test_milk_tea_no_western_fastfood_signature(self) -> None:
        """甜品饮品 build_prompt 不应把西式快餐代表菜（汉堡/薯条/炸鸡）混入,
        避免 LLM 误推."""
        prompt = DessertDrinksExpert().build_prompt(_build_input("想喝奶茶"))

        for dish in ("汉堡", "薯条", "炸鸡"):
            assert dish not in prompt, (
                f"甜品饮品 prompt 不应包含西式快餐代表菜 {dish!r}"
            )


# ---------------------------------------------------------------------------
# TestDessertDrinksParallelSafety — F024 §6 集成：作为"下午茶"备选可与正餐菜系并行
# ---------------------------------------------------------------------------


class TestDessertDrinksParallelSafety:
    """F024 §6 验收点：作为"下午茶"备选可与正餐菜系并行推荐."""

    def test_dessert_drinks_coexists_with_main_cuisines(self) -> None:
        # 甜品饮品 Node 与所有正餐菜系都注册到统一 registry
        for cid in ("sichuan", "cantonese", "shandong", "western", "japanese"):
            assert cid in CUISINE_REGISTRY
            assert "dessert_drinks" in CUISINE_REGISTRY

    def test_dessert_drinks_prompt_fragment_is_distinct(self) -> None:
        """各菜系的 prompt_fragment 必须互不污染——甜品饮品专属代表不应
        跑到正餐菜系."""
        from app.agents.cuisines.stubs.sichuan import SichuanExpert

        # 甜品饮品 fragment 至少包含一个甜品饮品代表
        assert "奶茶" in DessertDrinksExpert.prompt_fragment
        # 川菜 fragment 不应包含甜品饮品代表
        assert "奶茶" not in SichuanExpert.prompt_fragment
        assert "冰淇淋" not in SichuanExpert.prompt_fragment

    def test_dessert_drinks_parse_output_does_not_leak_to_other_cuisines(self) -> None:
        """parse_output 强制写入自己的 cuisine_id, 不会污染其它菜系输出."""
        expert = DessertDrinksExpert()
        raw = (
            '{"conclusion":"推荐奶茶",'
            '"keywords":["奶茶","喜茶","甜","下午茶"],'
            '"matched_allergies":["dairy"]}'
        )
        out = expert.parse_output(raw)

        assert out["cuisine_id"] == "dessert_drinks"
        assert "奶茶" in out["keywords"]


# ---------------------------------------------------------------------------
# TestDessertDrinksParseOutput — F003 §3.3 甜品饮品 Node 自己的解析行为
# ---------------------------------------------------------------------------


class TestDessertDrinksParseOutput:
    """甜品饮品继承的 `BaseCuisineExpert.parse_output` 对甜品饮品专用字段."""

    def test_parse_happy_path_milk_tea_and_coffee(self) -> None:
        expert = DessertDrinksExpert()
        conclusion = "今天适合来杯奶茶"
        raw = (
            f'{{"conclusion":"{conclusion}",'
            '"keywords":["奶茶","咖啡","喜茶","甜","下午茶"],'
            '"matched_allergies":[]}'
        )
        out = expert.parse_output(raw)

        assert out["cuisine_id"] == "dessert_drinks"
        assert out["conclusion"] == conclusion
        # F024 §2 关键词覆盖：奶茶 / 咖啡
        assert "奶茶" in out["keywords"]
        assert "咖啡" in out["keywords"]
        # §3 品牌：喜茶
        assert "喜茶" in out["keywords"]
        # §4 风味词：甜 / 下午茶
        assert "甜" in out["keywords"]
        assert "下午茶" in out["keywords"]
        assert all(isinstance(k, str) for k in out["keywords"])

    def test_parse_happy_path_cake_and_ice_cream(self) -> None:
        """F024 §3 甜品 + §3 冰淇淋：蛋糕 / 泡芙 / 冰淇淋 / 哈根达斯."""
        expert = DessertDrinksExpert()
        raw = (
            '{"conclusion":"今天推荐甜品",'
            '"keywords":["甜品","蛋糕","泡芙","冰淇淋","哈根达斯"],'
            '"matched_allergies":[]}'
        )
        out = expert.parse_output(raw)

        assert out["cuisine_id"] == "dessert_drinks"
        # F024 §2 关键词覆盖：甜品 / 蛋糕 / 冰淇淋
        assert "甜品" in out["keywords"]
        assert "蛋糕" in out["keywords"]
        assert "冰淇淋" in out["keywords"]
        # §3 甜品代表：泡芙
        assert "泡芙" in out["keywords"]
        # §3 冰淇淋代表品牌：哈根达斯
        assert "哈根达斯" in out["keywords"]

    def test_parse_happy_path_with_allergens(self) -> None:
        """F024 §4 过敏原：奶制品 / 坚果 / 麸质 / 蛋——若 LLM 命中应透传."""
        expert = DessertDrinksExpert()
        raw = (
            '{"conclusion":"今天推荐甜品",'
            '"keywords":["奶茶","蛋糕"],'
            '"matched_allergies":["dairy","tree_nut","wheat","egg"]}'
        )
        out = expert.parse_output(raw)

        assert out["cuisine_id"] == "dessert_drinks"
        assert "dairy" in out["matched_allergies"]
        assert "tree_nut" in out["matched_allergies"]
        assert "wheat" in out["matched_allergies"]
        assert "egg" in out["matched_allergies"]

    def test_parse_invalid_json_falls_back(self) -> None:
        expert = DessertDrinksExpert()
        out = expert.parse_output("not json at all")

        assert out["cuisine_id"] == "dessert_drinks"
        assert out["conclusion"] == "暂不可推荐"
        assert out["keywords"] == []
        assert out["matched_allergies"] == []
