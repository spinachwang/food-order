# F002 — 主 Agent 编排（router）

> **状态**：[ ] 未开始
> **所属里程碑**：M1 Agent MVP
> **依赖**：F001（读取偏好）、F003（菜系专家契约）、F004（整体工作流定义入口）
> **被依赖**：F040（总结 Agent 接收 cuisine_results）

## 1. 用户故事

作为 LangGraph 工作流的入口，主 Agent 接收用户消息 + 偏好，决定调哪些菜系专家（1–3 个），把意图与上下文注入到 `AgentState`，然后触发下游菜系专家并行执行。

## 2. 验收清单

- [ ] **分层时间预算**（原「1 秒内完成」对第二层物理上不可达，故拆开）：
  - 第一层规则 / 模糊路由：**< 100ms**（纯内存字符串匹配，不含网络 IO）
  - 第二层 LLM 兜底：**< 5s**，超时按 `NO_CUISINE_MATCHED` 降级到 `cuisine_weights` top-1
- [ ] 路由决策可解释：返回 `selected_cuisines: list[str]` 与 `routing_reason: str`
- [ ] **双层路由** ：
  - 第一层：**规则优先**（关键词 + 菜系权重的硬匹配），命中即短路返回，**不调用 LLM**
  - 第二层：**LLM 兜底**（§4 prompt），规则未命中时才走 LLM
- [ ] 路由策略：
  - **明确意图**（如"想吃辣的"）→ 匹配菜系集合（川 + 湘）— 规则层处理
  - **模糊意图**（如"随便推荐"）→ 根据 `cuisine_weights` 抽样 2–3 个 — 规则层处理
  - **灰色地带**（如"想吃点暖胃的"）→ 规则未命中，降级到 LLM 兜底
  - **无匹配**（消息为空 / 乱码）→ 第一层直接返回错误事件，不进入第二层
- [ ] **`routing_reason` 暴露给前端**：≤30 字、人话风格（如"你说想吃辣的 → 川 + 湘"），由 F050 在回复气泡中渲染
- [ ] 满足忌口过滤：若用户 `allergies` 与某菜系 100% 冲突（如花生过敏 + 川菜常用花生油），该菜系权重临时置 0
- [ ] 路由决策日志可观测：写入 `AgentState.routing_log`；**M1 不落库**（决策仅留在内存 + 日志，路由决策落库分析推到 M2）

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

> **实现说明**：router 节点不整体覆写 `AgentState`，而是返回一个**部分状态** `RouterOutput`
> （`app/agents/state.py` 中全 `NotRequired` 的 TypedDict），由 F004 的图合并——
> 与既有 `BaseCuisineExpert.run()` 的返回约定一致。
>
> **已知不一致（留给 F004 决议）**：上表 `cuisine_results` 写作 `list[CuisineExpertOutput]`，
> 但 `app/agents/state.py` 实现为 `dict[str, CuisineExpertOutput]`（按 `cuisine_id` 索引，
> 对 LangGraph 并行 fan-in 更自然）。router **完全不读** `cuisine_results`，
> 故本 feature 不动它，只在代码中留 `# TODO(F004)`。

### 3.3 路由策略（双层：规则优先 → LLM 兜底）

规则层按**意图标签（tag）分区**，而非线性「命中即合并」。同一 tag 只有一条规则能赢；
标签分两级优先级，显式点名强于口味修饰。

```text
第一层：规则引擎（关键词 + 偏好权重，硬匹配）

  优先级 1 — 显式点名菜系（用户直接说出菜系名，最强信号；14 条，各对应 1 个 cuisine_id）
  ├── "川菜/四川菜/川味"        → [sichuan]                             ✅ 短路
  ├── "粤菜/广东菜/广式/早茶"   → [cantonese]                           ✅ 短路
  └── …（其余 12 菜系同构，见 backend/app/agents/routing/rules.py）

  优先级 2 — 口味修饰意图
  ├── "想吃辣/吃辣/麻辣/辣的"   → [sichuan, hunan]                      ✅ 短路
  ├── "清淡/养生/不油/少油"     → [cantonese, suzhou, zhejiang]         ✅ 短路
  ├── "快餐/简餐/吃快/吃饱/饱腹/扛饿"
  │                             → [western_fastfood, chinese_fastfood] ✅ 短路
  ├── "小吃/夜宵/街边/路边摊"   → [snacks]                              ✅ 短路
  ├── "甜品/奶茶/咖啡/蛋糕"     → [dessert_drinks]                      ✅ 短路
  ├── "随便/都行/无所谓/你决定" → 按 cuisine_weights 加权随机抽 2-3 个   ✅ 短路
  ├── 互斥标签同时命中且无显式点名（如"清淡的辣菜"）  ↓ 降级到第二层
  └── 未命中                                          ↓ 降级到第二层
                                ↓
第二层：LLM 兜底（§4 prompt，处理"灰色地带"）
└── LLM 输出            → [cuisines...] + routing_reason        ✅ 进入下游
```

