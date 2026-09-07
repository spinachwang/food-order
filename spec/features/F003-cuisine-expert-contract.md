# F003 — 菜系专家通用契约

> **状态**：[x] 已完成（M1 Phase 2 — 2026-09-07 base.run() 真链路接通，655 全量单测通过）
> **所属里程碑**：M1 Agent MVP
> **依赖**：F001（用户偏好）、F030（餐厅搜索）
> **被依赖**：F010–F024（14 个菜系专家）、F004（整体工作流）

本 spec 是 14 个菜系专家（川 / 粤 / 鲁 / 苏 / 浙 / 闽 / 湘 / 徽 / 日料 / 西餐 / 西式快餐 / 中式快餐 / 小吃 / 甜品饮品）的**共同骨架**。每个具体菜系 spec 必须**引用并遵循**本文档的契约，不重复定义。

## 1. 用户故事

作为 LangGraph 工作流，我希望所有菜系专家遵循统一的 Node 接口与输出 schema，以便主 Agent 可以**并行调度任意菜系**而不关心内部实现差异。

## 2. 验收清单

- [x] 每个菜系 Node 继承 `BaseCuisineExpert` 抽象类
- [x] 每个菜系注册到 `CUISINE_REGISTRY`（`cuisine_id` → Node 实例）
- [x] 每个菜系 Node 的输入 / 输出 schema 与本 spec §3 完全一致
- [x] 每个菜系 prompt 模板符合本 spec §4 模板结构
- [x] 每个菜系 spec 文件都引用本文档，不重复定义契约
- [x] 任意菜系 Node 可被主 Agent router 单独或并行调用

## 3. 输入 / 输出（Agent 视角）

### 3.1 LangGraph Node 接口

```python
from abc import ABC, abstractmethod
from typing import TypedDict
from langgraph.graph import Node

class CuisineExpertInput(TypedDict):
    user_message: str                    # 用户原始输入
    user_preferences: UserPreferences    # F001 加载的偏好
    location: str | None                 # 搜索锚点
    spice_tolerance: int                 # 0-3，0=不吃辣
    budget_min: float | None
    budget_max: float | None

class CuisineExpertOutput(TypedDict):
    cuisine_id: str                      # 与 F003 §3.2 一致
    conclusion: str                      # 一句话结论（"今天适合来份水煮鱼"）
    keywords: list[str]                  # 传给 F030 的搜索关键词
    matched_allergies: list[str]         # 该菜系下需要避开的过敏原（用于 summary agent 二次校验）

class BaseCuisineExpert(ABC):
    """抽象基类（F003 §2 验收点：每个菜系 Node 继承本类）。

    TODO(M2): matched_allergies 字段是否保留待 F003 §7 决议。
    """
    cuisine_id: str                      # 子类必须重写（与 F003 §3.2 cuisine_id 一致）
    display_name: str                    # 中文显示名（"川菜"）；子类必须重写
    llm_model: str = "MiniMax-M3"        # 统一使用同一模型（详见 §8.1）
    prompt_fragment: str = ""            # 菜系专属 prompt 片段；子类可选重写

    def build_prompt(self, inp: CuisineExpertInput) -> str:
        """默认实现：拼接 fragment + 公共模板。子类可选 override。"""
        ...

    def parse_output(self, raw: str) -> CuisineExpertOutput:
        """默认 JSON parse + 降级（详见 §3.3）。子类继承即可。"""
        ...

    @abstractmethod
    async def run(self, state: AgentState) -> dict[str, object]:
        """LangGraph Node 入口.

        Phase 1 stub: 抛 NotImplementedError（F004 在 wiring 测试用 mock 覆盖）.
        Phase 2 (2026-09-07): `BaseCuisineExpert` 默认实现已就位 — 调真实 LLM
        (`LLMProvider.complete`), parse_output → CuisineExpertOutput. 14 个菜系
        一律走 base.run(); 子类只在需要追加菜系专属 prompt shaping 时 override.
        LLM 失败 / 超时 → 返回 `_fallback_output` (keywords=[], conclusion="暂不可推荐").
        """
        ...
```

### 3.2 菜系标识符（cuisine_id）枚举

