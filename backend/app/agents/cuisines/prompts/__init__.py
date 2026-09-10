"""Prompt template module — see per-cuisine submodules for fragments.

Per ADR-0003 `提示词 first-class 资产`, 提示词与业务代码分离, 统一在此模块下:

- `base` — F003 §4 公共 base prompt 模板 (`render_base_prompt` + `_TEMPLATE`).
- `sichuan` — F010 川菜专属 fragment + 代表菜清单.

调用方应通过具体子模块导入常量, 不直接依赖本 `__init__`,
避免隐式重导出掩盖真实的提示词依赖关系.
"""

from app.agents.cuisines.prompts.base import render_base_prompt

__all__ = ["render_base_prompt"]
