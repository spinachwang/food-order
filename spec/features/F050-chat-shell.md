# F050 — Web 聊天壳（前端单页应用）

> **状态**：[ ] 未开始
> **所属里程碑**：M1 Agent MVP
> **依赖**：[F001](F001-user-preferences.md)、[F002](F002-main-agent-router.md)、[F003](F003-cuisine-expert-contract.md)、[F004](F004-langgraph-workflow.md)、[F030](F030-amap-restaurant-search.md)、[F031](F031-amap-weather.md)、[F040](F040-summary-agent.md)
> **被依赖**：无（M1 的 UI 收口；后续 M2 历史/收藏夹/登录态 会复用本 spec 的页面骨架）

> 本 spec 的视觉基线来自 [prototype/index.html](../../prototype/index.html)（Editorial / Warm Menu 风格 OKLch 单文件原型，Aug 30 写入）。**prototype 仅作参考**，不引入、不修改；本 spec 是 React 实现的唯一依据。

## 1. 用户故事

作为办公室打工人，我希望打开网页就能看到一个**单页聊天壳**：

1. 一眼看到当前时间、当前位置、天气，agent 已经知道我的上下文；
2. 通过 chip / 心情 / 滑杆快速调整偏好（不写也行），随时"重置"或套用"下雨天预设"；
3. 点击「给我推荐」或「随便」后，**流式**看到 agent 思考过程（路由到哪些菜系、调用了哪些工具、排序思路）；
4. 最终看到一张**主推卡片** + 两张**备选卡**，知道距离 / 人均 / 匹配度 / 标签；
5. 能"就它了·导航去吃" / "复制链接" / "存一下" 三种动作收尾。

> 来源：[product.md § 3 核心场景](../product.md) + [prototype/index.html](../../prototype/index.html) hero 文案。

## 2. 验收清单

### 2.1 页面骨架（来自 prototype `data-od-id`）

- [ ] **`topbar`** 顶栏：品牌标识（"午饭吃什么"）+ 主导航（"推荐"高亮）+ 实时时钟（HH:MM · 周X）+ 用户头像（首字母 Z 暂定）
- [ ] **`hero`** 主欢迎区：左侧问候语（按时段切换"早上好/中午好/下午好/晚上好 张工 👋"）+ 主标题（"今天中午，**吃点好的**别再吃昨天那家了"）+ 一句副文案；右侧 `hero-meta` 卡片（午餐窗口 11:50–13:30 + Agent 在线状态点）
- [ ] **`context`** 上下文条：两张并排卡片——左"当前位置"（地址 + 副地址 + `addr-edit` 切换链接）；右"天气·影响选餐"（温度 28° + 体感 + weather-tag 三连：有雨概率 60% / 建议近一点 / 暖食 +1 分）
- [ ] **`prefs`** 偏好面板（`section-head` 含 `reset-prefs` + `preset-rainy` 两个按钮）：
  - [ ] 口味多选 chips（中餐 / 日料 / 西餐 / 面食 / 米饭 / 轻食沙拉 / 粉米线 / 麻辣烫 / 汉堡快餐），多选
  - [ ] 温度三选一 toggle（冰镇 / 常温 / 热乎乎的），单选
  - [ ] 心情五选一 mood（🥱凑合吃 / 🍱想吃好点 / 🧘要健康 / 🌶️想暴辣 / 🫶想治愈），单选
  - [ ] 距离 + 预算两个 slider（步行 0–100 映射 0–20 min；预算 0–100 映射 ¥20–¥80），实时显示
  - [ ] 忌口多选 chips（香菜 / 葱 / 辣 / 内脏 / 生海鲜 / 牛肉 / 油炸 / 乳制品）
  - [ ] CTA 行：左侧"N 项偏好"实时统计；右侧 `surprise`（🤷 随便）+ `ask-agent`（给我推荐 →）
- [ ] **`reco`** 推荐区（两列布局，移动端 1 列）：
  - [ ] `reco-status` 状态条（绿色脉冲点 + "Agent · 实时分析中" + 右侧置信度百分比）
  - [ ] **`reco-main`** 主推卡片（`reco-hero`）：左侧 `visual`（径向渐变 + 中央"碗"插画 + 玻璃态徽章 "No.1 · 今日主推"）；右侧 `info`（eyebrow + h3 餐厅名 + 斜体 dish 副标题 + desc 描述 + tags 标签条 + 三栏 stats：距离/人均/匹配度 + 三个动作按钮 `go-eat` / `share-eat` / `save-eat`）
  - [ ] **`reco-alt`** 备选网格（两列 alt-1 + alt-2，每张含 num/标题/斜体菜名/价格 + 距离 + 历史标签）
  - [ ] **`thinking`** 思考流 aside（粘性定位，桌面端右侧）：步骤列表（读取偏好与忌口 → 天气信号注入 → 拉取半径 800m 内 47 家店 → 排除 38 家 → 重排序·输出 Top 3），每步带 marker 数字 + strong 标题 + em 元数据
