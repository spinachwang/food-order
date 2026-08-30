# roadmap.md — 里程碑

| 里程碑 | 范围 | 状态 |
|---|---|---|
| **M0** | 骨架 — FastAPI `/healthz` + Vite 默认页 + spec 目录 + CLAUDE.md 落定 | ◀ 当前 |
| **M1 Agent MVP** | LangGraph 多 Agent + 14 菜系专家 + 高德 MCP + Web 聊天壳 + 用户偏好 | 未开始 |
| M2 | 体验增强（登录态、历史记录、收藏夹） | 未开始 |
| M3 | 商业化（推荐准确率看板、多城市、第三方外卖深链接） | 未开始 |

## M0 验收清单

- [x] 仓库根目录有 `CLAUDE.md` / `README.md` / `.env.example` / `.gitignore`
- [x] `spec/` 目录占位文档齐备
- [x] `backend/` FastAPI 骨架可启动并返回 `/healthz`
- [x] `frontend/` Vite + React 默认页可访问
- [x] 至少 1 个后端 smoke 测试（`test_healthz`）

## M1 Agent MVP 验收清单

> 每条都能映射到 F-ID；详见 [features.md](features.md)

### 基础设施

- [ ] **F001** 用户偏好可 CRUD（PUT / GET 返回符合契约）
- [ ] **F002** 主 Agent 可基于用户消息 + 偏好路由到 1～3 个菜系专家
- [ ] **F003** 14 菜系专家均遵循统一契约（Node 接口 / 输入输出 / prompt 模板）
- [ ] **F021** LangGraph 工作流可端到端跑通：从用户消息 → 推荐

### 菜系覆盖

- [ ] **F010–F024** 14 个菜系专家均有独立 spec + 对应 Node 实现

### 高德 MCP

- [ ] **F030** 餐厅搜索可返回 ≥3 家符合条件的餐厅
- [ ] **F031** 天气查询可返回当前温度 / 天气状况 / 降水概率

### 总结与推荐

- [ ] **F040** 总结 Agent 输出包含：推荐餐厅 / 是否外卖 / 原因 / 备选 ≥2 个

### Web 聊天壳

- [x] **F050** 前端聊天窗口可发起对话并流式渲染最终推荐

### 质量

- [ ] 后端测试覆盖率 ≥ 80%（pytest + httpx）
- [ ] 端到端 1 个 happy path（Playwright）：用户输入 → 流式输出 → 推荐卡片渲染（M1 不含反馈回写）
- [ ] 后端 mypy --strict 通过
- [ ] 前端 ESLint + Prettier 通过

## [REPLACED] 原 M1 范围（已被 ADR 0002 取代）

- [REPLACED] 原 M1 Sprint 1：鉴权 + 店铺 / 菜单 / 订单 CRUD + MySQL + Alembic
- [REPLACED] 原 M1 Sprint 2：顾客端流程串联 + 沙箱支付
- [REPLACED] 原 M2：微信小程序 + 实时订单 + 配送配置
- [REPLACED] 原 M3：优惠券 / 会员 / 看板 / 第三方配送

## 技术债 / 待办

- 高德 MCP 服务配置（key 放在 `.env` 的 `AMAP_API_KEY`）
- LangGraph 版本锁定（默认 0.2+ 稳定版）
- 是否引入 Redis 做短期对话缓存（M2 再说）