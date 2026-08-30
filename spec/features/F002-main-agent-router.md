# F002 — 主 Agent 编排（router）

> **状态**：[ ] 未开始
> **所属里程碑**：M1 Agent MVP
> **依赖**：F001（读取偏好）、F003（菜系专家契约）、F021（整体工作流定义入口）
> **被依赖**：F040（总结 Agent 接收 cuisine_results）

## 1. 用户故事

作为 LangGraph 工作流的入口，主 Agent 接收用户消息 + 偏好，决定调哪些菜系专家（1–3 个），把意图与上下文注入到 `AgentState`，然后触发下游菜系专家并行执行。

## 2. 验收清单

- [ ] 接收 `user_message` 后 1 秒内完成菜系路由决策
- [ ] 路由决策可解释：返回 `selected_cuisines: list[str]` 与 `routing_reason: str`
- [ ] 路由策略：
  - **明确意图**（如"想吃辣的"）→ 匹配菜系集合（川 + 湘）
  - **模糊意图**（如"随便推荐"）→ 根据 `cuisine_weights` 抽样 2–3 个
  - **无匹配**（消息为空 / 乱码）→ 返回错误事件，不进入下游
- [ ] 满足忌口过滤：若用户 `allergies` 与某菜系 100% 冲突（如花生过敏 + 川菜常用花生油），该菜系权重临时置 0
- [ ] 路由决策日志可观测：写入 `AgentState.routing_log`

## 3. 输入 / 输出

### 3.1 输入

```python
class MainAgentInput(TypedDict):
    user_message: str
    user_preferences: UserPreferences     # F001
    session_id: str | None
    location_override: str | None
```

### 3.2 输出（写入 `AgentState`）

```python
class AgentState(TypedDict):
    user_message: str
    user_preferences: UserPreferences
    selected_cuisines: list[str]         # 1-3 个 cuisine_id
    routing_reason: str                  # "用户明确说想吃辣 → 川 + 湘"
    routing_log: list[dict]              # 时间戳 + 决策详情
    cuisine_results: list[CuisineExpertOutput]   # 由并行菜系节点填充
    weather: WeatherInfo | None          # F031 填充
    recommendation: Recommendation | None # F040 填充
    errors: list[dict]                   # 全局错误收集
```

### 3.3 路由策略

```text
意图识别（LLM 或规则）
├── "想吃辣的/麻辣"   → [sichuan, hunan]
├── "清淡/养生"        → [cantonese, suzhou, zhejiang]
├── "日料/寿司/刺身"  → [japanese]
├── "西餐/牛排"        → [western]
├── "快餐/快/饱"       → [western_fastfood, chinese_fastfood]
├── "小吃/夜宵/街边"  → [snacks]
├── "甜品/奶茶/咖啡"  → [dessert_drinks]
├── "随便" / 模糊      → 按 cuisine_weights top-2/3 抽样
└── 其他/空            → 默认 cuisine_weights top-2
```

**忌口过滤**：在最终 `selected_cuisines` 之前，对每个候选菜系查 F003 §4 菜系专属提示中的"过敏原注意"。若 100% 冲突，从列表中剔除并记日志。

## 4. Prompt 模板（router 自身）

```text
你是"午餐决策助手"的路由 Agent。决定调哪些菜系专家。

【用户消息】
{message}

【用户偏好摘要】
- 菜系权重：{cuisine_weights_top3}
- 忌口：{allergies}
- 辣度：{spice_tolerance}

【可选菜系】
{cuisine_registry_keys_and_names}

【任务】
1. 输出 `selected_cuisines`：1-3 个 cuisine_id
2. 输出 `routing_reason`：≤30 字说明

【输出格式】严格 JSON：
{
  "selected_cuisines": ["...", "..."],
  "routing_reason": "..."
}
```

## 5. 数据 / 接口变更

- 不新增数据库表
- 不新增 REST 接口
- 新增 LangGraph Node：`backend/app/agents/main_router.py`
- 复用 F001 的 `load_preferences`

## 6. 错误码

| code | 含义 | 处理 |
|---|---|---|
| `EMPTY_MESSAGE` | 用户消息为空 | 返回错误事件，不进下游 |
| `NO_CUISINE_MATCHED` | 路由策略无输出 | 兜底用 cuisine_weights top-1 |
| `ALL_CUISINES_FILTERED` | 全部候选被忌口剔除 | 兜底返回"今天没合适的，换个口味吧" |

## 7. 测试计划

### 单元测试

- [ ] 规则路由：`"想吃辣的"` → `[sichuan, hunan]`
- [ ] 规则路由：`"清淡的"` → `[cantonese, suzhou]`
- [ ] 模糊路由：`"随便"` + `cuisine_weights={"sichuan":0.9}` → `[sichuan, ...]`
- [ ] 忌口过滤：花生过敏 + 高川菜权重 → 川菜被剔除
- [ ] 空消息 → `EMPTY_MESSAGE`

### 集成测试

- [ ] `test_main_router_integration.py`：模拟完整 `AgentState` 流转，验证 `selected_cuisines` 后续被菜系 Node 消费

### 端到端（Playwright）

- [ ] 不直接测；由 F021 覆盖

## 8. 待澄清问题

- 是否引入规则优先 + LLM 兜底的双层路由（先用关键词规则快速过滤，再让 LLM 兜底）？默认是
- `routing_reason` 是否要暴露给前端用户？默认**不暴露**（避免"AI 心声"暴露）
- 路由决策是否要落库用于后续分析？M1 不做