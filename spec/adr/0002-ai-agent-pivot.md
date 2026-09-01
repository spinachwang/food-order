# ADR 0002 — 从"餐饮 Web 应用"转向"AI Agent 午餐决策系统"

- **状态**：Accepted
- **日期**：2026-08-29
- **决策者**：项目负责人
- **取代**：ADR 0001 中关于"餐饮点单 / 外卖 Web 应用"的隐含定位（技术栈本身仍沿用）

## 背景

ADR 0001 确立了 `food-order` 仓库的初始技术栈（FastAPI + Vite/React + MySQL + JWT）。在该 ADR 的语境中，`food-order` 是一个**面向多角色的传统餐饮点单 Web 应用**（顾客 / 商家 / 骑手 / 平台管理员）。

项目实际推进时发现，真正的产品定位是一个**面向办公室打工人的午餐推荐 AI Agent**：

1. 只有一个角色（用户），不需要商家端 / 骑手端
2. 核心价值不是"下单 + 支付"，而是"决策辅助"
3. 决策依赖三类外部信息：用户偏好、附近餐厅、当前天气 —— 需要多 Agent 协作
4. 用户交互形态是**对话**，不是传统的"浏览店铺 → 加入购物车 → 结算"流程

## 决策

把 `food-order` 重新定义为：

> 一个 LangGraph 多 Agent 编排 + Web 聊天界面 + 高德 MCP 集成的午餐决策助手。

具体动作：

| 项 | 处理 |
|---|---|
| 前端（Vite + React） | **保留**，但范围收缩为"单页聊天壳"：一个聊天窗口，渲染流式 SSE |
| 后端（FastAPI） | **保留**，承担 API + LangGraph 执行入口 |
| 数据（MySQL） | **保留**，仅新增 `user_preferences`（M1 一张表；`user_feedback` 见下文修订记录） |
| 鉴权（JWT） | **降级为可选**：M1 用设备 ID / 匿名会话即可，登录态延后 |
| 商家 / 骑手 / 订单 / 支付 / 购物车 | **废弃**（标记 `[ARCHIVED-M0]`） |
| 新增 LangGraph 编排层 | `backend/app/agents/`：StateGraph + 14 菜系 Node + router + summary |
| 新增高德 MCP 集成 | `backend/app/mcp/amap/`：周边搜索 + 天气两个工具封装 |
| 新增 Web 聊天窗口 | `frontend/src/features/chat/`：聊天 UI + SSE 消费 |
| 保留 `spec/adr/0001` 选定的技术栈 | 但 ADR 0001 中"传统 Web 应用"的隐含定位被本 ADR 取代 |

## 理由

- **决策疲劳是真实痛点**：相比"替代美团"这种红海，"帮牛马决定中午吃啥"定位更精准、更易跑通
- **技术栈契合度高**：FastAPI 适合流式输出；LangGraph 适合多 Agent 编排；高德 MCP 现成可用
- **回归路径短**：技术栈完全沿用 ADR 0001，只是**业务方向**变了，没有浪费
- **不破坏现有 M0 骨架**：`backend/app/main.py` + `/healthz` + `frontend/` 默认页都还能跑

## 后果

- M1 范围**完全替换**为 Agent MVP：原 M1 Sprint 1（鉴权 + 店铺 / 菜单 / 订单 CRUD）标记 `[REPLACED]`
- 编号体系重置：原 F001–F020 标记 `[ARCHIVED-M0]`，新增 F001/F002/F003/F010–F024/F030/F031/F040/F021
- `CLAUDE.md` 中"技术栈"表保留原选型；但**业务方向段落**需更新（本 ADR 后另起一次 commit 同步）
- 不再依赖外部商户数据源（不再需要爬美团 / 饿了么）；改为只调用高德 MCP

## 备选方案

- **维持传统 Web 应用定位**：放弃，因不符合用户实际意图
- **完全丢弃现有 Web 栈，改纯 CLI Agent**：放弃，因失去可视化交互
- **不做 MCP，自接高德 REST API**：备选；如果高德 MCP 不可用，回退到该方案（`backend/app/services/amap_client.py` 直连 `https://restapi.amap.com/`）

## 待澄清（执行中跟进）

- 高德 MCP 服务是否已配置？key 放 `.env` 的 `AMAP_API_KEY` 字段
- LangGraph 版本锁定（默认 0.2+ 稳定版）
- 是否做"用户反馈回写偏好"——**已决议 2026-08-30**：M1 不做（见下文修订记录）

## 参考

- ADR 0001：[./0001-initial-stack.md](./0001-initial-stack.md)
- 新定位：[../product.md](../product.md)
- 新功能索引：[../features.md](../features.md)

---

## 修订记录

### 2026-08-30 — M1 范围二次收敛

> 用户确认三件事：(a) M1 不做登录；(b) `budget_lunch_max` 包含配送费；(c) M1 不做反馈。
> 同步影响本 ADR 与 [../features/F001-user-preferences.md](../features/F001-user-preferences.md) / [../data-model.md](../data-model.md) / [../api.md](../api.md) / [../features/F050-chat-shell.md](../features/F050-chat-shell.md) / [../product.md](../product.md) / [../features.md](../features.md) / [../roadmap.md](../roadmap.md)。