- [ ] **`foot`** 底栏：左"午饭吃什么 · Lunch Agent v0.3 · 让打工牛马不再为中午吃什么内耗"；右"数据：高德 POI · 实时排队 · 你的过去 30 天"

### 2.2 设计系统基线（来自 prototype `:root` CSS 变量）

- [ ] 字体三套：`Fraunces`（标题 serif）、`Inter`（正文 sans）、`JetBrains Mono`（数字 / 时间 / eyebrow）
- [ ] OKLch 配色 token：bg 餐巾纸奶白 / surface 卡片纯白 / surface-warm 浅米托盘 / fg 油墨黑 / accent 暖橙焦点（`#E55934` 系）/ accent-deep / accent-soft / green 健康标签 / gold 价格徽章
- [ ] 圆角 token：`--r-sm 6px` / `--r-md 12px` / `--r-lg 20px` / `--r-xl 28px`
- [ ] 阴影 token：`--shadow-1` 轻卡片 / `--shadow-2` 中卡片 / `--shadow-pop` 暖橙浮起（仅用于主 CTA）
- [ ] 焦点态：所有交互元素 `focus-visible` 时 2px accent 描边 + 3px offset
- [ ] 字号：`h1 clamp(40px, 5.5vw, 72px)` / `h2 clamp(28px, 3vw, 40px)` / 正文 15px / 行高 1.55

### 2.3 SSE 事件 → UI 渲染映射（来自 F004 §4）

| SSE event | 触发节点 | 渲染动作 |
|---|---|---|
| `cuisine_selected` | F002 router | `thinking` 追加步骤 1："已路由到 N 个菜系：xxx / yyy" |
| `cuisine_result` | F003 各 cuisine Node | `thinking` 追加步骤 N："川菜专家结论：xxx · 关键词：…" |
| `restaurant_found` | F030 search | `thinking` 追加步骤 N+1："拉取 47 家店 · 排除 38 家"；同时为该 cuisine_id 准备 reco 数据 |
| `weather` | F031 fetch | `context.weather-card` 数值 + tags 实时刷新 |
| `recommendation` | F040 summarize | `reco-status` 切为"Agent · 推荐已更新" + `reco-main` 全量替换 + `reco-alt` 替换 |
| `error` | 任一 Node | `thinking` 追加红色错误步骤 + 主区显示降级空态（见 §5） |
| `done` | F004 收尾 | `reco-status` 停止脉冲；按钮恢复可用 |

### 2.4 交互按钮契约

| `data-od-id` | 触发行为 | 备注 |
|---|---|---|
| `ask-agent` | 调 F004 `POST /api/v1/agent/chat`（body: `{message, session_id?, location_override?}`）→ 开启 SSE 监听 | CTA 主按钮；点击后 1.2s 内 `reco-status` 必更新（对应 SSE `cuisine_selected`） |
| `surprise` | **M1 简化**：滚动到 `reco` 锚点 + 显示缓存的默认推荐（不调 SSE、不发消息） | M2 升级为发 `surprise_me` 走完整流（F050 §8 #1） |
| `go-eat` | 仅调起高德地图 web URL `https://uri.amap.com/marker?position=lng,lat&name=xxx`（新窗口打开） | 不接外卖 API，仅导航；**M1 不写 feedback** |
| `share-eat` | 复制"餐厅名 + 距离 + 高德 marker URL"到剪贴板；toast 反馈"已复制" | 纯前端（F050 §8 #3 决议） |
| `save-eat` | **M1 不存**：仅本地切按钮文案为"已收藏" + toast 提示；M2 接 `POST /api/v1/feedback` 后改为真存 | 见 §8 #2 决议 2026-08-30 修订 |
| `reset-prefs` | 把 prefs 全部恢复默认（口味全空 / 温度=`"hot"` / 心情=想吃好点 / 距离=35 / 预算=55）→ 调 F001 `PUT /api/v1/preferences` 同步 | 本地立即生效 + 后端持久化 |
| `preset-rainy` | 一键套下雨天偏好：温度=`"hot"` / 心情=想治愈 / 距离=25；**不调后端**，仅本地 store | 用户点 `ask-agent` 时由 router 读 prefs 再计算（F050 §8 #4 决议） |
| `addr-edit` | **M1**：浏览器 `prompt()` 浮层输入地址 → 写入 `location_override`；**M2**：接高德选址组件 | 详见 [F030 高德 MCP 周边搜索](F030-amap-restaurant-search.md) |