**合并规则**：多个非互斥 tag 同时命中时，按「显式点名优先 → 口味修饰」顺序合并去重，截断 3 个。
例：`"日料，清淡的"` → `[japanese, cantonese, suzhou]`（japanese 因显式点名占首位，不被粤苏浙挤掉）。

**互斥标签**：`{spicy, light}` 语义冲突。同时命中且无显式点名时不做武断合并，
直接降级到第二层由 LLM 判断——这正是本 spec 说的"灰色地带"。

**禁止单字关键词**：`"快"` / `"饱"` 一类单字在子串匹配下误命中率过高
（「我**快**到了」「我吃**饱**了」「吃得有点**快**」都会被判成快餐），
规则表中所有关键词**必须 ≥2 字**。

**"随便"的抽样语义**：按 `cuisine_weights` 做**加权随机抽样**（无放回，n ∈ {2,3}），
而非确定性 top-N——同一用户重复说"随便"应当拿到不同组合（午餐决策的核心价值）。
`random.Random` 实例通过参数注入，测试传固定 seed 保证确定性。

**空消息 / 乱码**：第一层就拒绝，不进入第二层，直接返回 `EMPTY_MESSAGE` 错误事件。
「乱码」判定 = strip 后无任何 CJK / 字母 / 数字字符（如 `"！！！@#￥"`）。

**忌口过滤**：在最终 `selected_cuisines` 之前（无论哪一层）套用**硬冲突表**
`HARD_ALLERGY_CONFLICTS`（`backend/app/agents/routing/allergies.py`）。
表的口径严格取字面「**100% 冲突**」——即该菜系几乎无菜可点，而非「部分菜品含」：

| cuisine_id | 冲突过敏原 | 依据（F003 §4 菜系专属提示） |
|---|---|---|
| `fujian` | `shellfish`, `fish` | 「闽菜大量海鲜；忌 shellfish / fish 者**几乎无菜可吃**」 |
| `western_fastfood` | `fried_food` | 「油炸物（fried_food）**默认含**」 |
| `sichuan` | `peanut` | 「川菜常用花生油」（本 spec §2 点名的例子） |

其余菜系（粤菜蚝油、西餐奶制品、苏菜蟹粉…）属「部分菜品含」，**不在路由层硬拦**，
由各菜系专家 prompt 的「过敏原注意」在**菜品级**规避——保住用户的可选面。

命中冲突时：该菜系权重临时置 0（模糊抽样场景）或从列表中剔除（规则 / LLM 场景），并记 `routing_log`。

## 4. Prompt 模板（router LLM 兜底阶段的输入）

> 仅当第一层规则未命中时调用；规则层命中场景不进入此 prompt。

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
- 复用 F001 的 `load_preferences`
- **不引入 `langgraph` 依赖**：本 feature 只交付一个 LangGraph-node *形状*的纯 async 函数
  （`state -> partial state`，与既有 `BaseCuisineExpert.run` 同构）。真正的组图 / `Send` 分发
  归 F004。理由见 [ADR 0002](../adr/0002-router-two-layer-strategy.md)。
- 新增模块：

| 文件 | 职责 |
|---|---|
| `backend/app/agents/main_router.py` | 节点入口 `route_cuisines()` + 双层编排 + 错误码常量 |
| `backend/app/agents/routing/rules.py` | 意图标签规则表、`match_rules()`、模糊词、`sample_by_weights()` |
| `backend/app/agents/routing/allergies.py` | `HARD_ALLERGY_CONFLICTS` + 权重置零 / 列表剔除 |
| `backend/app/agents/routing/prompt.py` | §4 LLM prompt 渲染 + JSON 回包解析 |
| `backend/app/agents/state.py`（改） | `AgentState` 加 `routing_reason` / `routing_log`；新增 `RoutingLogEntry` / `RouterOutput` |

