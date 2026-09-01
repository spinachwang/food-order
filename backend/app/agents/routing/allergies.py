"""F002 §3.3 忌口硬冲突表。

严格取字面"100% 冲突"——即该菜系几乎无菜可点，而非"部分菜品含"。
其他菜系（粤菜蚝油、西餐奶制品…）的菜品级规避由菜系专家 prompt 完成。
"""

from __future__ import annotations

from types import MappingProxyType

from app.core.constants import ALLERGY_VALUES, CUISINE_IDS

# F002 §3.3 锁定 3 个菜系 + 对应过敏原：
#   fujian          × {shellfish, fish}   闽菜大量海鲜；忌海鲜者几乎无菜可吃
#   western_fastfood × {fried_food}        西式快餐（汉堡/披萨）默认油炸
#   sichuan         × {peanut}             川菜常用花生油（spec §2 例子）
#
# 测试在 tests/unit/test_routing_allergies.py 锁死：
#   keys ⊆ CUISINE_IDS, values ⊆ ALLERGY_VALUES, 仅有这 3 个菜系。
#
# `MappingProxyType` 包裹让外部无法 mutate 这个映射（review feedback：
# 之前 dict 可变，新增菜系时被运行时插入会绕过 F001 schema 校验）。
_HARD_ALLERGY_CONFLICTS_RAW: dict[str, frozenset[str]] = {
    "fujian": frozenset({"shellfish", "fish"}),
    "western_fastfood": frozenset({"fried_food"}),
    "sichuan": frozenset({"peanut"}),
}
HARD_ALLERGY_CONFLICTS: MappingProxyType[str, frozenset[str]] = MappingProxyType(
    _HARD_ALLERGY_CONFLICTS_RAW
)

# 编译期 sanity：发现漂移直接 fail-fast。
for _cuisine, _allergies in HARD_ALLERGY_CONFLICTS.items():
    assert _cuisine in CUISINE_IDS, f"unknown cuisine: {_cuisine}"
    for _a in _allergies:
        assert _a in ALLERGY_VALUES, f"unknown allergy: {_a}"


def filter_conflicts(cuisines: list[str], allergies: set[str]) -> list[str]:
    """从候选菜系列表中剔除与过敏原硬冲突的菜系。

    返回新列表（不可变），不改入参。spec §3.3：不在冲突表内的过敏原 no-op。
    """
    if not allergies:
        return list(cuisines)
    return [c for c in cuisines if not (allergies & HARD_ALLERGY_CONFLICTS.get(c, frozenset()))]


def zero_out_conflicts(weights: dict[str, float], allergies: set[str]) -> dict[str, float]:
    """对加权抽样路径：将硬冲突菜系的权重临时置 0。

    返回新 dict，不改入参（spec 要求不可变）。其他菜系的权重原样保留。
    """
    if not allergies:
        return dict(weights)
    conflicted: set[str] = set()
    for cuisine, conflicts in HARD_ALLERGY_CONFLICTS.items():
        if allergies & conflicts:
            conflicted.add(cuisine)
    return {k: (0.0 if k in conflicted else v) for k, v in weights.items()}