### 2.5 响应式断点

- [ ] `≤1080px`：hero 改为单列；reco-wrap 改为单列；`thinking` 改为静态定位
- [ ] `≤720px`：顶栏导航隐藏；shell 内边距收紧；mood-row 改 3 列；reco-hero 改单列；alt-grid 改单列；CTA 行垂直堆叠

### 2.6 可访问性

- [ ] 所有 chip / toggle / mood 使用 `aria-pressed`；toggle-row / mood-row 用 `role="radiogroup"` + `aria-label`
- [ ] 滑杆有 `aria-label="步行距离"` / `aria-label="预算上限"`
- [ ] 配色对比度 ≥ WCAG AA（accent-deep on bg / fg on surface）
- [ ] 键盘可达：alt-card 可 `tabindex="0"`，Enter/Space 触发替换主推
- [ ] 偏好修改 → 主推荐变化（E2E 覆盖）

## 3. 偏好字段映射（前端 schema ↔ F001）

| prototype 控件 | F001 字段 | 备注 |
|---|---|---|
| 口味 chips（多选） | `cuisine_weights: dict[cuisine_id, 1.0]`（选中=1.0；未选=0.0；首次访问未选任何 = 全 0.5 默认） | M1 前端把 chip 折成"二元权重"，M2 再升级为连续滑杆 |
| 温度 toggle | `temperature_preference: Literal["cold","room","hot"]`（冰镇=`"cold"` / 常温=`"room"` / 热乎=`"hot"`） | F001 §3.4 / §4 新增字段（2026-08-30 §8 #6 决议） |
| 心情 mood | 不存 F001，仅本地会话级（Zustand 临时） | 心情是当下语境，不持久化（F050 §8 #8 决议） |
| 距离 slider | `location_radius_m: int`（M2 再加字段；M1 仅本地 store） | M1 可不存，仅会话级 |
| 预算 slider | `budget_lunch_max: Decimal` | slider 0–100 → ¥20–¥80 |
| 忌口 chips | `allergies: list[str]`（仅严格匹配 F001 §3.1 枚举的 chips 才上报后端） | 映射：`"生海鲜"`→`"shellfish"` / `"乳制品"`→`"dairy"` / `"油炸"`→`"fried_food"`（新增）。其他 chips（`香菜/葱/辣/内脏/牛肉`）属口味偏好而非过敏，**M1 仅本地会话级**，不入 F001；M2 视需求扩展 §3.1 枚举 |

## 4. 输入 / 输出（前端视角）

### 4.1 主动作：`ask-agent` 触发的 SSE 流

```typescript
// 客户端伪代码
const res = await fetch('/api/v1/agent/chat', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json', 'X-User-Id': <anon-uuid> },
  body: JSON.stringify({
    message: '今天想吃辣的',
    session_id?: string,
    location_override?: string,  // 来自 addr-edit
  }),
});
const reader = res.body.getReader();
const decoder = new TextDecoder();
// 事件循环按 F004 §4 表逐条处理：cuisine_selected → cuisine_result →
// restaurant_found → weather → recommendation → done
```

### 4.2 偏好读：`GET /api/v1/preferences`

- 不带 `X-User-Id` → 后端自动生成匿名 UUID 写入 cookie，前端缓存到 Zustand store
- 校验失败 → toast 提示并回滚到默认

### 4.3 偏好写：`PUT /api/v1/preferences`

- 触发时机：`reset-prefs` / `preset-rainy` 后用户点 `ask-agent` 之前（M1 简化：仅 reset 同步）
- 校验失败 → `INVALID_CUISINE_ID` / `INVALID_ALLERGY` / `INVALID_SPICE` / `INVALID_BUDGET`（F001 §6）

### 4.4 M1 不做 feedback

> `POST /api/v1/feedback` 端点与 `go-eat` / `save-eat` 的服务端反馈回写**延后到 M2**。M1 的 `save-eat` 仅切前端按钮文案 + toast，`go-eat` 仅跳转高德导航；均不发起后端请求。详见 §8 #2 决议 2026-08-30 修订。