## 6. 错误码

| code | 含义 | 处理 |
|---|---|---|
| `EMPTY_MESSAGE` | 用户消息为空 | 返回错误事件，不进下游 |
| `NO_CUISINE_MATCHED` | 路由策略无输出 | 兜底用 cuisine_weights top-1 |
| `ALL_CUISINES_FILTERED` | 全部候选被忌口剔除 | 兜底返回"今天没合适的，换个口味吧" |

## 7. 测试计划

### 单元测试

`backend/tests/unit/test_main_router.py`：

- [ ] **规则层短路**：明确关键词（"想吃辣的"）命中时，**mock LLM 不被调用**（`FakeLLMProvider.calls == []`），直接返回 `[sichuan, hunan]`
- [ ] 规则路由：`"想吃辣的"` → `[sichuan, hunan]`
- [ ] 规则路由：`"清淡的"` → `[cantonese, suzhou, zhejiang]`（3 个，与 §3.3 规则表一致）
- [ ] 规则路由参数化：日料 / 西餐 / 快餐 / 夜宵 / 奶茶 各命中对应菜系
- [ ] **显式点名优先**：`"日料，清淡的"` → `japanese` 位于首位，不被粤苏浙挤掉
- [ ] **互斥标签降级**：`"想吃清淡的辣菜"`（spicy + light）→ 不武断合并，降级调 LLM
- [ ] **LLM 兜底**：规则未命中（"想吃点暖胃的"）→ mock LLM 被调用，返回 LLM 给出的菜系列表
- [ ] LLM 降级：坏 JSON / `selected_cuisines` 为 null / 抛 `LLMTimeoutError` → 均 `NO_CUISINE_MATCHED` + top-1 兜底，且**不向上抛异常**
- [ ] LLM 回包含未知 `cuisine_id` → 静默丢弃，仅保留 ∈ `CUISINE_IDS` 的
- [ ] 模糊路由：`"随便"` + `cuisine_weights={"sichuan":0.9}` → 固定 seed 下输出确定；固定 seed 大样本下 0.9 权重的命中频率显著高于低权重
- [ ] **routing_reason 格式**：所有路径（规则 / 模糊 / LLM / 各降级分支）输出的 `routing_reason` 长度均 ≤30 字、人话风格（如"暖胃的 → 粤 + 苏"），可被前端直接渲染
- [ ] 忌口过滤：花生过敏 + 高川菜权重 → 川菜被剔除
- [ ] 忌口过滤：`shellfish` 过敏 → `fujian` 被剔除；不在冲突表内的过敏原 → no-op
- [ ] `ALL_CUISINES_FILTERED` → `routing_reason == "今天没合适的，换个口味吧"`
- [ ] 空消息 `""` / `"   "` / 乱码 `"！！！@#￥"` → `EMPTY_MESSAGE`（**不进入 LLM 兜底**）
- [ ] `state` 缺 `user_preferences` → 降级到中性权重，不 `KeyError`
- [ ] `routing_log` 形状齐全（`ts` / `layer` / `detail` / `elapsed_ms`），且规则层 `elapsed_ms < 100`

`backend/tests/unit/test_routing_rules.py`（表完整性）：

- [ ] 所有规则的 `cuisines` ⊆ `CUISINE_IDS`；所有 `reason` ≤30 字；同 tag 无重复
- [ ] **所有关键词 ≥2 字**（防止单字误命中回归）
- [ ] `sample_by_weights` 退化情形：全零权重 / 候选少于 n / NaN / 负数 / 权重不归一 / 无放回

`backend/tests/unit/test_routing_allergies.py`：

- [ ] `HARD_ALLERGY_CONFLICTS` keys ⊆ `CUISINE_IDS`、values ⊆ `ALLERGY_VALUES`
- [ ] `zero_out_conflicts` 不修改入参（不可变性）

### 集成测试

- [ ] `test_main_router_integration.py`：模拟完整 `AgentState` 流转，验证 `selected_cuisines` 后续被菜系 Node 消费

### 端到端（Playwright）

- [ ] 不直接测；由 F004 覆盖