```python
CUISINE_REGISTRY = {
    "sichuan":         ("川菜",         F010),
    "cantonese":       ("粤菜",         F011),
    "shandong":        ("鲁菜",         F012),
    "suzhou":          ("苏菜",         F013),
    "zhejiang":        ("浙菜",         F014),
    "fujian":          ("闽菜",         F015),
    "hunan":           ("湘菜",         F016),
    "anhui":           ("徽菜",         F017),
    "japanese":        ("日料",         F018),
    "western":         ("西餐",         F019),
    "western_fastfood":("西式快餐",     F020),
    "chinese_fastfood":("中式快餐",     F022),
    "snacks":          ("小吃",         F023),
    "dessert_drinks":  ("甜品饮品",     F024),
}
```

### 3.3 错误与重试

- **LLM 解析失败 → 重试 1 次（归属 expert 层，不在 provider 层做）**：LLM provider 层只对 HTTP 5xx / 429 / timeout 做 transport-level 重试（exponential backoff，可配置 max_retries）；`BaseCuisineExpert.parse_output` 收到 raw 字符串后做 1 次 JSON parse 重试，仍失败则该菜系 Node 输出 `conclusion="暂不可推荐"` + `keywords=[]`，主流程降级到其他菜系
- `keywords` 为空 → 跳过 F030 调用，不向 summary agent 提供餐厅
- 单个菜系 Node 异常 → **不中断**整体工作流，由 summary agent 决定如何处理（详见 F040）

## 4. Prompt 模板结构

```text
你是一位 {cuisine_display_name} 推荐专家。

【用户输入】
{message}

【用户偏好】
- 不吃 / 忌口：{allergies_str}
- 辣度承受：{spice_tolerance_str}   # 0=不吃辣 / 1=微辣 / 2=中辣 / 3=重辣
- 预算：{budget_str}              # "20-60 元" 或 "不限"
- 默认位置：{location_str}        # "国贸三期" 或 "未指定"

【你的任务】
1. 输出一句话结论（≤30 字）：今天是否适合推荐 {cuisine_display_name}，若有代表性菜品则点名
2. 输出 3-5 个高德搜索关键词（含菜系词 + 代表性菜名 + 风味词）

【输出格式】严格 JSON，不要多余文字：
{
  "conclusion": "...",
  "keywords": ["...", "...", "..."],
  "matched_allergies": ["..."]
}

【该菜系要点】（由各菜系 spec 自填）
{...菜系专属提示...}
```

各菜系 spec 在 `{...菜系专属提示...}` 段补充：

- 代表性菜品清单（用于关键词生成）
- 风味 / 技法关键词（如"麻辣 / 鲜香 / 清淡"）
- 与邻近菜系的边界澄清（如"川湘不要互推"）
- 过敏原注意（如川菜常用花生油）

## 5. 数据 / 接口变更

- 新增抽象类：`backend/app/agents/cuisines/base.py`
- 新增注册表：`backend/app/agents/cuisines/registry.py`
- 新增 LangGraph Node 类型协议：`CuisineExpert`
- 不新增数据库表
- 不新增 REST 接口

## 6. 测试计划

### 单元测试

- [x] `test_base_contract.py`：所有 14 菜系 Node 继承 `BaseCuisineExpert`，注册到 `CUISINE_REGISTRY`
- [x] `test_base_contract.py`：每个 Node 的 `parse_output` 能正确解析合法 JSON
- [x] `test_base_contract.py`：每个 Node 在 LLM 返回非法 JSON 时按 §3.3 降级

### 集成测试

- [x] `test_cuisine_parallel.py`：主 Agent 可并行触发 ≥3 个菜系 Node，且结果独立聚合到 `AgentState.cuisine_results`

### 端到端（Playwright）

- [ ] 不直接测；由 F004（整体工作流）的 e2e 覆盖

## 7. 待澄清问题

- `matched_allergies` 字段是否真的必要（summary agent 也可自查）？可后续精简

## 8. 技术约定（暂定）

> 以下决策为 M1 阶段的临时约定，等后续迭代或接入真实 LLM 服务后再评估是否调整。

### 8.1 LLM 选型

- **统一使用 `MiniMax-M3`**，所有 14 个菜系 Node 共享同一模型
- 不按菜系难度切模型（暂定；后续若出现明显能力/成本瓶颈再扩展）
- 在 `BaseCuisineExpert` 上以类属性 `llm_model: str = "MiniMax-M3"` 暴露，便于后续统一切换

### 8.2 语言约定

- **统一使用中文**：prompt 模板、LLM 输出、`keywords` 列表全部使用中文
- keywords 仅中文，不做双语（暂定；后续若高德 POI 匹配率不足再评估）