## 5. 错误码与降级 UI

| code / 情形 | HTTP / SSE | UI 降级 |
|---|---|---|
| SSE 连接建立失败 | `network error` | `reco-status` 切为"网络断了·点此重试"；`ask-agent` 重新可点 |
| SSE 中途中断 | `done` 未到达 | `thinking` 末尾追加 "⚠️ 流式中断"；`reco-main` 显示空态卡"agent 还没说完" |
| `INVALID_CUISINE_ID` / `INVALID_ALLERGY` / `INVALID_SPICE` / `INVALID_BUDGET` | 400 | 红色 toast；prefs 回滚到上一次成功状态 |
| 后端 401 | 401 | **M1 不做登录**：后端不会返回 401；此行作为 M2 登录态引入后的预留 |
| 后端 5xx | 500 | 红色 toast"agent 累了，稍后再试"；按钮恢复可用 |
| `EMPTY_MESSAGE` SSE 事件 | 200 + error event | toast"请告诉我你想吃什么" |
| 高德搜索 0 结果 | `restaurant_found` 带空数组 | `reco-main` 显示"附近没找到合适的，试试调整距离/预算"；`reco-alt` 不渲染 |
| 天气失败 | `weather=null` | `context.weather-card` 显示"天气暂不可用·agent 按默认决策"；`recommendation` 仍正常输出（F040 用默认决策） |
| 单个菜系 Node 失败 | 该 cuisine 的 `cuisine_result` 缺失 | `thinking` 追加 "川菜专家暂不可用"；F040 跳过该菜系，其余正常 |

## 6. 数据 / 接口变更

### 不新增 API

F050 仅消费 F001 / F004 / F040 已定义的接口。**不**新增后端端点。

### 前端目录（预期，M1 落地时按 TDD 迭代）

```
frontend/src/
├── main.tsx
├── App.tsx                          # 单页根：直接渲染 <ChatShell />
├── features/
│   └── chat/
│       ├── api.ts                   # SSE fetch 封装 + TanStack Query hooks
│       ├── store.ts                 # Zustand：prefs / address / session_id
│       ├── components/
│       │   ├── TopBar.tsx
│       │   ├── Hero.tsx
│       │   ├── ContextStrip.tsx
│       │   ├── PreferencesPanel.tsx
│       │   ├── RecommendationCard.tsx
│       │   ├── AltCard.tsx
│       │   ├── ThinkingLog.tsx
│       │   ├── AddressEditPopover.tsx
│       │   └── Footer.tsx
│       └── hooks/
│           ├── useAgentStream.ts    # SSE 解析 + 事件分发
│           └── usePreferences.ts    # TanStack Query 包装 F001
├── stores/                          # 全局：device-id、theme（M2 用）
├── styles/
│   ├── tokens.css                   # ← 本 spec §2.2 的全部 CSS 变量（SSOT）
│   └── global.css
└── lib/
    ├── api-client.ts                # fetch 封装 + X-User-Id 自动注入
    └── sse.ts                       # 通用 SSE parser（Future M2 多会话用）
```

> 本 spec **不约束**具体组件文件名，只约定章节语义与 SSE 事件归属（见 §2.3）；React 落地时的组件拆分留给 TDD 阶段。

### 前端依赖

- `react` / `react-dom` 18（已在 [package.json](../../frontend/package.json)）
- `react-router-dom` 6（已声明，M1 单路由不实际使用）
- `@tanstack/react-query` 5（已声明；用于 F001 偏好缓存）
- `zustand`（已声明；用于 prefs / session_id 本地状态）
- 新增：`zod`（F001 schema 校验，防 400）

## 7. 测试计划

### 7.1 单元测试（Vitest + Testing Library）

- [ ] `TopBar.test.tsx`：时钟渲染格式；问候语按时段切换（mock `new Date()`）
- [ ] `Hero.test.tsx`：h1 含"吃点好的"em 标签；hero-meta 卡片显示午餐窗口
- [ ] `ContextStrip.test.tsx`：地址 + 天气两卡；addr-edit 触发回调
- [ ] `PreferencesPanel.test.tsx`：
  - chip 多选 toggle → `aria-pressed` 切换 + `updateCtaHint` 计数
  - toggle / mood 单选互斥
  - slider input → 显示值更新
  - `reset-prefs` 恢复默认值
  - `preset-rainy` 套用雨天偏好
