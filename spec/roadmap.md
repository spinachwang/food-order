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

- [~] **F001** 用户偏好可 CRUD（PUT / GET 返回符合契约）—— 代码已落地（[F001 §3.5](../../spec/features/F001-user-preferences.md) + commit 48b86dc），但 `test_preferences_service.py` 7 处 ERROR（依赖 MySQL），integration 尚未在本机跑通
- [~] **F002** 主 Agent 可基于用户消息 + 偏好路由到 1～3 个菜系专家 —— `route.py` 节点已落地；mypy 报 graph.py `add_node` 重载不匹配，待修
- [x] **F003** 14 菜系专家均遵循统一契约（Node 接口 / 输入输出 / prompt 模板）
- [x] **F004** LangGraph 工作流可端到端跑通：从用户消息 → 推荐（骨架，F030/F031/F040 占位 stub）

### 菜系覆盖

- [~] **F010–F024** 14 个菜系专家均有独立 spec + 对应 Node 实现 —— spec 14/14 ✅、stub 14/14 ✅、测试 14/14 ✅，但 mypy 报 14 处 `default_location` 类型不匹配，待修

### 高德 MCP

- [~] **F030** 餐厅搜索可返回 ≥3 家符合条件的餐厅 —— `search_restaurants.py` + 测试已落地；mypy + ruff 报错待修
- [~] **F031** 天气查询可返回当前温度 / 天气状况 / 降水概率 —— `fetch_weather.py` + 测试已落地；mypy + ruff 报错待修

### 总结与推荐

- [~] **F040** 总结 Agent 输出包含：推荐餐厅 / 是否外卖 / 原因 / 备选 ≥2 个 —— `summarize.py` 已落地；mypy + ruff 报错待修

### Web 聊天壳

- [x] **F050** 前端聊天窗口可发起对话并流式渲染最终推荐

### 质量

- [~] **后端测试覆盖率 ≥ 80%** —— `pytest backend/tests/unit` 实测 **87.39%**（831 passed / 3 failed / 7 errors），超过 80% 门槛；integration tests 因本机无 MySQL 未跑
- [!] **端到端 1 个 happy path（Playwright）** —— `playwright.config.ts` + 4 个 spec 在位（`homepage.spec.ts` / `address_picker.spec.ts` / `address_geolocation.spec.ts` / `address_compat.spec.ts`），但本轮未启动后端 + MySQL，未跑通
- [ ] **后端 mypy --strict 通过** —— 实测 **65 errors in 30 files**：14 处 `default_location` 类型不匹配（test fixture 仍用旧 str）、graph.py `add_node` 重载不匹配、若干其他
- [ ] **前端 ESLint + Prettier 通过** —— **ESLint 配置文件缺失**（`frontend/` 下无 `.eslintrc*` 也无 `eslint.config.js`），`pnpm lint` 无法执行；这是项目基础设施缺口，先于代码 bug

---

## 🧪 测试基线（2026-09-09）

> 下次跑测试以此为锚点对比；任何"修复了 X 问题"应在此记录差异。

### 后端

| 工具 | 命令 | 结果 |
|---|---|---|
| pytest（unit only） | `python -m pytest backend/tests/unit -q` | **831 passed / 3 failed / 7 errors / 87.39% coverage** |
| pytest（unit + coverage gate） | `python -m pytest backend/tests/unit` | 覆盖率 **87.39% ≥ 80% ✅** |
| ruff check | `python -m ruff check backend` | **238 errors**：RUF002（107，docstring 含全角符号）/ RUF003（117，comment 含全角符号）/ RUF022（4）/ N802（2）/ UP037（2）/ I001（2）/ F401（2）/ SIM103（1）/ RUF100（1） |
| mypy（strict 隐含） | `python -m mypy backend --no-incremental` | **65 errors in 30 files** |
| pytest（integration） | `python -m pytest backend/tests/integration` | **本机无 MySQL，未跑** |

### 前端

| 工具 | 命令 | 结果 |
|---|---|---|
| vitest | `pnpm exec vitest run` | **25 files / 197 tests passed**（11.75s） |
| typecheck（tsc -b） | `pnpm typecheck` | **3 errors**：`StructuredAddress` 测试 fixture 缺 `longitude` / `latitude`（`ContextStrip.test.tsx`、`api-client.test.ts`、`formatAddressSummary.test.ts`） |
| eslint | `pnpm lint` | **❌ ESLint config 文件缺失**（`frontend/.eslintrc*` / `eslint.config.js` 均无）；工具缺失，先于代码 bug |
| playwright | `pnpm exec playwright test` | **❌ 本轮未跑**（需先启动 MySQL + 后端 + 前端） |

### 已识别的优先修复项（按性价比排序）

1. **新增 `frontend/eslint.config.js`**（最小修复，pnpm lint 才能跑）
2. **修 mypy `default_location` 14 处不一致**（test fixture 与 spec/data-model.md §user_preferences 对齐；更新到 JSON dict）
3. **修 mypy `graph.py add_node` 重载**（graph.py:94-100；用 `functools.partial` 或 `@logged_node` 返回 Callable 而不是 object）
4. **修 ruff RUF002/RUF003 全角符号**（237 条；可考虑在 ruff.toml 加 `[ruff.lint] preview = true` + `allowed-confusables` 或禁用 RUF002/RUF003）
5. **修 vitest 测试 fixture 缺 `longitude`/`latitude`**（3 处 TS 错误）
6. **起 MySQL 后跑 integration tests**（解锁 F001 service ERROR + 80% 全量覆盖率确认）

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