**变更摘要：**

1. **鉴权**：从"降级为可选"进一步收紧为 **M1 完全不做**——用户标识只用前端生成的匿名 UUID（`X-User-Id` 请求头 + cookie），无 JWT / 无 session / 无密码。登录态与多设备同步推到 M2。
2. **数据表**：从两张 (`user_preferences` + `user_feedback`) 收敛为 **一张 `user_preferences`**。`user_feedback` 不在 M1 建表；M2 引入反馈学习时再补建。
3. **`/feedback` 端点**：M1 不实现。前端 `go-eat` 仅跳转高德导航，`save-eat` 仅切按钮文案 + toast，均不发起后端请求。
4. **`budget_lunch_max` 语义**：明确**包含配送费**（餐品 + 打包费 + 平台配送费的合计上限），F040 总结 Agent 据此判断"超预算"。

**未变化：**

- 14 菜系专家 + LangGraph 编排 + 高德 MCP + Web 聊天壳四大件保留
- `CLAUDE.md` 中"技术栈"表保留原选型
- 编号体系不变

---

### 2026-08-31 — 路由层细节

> 用户拍板 F002 主 Agent router 的三条实现细节：(a) 引入规则优先 + LLM 兜底的双层路由；(b) `routing_reason` 暴露给前端；(c) 路由决策 M1 不落库。
> 同步影响 [../features/F002-main-agent-router.md](../features/F002-main-agent-router.md)，其它 spec 不受影响。

**变更摘要：**

1. **双层路由**：F002 router 改为两层——第一层是**规则引擎**（关键词 + 偏好权重硬匹配），命中即短路返回，**不调用 LLM**；第一层未命中（"灰色地带"，如"想吃点暖胃的"）才降级到第二层 **LLM 兜底**（§4 prompt）。降低延迟与 token 成本。

2. **`routing_reason` 暴露给前端**：推翻原"避免 AI 心声暴露"默认——`routing_reason` 改为在 F050 的回复气泡中渲染给用户。要求 ≤30 字、人话风格（如"你说想吃辣的 → 川 + 湘"）。LLM prompt 的输出契约相应收紧。

3. **路由决策 M1 不落库**：决策仅保留在 `AgentState.routing_log`（内存 + 日志），不写入数据库。`routing_decisions` 表 / 路由分析看板推到 M2。

**未变化：**

- F002 的对外契约（输入 / 输出 schema、忌口过滤、错误码）保持兼容
- LangGraph 编排整体结构（F021）不变
- 菜系专家并行执行不受影响

---

### 2026-08-31 — F021 重命名为 F004（号段对齐）

> F021（LangGraph 整体工作流）的内容属基础设施，原编号与"01x–02x 菜系专家"号段含义不符。重命名为 F004，归入 `F00x` 基础设施号段。
> 同步影响 [../features.md](../features.md) / [../roadmap.md](../roadmap.md) / [../features/F002-main-agent-router.md](../features/F002-main-agent-router.md) / [../features/F003-cuisine-expert-contract.md](../features/F003-cuisine-expert-contract.md) / [../features/F010-sichuan.md](../features/F010-sichuan.md) / [../features/F030-amap-restaurant-search.md](../features/F030-amap-restaurant-search.md) / [../features/F031-amap-weather.md](../features/F031-amap-weather.md) / [../features/F040-summary-agent.md](../features/F040-summary-agent.md) / [../features/F050-chat-shell.md](../features/F050-chat-shell.md)。

**变更摘要：**

1. **文件重命名**：`spec/features/F021-langgraph-workflow.md` → `spec/features/F004-langgraph-workflow.md`（用 `git mv` 保留历史，非历史重写）。
2. **号段规则修订**：`F00x` 明确为"基础设施"号段（成员：F001 偏好 / F002 router / F003 专家契约 / **F004 LangGraph 工作流**）；`F01x–F02x` 仍为"菜系专家"号段；F021 不再插队占用专家号段位。
3. **依赖引用同步**：上述 10 个文件内的 `F021` / `F021-langgraph-workflow.md` 字面量全部替换为 `F004` / `F004-langgraph-workflow.md`。

**未变化：**

- 本 ADR 第 49 行"编号体系"描述与第 111 行"LangGraph 编排整体结构（F021）不变"作为历史决策保留，**不事后修改**——但当下生效的编号以 F004 为准。
- F004 文件内容（State 类型、Node 列表、Edge 条件、SSE 事件、checkpoint 等）一字未动。
- **编号空间澄清**：M0 时期原 features.md 中 `[ARCHIVED-M0] F004`（提交订单（未支付））与 M1 新 `F004`（LangGraph 工作流）编号相同，但属于不同里程碑 / 不同范畴，**不冲突**——M0 区段已显式标记 `[ARCHIVED-M0]`，且本 ADR 第 49 行明确"原 F001–F020 标记 `[ARCHIVED-M0]`，新增 F001/F002/F003/F010–F024/…"，即 M1 编号体系自 ADR 0002 起独立编号。