- [ ] `RecommendationCard.test.tsx`：渲染 eyebrow / h3 / dish / desc / tags / 三栏 stats / 三个按钮
- [ ] `AltCard.test.tsx`：点击触发 `onPromote` 回调（替换主推）
- [ ] `ThinkingLog.test.tsx`：逐条 step 渲染，done 状态正确
- [ ] `useAgentStream.test.ts`：mock fetch + SSE reader，验证 6 类事件分发到对应 setter

### 7.2 集成测试

- [ ] `chat_flow.test.tsx`：mock `useAgentStream` 返回模拟事件序列 → 断言 UI 状态从 hero → thinking 追加 → reco-main 替换的完整链路

### 7.3 端到端（Playwright，`frontend/e2e/`）

- [ ] **`chat_recommendation.spec.ts`**（沿用 [F004 §7](F004-langgraph-workflow.md) 步骤）：
  1. `goto('/')`
  2. 点 `ask-agent`（不输入消息，使用默认 prefs）
  3. 等待 SSE 流：`cuisine_selected` → `cuisine_result` → `restaurant_found` → `weather` → `recommendation` → `done`
  4. 断言 `reco-main` 渲染含 headline + 餐厅名 + reason + 置信度 > 0
  5. 断言 `reco-alt` 渲染 ≥2 张
  7. 点 `save-eat` → 仅切按钮文案"已收藏" + toast（**不调后端**，M1 不做 feedback）
- [ ] **`preferences_flow.spec.ts`**：
  1. 点 chip"日料" → `aria-pressed="true"`
  2. 点 `ask-agent` → `cuisine_selected` 事件中包含 `japanese`
- [ ] **`error_degradation.spec.ts`**：
  1. mock 后端返回 5xx
  2. 点 `ask-agent` → toast"agent 累了"+ `reco-main` 显示空态卡
- [ ] **`responsive.spec.ts`**：分别在 1440 / 1024 / 768 / 375 viewport 截图，`reco-wrap` 列数符合 §2.5

### 7.4 视觉回归（Playwright screenshots）

- [ ] hero / prefs / reco / thinking 4 个关键区块在 1440 桌面 + 375 移动各截一张
- [ ] `ask-agent` 触发后 0ms / 600ms / 1200ms / 完成 各截一张（验证流式渲染节奏）

## 8. 已决议（2026-08-30 用户确认取代原待澄清问题）

> 原 §8 列出的 12 个待澄清问题已全部按本文档"建议"项落地。下表是决议快照，便于后续 review 时一眼对齐。

| # | 原问题 | 决议 | 落地位置 |
|---|---|---|---|
| 1 | `surprise` 行为 | **M1 简化**：滚动到 `reco` 锚点 + 显示缓存的默认推荐，**不调 SSE**、不发消息 | §2.4 按钮契约 |
| 2 | `save-eat` 是否真存 | **M1 不存**：仅切前端按钮文案 + toast；M2 接 `POST /api/v1/feedback` 后再真存 | §2.4 按钮契约（2026-08-30 修订） |
| 3 | `share-eat` 链接格式 | **高德 marker URL**：`https://uri.amap.com/marker?position=lng,lat&name=xxx` | §2.4 按钮契约 |
| 4 | `preset-rainy` 是否同步后端 | **否**：仅本地 store；下次 `ask-agent` 时由 router 读 prefs | §2.4 按钮契约 |
| 5 | `addr-edit` 实现 | **M1**：浏览器 `prompt()` + 写入 `location_override`；**M2**：接高德选址组件 | §2.4 按钮契约 |
| 6 | 温度字段语义错位 | **新增** `temperature_preference: Literal["cold","room","hot"]` 字段；`spice_tolerance` 恢复"辣度"原意 | [F001 §3.4](F001-user-preferences.md) + §4 TypedDict + §6 错误码 |
| 7 | "油炸" 不在 F001 枚举 | **新增** `"fried_food"` 到 F001 §3.1 ALLERGY_VALUES | [F001 §3.1](F001-user-preferences.md) |
| 8 | 心情持久化 | **不持久化**：仅本地会话级（Zustand 临时） | §3 偏好字段映射 |
| 9 | < 375px 移动端 | reco-stats 改为 1 列 + 水平 scroll | §2.5 响应式 |
| 10 | 暗色模式 | **M1 不做**（仅亮色 token） | §2.2 设计系统基线 |
| 11 | 国际化 | **M1 不做**（仅中文） | §1 用户故事 |
| 12 | `history` / `fav` 章节 | **M1 不渲染**（CSS 留位，M2 接 `/history` `/favorites` API） | §6 数据/接口变更（不新增 M1 端点） |

