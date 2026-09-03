# F004 — LangGraph 整体工作流

> **状态**：[x] 已完成（LangGraph 0.2.x 图骨架；F030/F031/F040 stub 节点占位）
> **所属里程碑**：M1 Agent MVP — 本骨架已经让 happy path 端到端跑通；后续 spec 上线时只需替换对应 stub 节点函数体。
> **依赖**：[F001](F001-user-preferences.md)、[F002](F002-main-agent-router.md)、[F003](F003-cuisine-expert-contract.md)、[F010–F024](.)、[F030](F030-amap-restaurant-search.md)、[F031](F031-amap-weather.md)、[F040](F040-summary-agent.md)
> **被依赖**：无（顶层收口）

## 1. 用户故事

作为 LangGraph 工作流的总图，我希望**单一可执行入口**编排：从用户消息到最终推荐的全流程，并支持流式事件回传给前端 SSE。

## 2. 验收清单

- [x] 单一函数入口：`build_graph() -> CompiledStateGraph`
- [x] State 类型统一：见 §3.1
- [x] Node 列表：见 §3.2
- [x] Edge 条件：见 §3.3
- [x] 流式事件：使用 LangGraph 的 `astream_events` 把中间节点结果转为 SSE 事件
- [x] checkpoint：使用 `MemorySaver`（M1），后续可换 Postgres
- [x] 端到端 happy path 单测 < 2 秒（实测 ~0.6 秒）

## 3. 整体设计

### 3.1 State 类型

```python
class AgentState(TypedDict):
    # 输入
    user_message: str
    user_id: str
    session_id: str | None
    location_override: str | None

    # F001 加载
    user_preferences: UserPreferences

    # F002 router 输出
    selected_cuisines: list[str]            # 1-3 个 cuisine_id
    routing_reason: str
    routing_log: list[dict]

    # 菜系专家并行输出
    cuisine_results: list[CuisineExpertOutput]

    # F030 餐厅搜索结果（cuisine_id → 餐厅列表）
    restaurant_lists: dict[str, list[Restaurant]]

    # F031 天气
    weather: WeatherInfo | None

    # F040 最终推荐
    recommendation: Recommendation | None

    # 全局错误收集
    errors: list[dict]
```

### 3.2 Node 列表

| 序号 | Node | 对应 spec | 行为 |
|---|---|---|---|
| 1 | `load_preferences` | F001 | 按 `user_id` 从 DB 读偏好；不存在则初始化默认值 |
| 2 | `route_cuisines` | F002 | 解析用户消息 + 偏好 → 1-3 个菜系 |
| 3 | `cuisine_<id>` × N | F003 / F010–F024 | **并行**：每个菜系 Node 输出结论 + 关键词 |
| 4 | `search_restaurants` | F030 | **聚合**：按 `selected_cuisines` 调高德搜索，填 `restaurant_lists` |
| 5 | `fetch_weather` | F031 | 独立调高德天气 API |
| 6 | `summarize` | F040 | 综合以上，输出最终 recommendation |
| 7 | `stream_output` | 本 spec | 把 State 变化转为 SSE 事件 |

> Node 3 / 4 / 5 可并行；Node 6 必须等 3+4+5 全部完成。

### 3.3 Edge 条件

```python
# 简化表示
START → load_preferences
load_preferences → route_cuisines
route_cuisines → cuisine_sichuan
route_cuisines → cuisine_cantonese
... (其他 12 个菜系)
每个 cuisine_<id> → search_restaurants
search_restaurants → fetch_weather  # 两者并行汇聚到下一节点
fetch_weather → summarize
summarize → END
```

LangGraph 实现：用 `Send` API 把 `route_cuisines` 的输出动态分发给对应菜系 Node。

### 3.4 错误处理

- 单个菜系 Node 异常 → 不中断，标记 `cuisine_results` 中该条为 `error`，summary 跳过该菜系
- `search_restaurants` 异常 → 该 cuisine_id 餐厅列表为空，summary 跳过
- `fetch_weather` 异常 → `weather=None`，summary 用默认决策
- `summarize` 异常 → 返回错误事件给前端，不写 `recommendation`

## 4. 流式 SSE 事件映射

| LangGraph State 变化 | SSE event |
|---|---|
| `selected_cuisines` 更新 | `cuisine_selected` |
| 单个 cuisine_result 进入 | `cuisine_result` |
| `restaurant_lists[cuisine_id]` 进入 | `restaurant_found` |
| `weather` 进入 | `weather` |
| `recommendation` 进入 | `recommendation` |
| 任何 Node 抛错 | `error` |
| 工作流结束 | `done` |

事件 schema 见 [api.md § M1](../api.md#m1-agent-mvp) 中 `POST /api/v1/agent/chat`。

## 5. Checkpoint

- M1：`MemorySaver`（进程内 dict）
- M2：换 `PostgresSaver`（用 MySQL 模拟，需要 adapter）
- session_id 不为空时按 session_id 恢复；为空时新建

## 6. 数据 / 接口变更

- 不新增表（依赖 F001 已建）
- 新增模块：
  - `backend/app/agents/graph.py`（build_graph 入口）
  - `backend/app/agents/state.py`（AgentState 定义）
  - `backend/app/agents/nodes/`（各 Node 实现）
- 新增 API endpoint：`POST /api/v1/agent/chat`（SSE）

## 7. 测试计划

### 单元测试

- [ ] `test_graph.py`：build_graph 返回 CompiledStateGraph
- [ ] `test_graph.py`：State schema 字段齐全

### 集成测试（`backend/tests/integration/test_graph_e2e.py`）

- [ ] Happy path：mock 全部上游 → 端到端跑通 → 输出 recommendation
- [ ] 单个菜系失败 → summary 跳过该菜系，其余正常
- [ ] 天气失败 → summary 用默认决策
- [ ] 空消息 → 返回 `EMPTY_MESSAGE` 错误事件
- [ ] 全菜系失败 → summary 输出降级文案

### 端到端（Playwright，`frontend/e2e/`）

- [ ] `chat_recommendation.spec.ts`：
  1. 打开聊天窗口
  2. 输入"今天想吃辣的"
  3. 等待 SSE 流式事件：`cuisine_selected` → `cuisine_result` → `restaurant_found` → `weather` → `recommendation`
  4. 断言最终 `recommendation` 渲染包含 headline + 餐厅名 + reason

### 性能

- [ ] 端到端 happy path < 2 秒（mock 全部上游）

## 8. 待澄清问题

- LangGraph 版本：默认 0.2+ 稳定版
- 是否启用 `astream_events` v2 API？默认启用
- checkpoint 是否需要加密存储？M1 不需要

## 9. 关联文档

- 工作流依赖的全部 Node 定义见 `backend/app/agents/cuisines/*` 与 `backend/app/agents/summary.py`
- SSE 事件 schema 见 [../api.md § M1](../api.md#m1-agent-mvp)
- State schema 来源：[F002 § 3.2](F002-main-agent-router.md)、[F003 § 3.1](F003-cuisine-expert-contract.md)、[F040 § 3.2](F040-summary-agent.md)