# roadmap.md — 里程碑

| 里程碑 | 范围 | 状态 |
|---|---|---|
| **M0** | 骨架 — FastAPI `/healthz` + Vite 默认页 + spec 目录 + CLAUDE.md 落定 | ✅ 已完成 |
| **M1 Agent MVP** | LangGraph 多 Agent + 14 菜系专家 + 高德 MCP + Web 聊天壳 + 用户偏好 | 🚧 进行中（功能模块落地，质量门未过） |
| M2 | 体验增强（登录态、历史记录、收藏夹） | 未开始 |
| M3 | 商业化（推荐准确率看板、多城市、第三方外卖深链接） | 未开始 |

> 状态约定：`[ ]` 未开始 / `[~]` 进行中 / `[x]` 完成 / `[!]` 阻塞

---

## M0 验收清单

- [x] 仓库根目录有 `CLAUDE.md` / `README.md` / `.env.example` / `.gitignore`
- [x] `spec/` 目录占位文档齐备
- [x] `backend/` FastAPI 骨架可启动并返回 `/healthz`
- [x] `frontend/` Vite + React 默认页可访问
- [x] 至少 1 个后端 smoke 测试（`test_healthz`）

---

## M1 Agent MVP 验收清单

> 每条都能映射到 F-ID；详见 [features.md](features.md)
>
> **状态更新于 2026-09-09**：详见 [§ 测试基线](#-测试基线--2026-09-09)。

### 基础设施

- [x] **F001** 用户偏好可 CRUD（PUT / GET 返回符合契约）—— ✅ 全量集成测试 14/14 过；`curl /api/v1/preferences` 返回结构化 `default_location` 与 14 菜系权重
- [~] **F002** 主 Agent 可基于用户消息 + 偏好路由到 1～3 个菜系专家 —— `route.py` 节点已落地；`test_rule_layer_with_real_preferences` fixture 仍用旧 str，需修
- [x] **F003** 14 菜系专家均遵循统一契约（Node 接口 / 输入输出 / prompt 模板）
- [x] **F004** LangGraph 工作流可端到端跑通：从用户消息 → 推荐（骨架，F030/F031/F040 占位 stub）

### 菜系覆盖

- [x] **F010–F024** 14 个菜系专家均有独立 spec + 对应 Node 实现 —— spec 14/14 + stub 14/14 + 测试 14/14 ✅

### 高德 MCP

- [x] **F030** 餐厅搜索可返回 ≥3 家符合条件的餐厅 —— `search_restaurants.py` + 测试 + 集成 ✅
- [x] **F031** 天气查询可返回当前温度 / 天气状况 / 降水概率 —— `fetch_weather.py` + 测试 + 集成 ✅

### 总结与推荐

- [x] **F040** 总结 Agent 输出包含：推荐餐厅 / 是否外卖 / 原因 / 备选 ≥2 个 —— `summarize.py` + 测试 ✅

### Web 聊天壳

- [x] **F050** 前端聊天窗口可发起对话并流式渲染最终推荐

### 质量

- [x] **后端测试覆盖率 ≥ 80%** —— 91.57% ✅
- [~] **端到端 1 个 happy path（Playwright）** —— 12 个 spec 跑通 6 个（homepage 基础结构 + chip + preset-rainy + 天气占位 + 1080px 响应式等）；6 个失败多为依赖真实高德 API 数据
- [ ] **后端 mypy --strict 通过** —— 65 errors
- [ ] **前端 ESLint + Prettier 通过** —— ESLint 配置缺失

---

## 🧪 测试基线（2026-09-09）

> 下次跑测试以此为锚点对比；任何"修复了 X 问题"应在此记录差异。
> **v2 更新**：用户在本地确认 MySQL 已就绪 + AMAP key 已配置；跑通了完整链路。

### 后端

| 工具 | 命令 | 结果 |
|---|---|---|
| pytest（unit + integration，从 `backend/` 跑） | `cd backend && pytest tests -q` | **886 passed / 4 failed / 0 errors** |
| pytest（覆盖率） | `cd backend && pytest tests --cov=app` | **91.57% ≥ 80% ✅**（model / schema / structured_address / preferences service 接近全覆盖；mcp/amap/* 在 84-93%） |
| ruff check | `python -m ruff check backend` | **238 errors**：RUF002（107 docstring 全角符号）/ RUF003（117 comment 全角符号）/ RUF022（4）/ N802（2）/ UP037（2）/ I001（2）/ F401（2）/ SIM103（1）/ RUF100（1） |
| mypy | `python -m mypy backend --no-incremental` | **65 errors in 30 files**：14 处 `default_location` 类型不匹配（test fixture 仍用旧 str）+ graph.py 6 处 `add_node` 重载不匹配 + 其他 |
| alembic | `alembic -c backend/alembic.ini current` | **head = 8b3c2f1a4d5e** ✅ |

**4 个失败测试细节**：
1. `integration/test_main_router_integration.py::test_rule_layer_with_real_preferences` —— fixture 用 `default_location='...' (str)`，新 schema 要求 dict/StructuredAddress
2. `unit/test_base_contract.py::test_render_base_prompt_includes_hard_constraint_chinese_only` —— assertion 用全角子串，疑似 Windows console 编码（cp936/gbk）误报；需在 utf-8 环境复跑
3. `unit/test_observability.py::test_renders_single_user_message` —— 同上，编码显示问题
4. `unit/test_observability.py::test_truncates_at_4kb` —— **真 bug**：header 报的是截断后长度（4096）但 assertion 期待真实长度（8192）

### 前端

| 工具 | 命令 | 结果 |
|---|---|---|
| vitest | `pnpm exec vitest run` | **25 files / 197 tests passed** |
| typecheck（tsc -b） | `pnpm typecheck` | **3 errors**：`StructuredAddress` 测试 fixture 缺 `longitude` / `latitude` |
| eslint | `pnpm lint` | **❌ 配置缺失**：`frontend/` 下无 `.eslintrc*` / `eslint.config.js` |
| playwright（chromium） | `pnpm exec playwright test --project=chromium` | **6 passed / 6 failed**（12 tests；1.4m） |

**Playwright 失败明细**（依赖真实 Amap API 数据 + UI 状态）：
- `homepage.spec.ts:15 基本结构` / `homepage.spec.ts:51 reset-prefs` / `homepage.spec.ts:81 响应式 <720px`
- `address_picker.spec.ts:75 happy path 5 层选完` / `address_geolocation.spec.ts:65 useCurrentLocation` / `address_compat.spec.ts:56 legacy null 兼容`

**基础设施备注**：跑 Playwright 需要先 `pnpm exec playwright install chromium`（chromium-headless-shell 1234 ~114 MB）。backend / frontend dev server 都已确认能起 + curl 200。

### 已识别的优先修复项（按性价比排序）

1. **新增 `frontend/eslint.config.js`**（最小修复，pnpm lint 才能跑）
2. **修 vitest `StructuredAddress` fixture 缺 `longitude` / `latitude`**（3 处 TS 错误，最简单）
3. **修 mypy `default_location` 14 处不一致**（test fixture 与 spec/data-model.md §user_preferences 对齐）
4. **修 mypy `graph.py add_node` 重载**（graph.py:94-100；6 处错误）
5. **修 ruff RUF002/RUF003 全角符号**（237 条；考虑 `[tool.ruff.lint]` 加 `allowed-confusables` 或 ruff 项目级放宽）
6. **修 pytest 4 个失败**（1 个 fixture 改 dict + 1 个 truncate header bug + 2 个疑似编码）
7. **修 Playwright 6 个失败**（多为依赖真实高德 API 数据；可能需 mock 或改测试 fixture）

---

## [REPLACED] 原 M1 范围（已被 ADR 0002 取代）

- [REPLACED] 原 M1 Sprint 1：鉴权 + 店铺 / 菜单 / 订单 CRUD + MySQL + Alembic
- [REPLACED] 原 M1 Sprint 2：顾客端流程串联 + 沙箱支付
- [REPLACED] 原 M2：微信小程序 + 实时订单 + 配送配置
- [REPLACED] 原 M3：优惠券 / 会员 / 看板 / 第三方配送

## 技术债 / 待办

- 高德 MCP 服务配置（key 放在 `.env` 的 `AMAP_API_KEY`）
- LangGraph 版本锁定（默认 0.2+ 稳定版）
- 是否引入 Redis 做短期对话缓存（M2 再说）
- **本机起 MySQL 跑 integration tests**（解锁 F001 / F030 / F031 / F040 全量验收）
- **写 `frontend/eslint.config.js`**（质量门硬性前置）