<details>
<summary>📜 原待澄清问题（已折叠，仅供历史追溯）</summary>

1. **`surprise` 按钮的精确行为**：prototype 是平滑滚动到 reco 节（无 agent 重算）。是否要：(a) 保持当前行为，滚动 + 显示缓存的默认推荐（M1 简化） / (b) 改为发送 `surprise_me` 消息走完整 SSE 流（更"agent"）。**已选 (a)**。
2. **`save-eat` 是否真的调 F001 `/feedback`**：prototype 当前是**纯前端**切按钮文案。**M1 决议（2026-08-30 修订）：不存**——M1 不做 feedback，M2 接 `POST /api/v1/feedback` 后再切到真存。
3. **`share-eat` 复制的链接格式**：高德 marker URL vs 经纬度 JSON。**已选：高德 marker URL**。
4. **`preset-rainy` 是否调 `PUT /api/v1/preferences`**：**已选：否**（仅本地 store）。
5. **`addr-edit` 的实现**：M1 用浏览器 `prompt()` 占位（最简），M2 接高德选址组件。**已选：M1 prompt**。
6. **温度 toggle 与 `spice_tolerance` 字段语义错位**：复用字段语义有损 vs 新增 `temperature_preference` 字段。**已选：新增字段**（详见决议表 #6）。
7. **忌口 chips"油炸"不在 F001 §3.1 枚举**：F001 §3.1 增加 `"fried_food"` 或前端用 `allergies` 自由文本字段。**已选：F001 §3.1 增加 `"fried_food"`**（详见决议表 #7）。
8. **心情是否持久化**：**已选：否**（仅本地 store 临时）。
9. **移动端 < 375px**：**已选：改为 1 列 + 水平 scroll**。
10. **暗色模式**：**已选：M1 不做**（仅亮色）。
11. **国际化**：**已选：M1 不做**（仅中文）。
12. **`history` / `fav` 两个章节是否纳入 M1**：prototype 的 CSS 已定义但**未在 DOM 渲染**。**已选：(a) 不渲染，M2 接 API**。

</details>

## 9. 关联文档

- 视觉基线：[prototype/index.html](../../prototype/index.html)（1237 行，Aug 30 写入，**只读参考**）
- SSE 事件来源：[F004 §4 流式 SSE 事件映射](F004-langgraph-workflow.md)
- 偏好 schema：[F001 §3 偏好字段定义](F001-user-preferences.md)
- 推荐决策：[F040 §3 决策矩阵](F040-summary-agent.md)
- 菜系路由：[F002 主 Agent router](F002-main-agent-router.md) + [F003 菜系专家通用契约](F003-cuisine-expert-contract.md)
- 餐厅搜索：[F030 高德 MCP 周边搜索](F030-amap-restaurant-search.md)
- 天气查询：[F031 高德 MCP 天气查询](F031-amap-weather.md)
- M1 验收：[roadmap.md § M1 Web 聊天壳](../roadmap.md)

## 10. 变更日志

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-08-30 | 0.1 | 初稿：从 prototype 沉淀章节结构 + 设计 token + SSE 映射 + 8 按钮契约 |
| 2026-08-30 | 0.2 | §8 待澄清问题全部决议（用户确认）；§2.4 按钮契约具体化；§3 偏好映射按新 schema 重写；同步更新 [F001 §3.1](../features/F001-user-preferences.md)（新增 `fried_food`）、[F001 §3.4](../features/F001-user-preferences.md)（新增 `temperature_preference`）、[F001 §4 TypedDict](../features/F001-user-preferences.md)、[F001 §6 错误码](../features/F001-user-preferences.md)（新增 `INVALID_TEMPERATURE`；顺手修复 `INVALID_ALLERGY` 误引 §3.2 → §3.1） |
| 2026-08-30 | 0.3 | **M1 不做 feedback**：移除 §2.4 中 `go-eat` / `save-eat` 的 `/feedback` 调用，§4.4 改写为占位，目录结构移除 `useFeedback.ts`，§8 #2 决议改为"不存"；§5 401 行改为 M2 预留 |
| 2026-08-30 | 0.4 | **M1 不做登录**：§5 401 行更新为"M1 后端不会返回 401" |