"""川菜专家完整实现 — F010.

继承 F003 §3.1 `BaseCuisineExpert`, 引入川菜专属 prompt 片段与代表菜清单.

## 提示词位置 (per ADR-0003)

本文件 **不内联任何 prompt 字符串**; 所有提示词片段与菜品清单均在
`app.agents.cuisines.prompts.sichuan` 模块, 通过稳定 API 引用:

- `from app.agents.cuisines.prompts.sichuan import CUISINE_PROMPT_FRAGMENT`
- `from app.agents.cuisines.prompts.sichuan import SIGNATURE_DISHES`

修改提示词文案 / 菜品清单只动 `prompts/sichuan.py`, 业务代码保持不变.

## 与 F010 §4 spec 的差异

`CUISINE_PROMPT_FRAGMENT` 在 F010 §4 基础上扩展了以下内容, 让 LLM 指令更明确:

1. **代表菜清单**: 把 §3 的菜品按"经典 / 火锅 / 面食 / 小吃"分类列出, 让 LLM 更易选 2-3 道.
2. **风味关键词**: 把 §4 提到的"麻辣 / 花椒 / 火锅"等显式列出, 供 LLM 抽取.
3. **过敏原 LLM 动作指令**: 明示 "如 allergies 含 peanut, 必须在 matched_allergies 中输出 'peanut'",
   把 §2 验收点 3 落到 LLM 行为层面.

如后续 spec 修订, 这些扩展内容须同步回写到 `spec/features/F010-sichuan.md §4`,
避免 prompt 与 spec 双向 drift.

## Phase 1 范围

`run()` 继承父类的 `NotImplementedError`, 由 F004 在 LangGraph
工作流中通过节点 body 调用 `build_prompt` + LLM + `parse_output`.
"""

from app.agents.cuisines.base import BaseCuisineExpert
from app.agents.cuisines.prompts.sichuan import (
    CUISINE_PROMPT_FRAGMENT,
    SIGNATURE_DISHES,
)


class SichuanExpert(BaseCuisineExpert):
    """川菜推荐专家 — F010.

    关键契约:
    - `cuisine_id = "sichuan"` / `display_name = "川菜"`
    - `prompt_fragment` 引用 `prompts.sichuan.CUISINE_PROMPT_FRAGMENT`
      (含花生油风险、与湘菜 / 徽菜的边界澄清)
    - `signature_dishes` 引用 `prompts.sichuan.SIGNATURE_DISHES`
    - 关键词生成规则通过 `prompt_fragment` 透传给 LLM
    - 实际 LLM 调用在 F004 LangGraph 工作流中实现（Phase 1 抛 NotImplementedError）
    """

    cuisine_id = "sichuan"
    display_name = "川菜"
    prompt_fragment = CUISINE_PROMPT_FRAGMENT
    signature_dishes: tuple[str, ...] = SIGNATURE_DISHES
