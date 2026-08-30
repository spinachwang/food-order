# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> 本仓库由 **SDD + TDD + Git** 驱动：先在 `spec/` 写规格，再写测试，最后实现。所有破坏性 git 操作均被全局禁用。

---

## 项目概述

`food-order` 是一个**餐饮点单 / 外卖**方向的 Web 应用（具体业务范围在 [`spec/product.md`](spec/product.md) 落定）。本仓库当前为 M0 — 骨架阶段。

## 技术栈（固定）

| 层 | 选型 | 说明 |
|---|---|---|
| 前端 | Vite + **React 18** + TypeScript | 状态管理用 Zustand；路由用 React Router v6；HTTP 用 TanStack Query |
| 后端 | **FastAPI** + Python 3.11+ | ORM 用 SQLModel（SQLAlchemy 2.0 + Pydantic v2）；迁移用 Alembic |
| 数据库 | **MySQL 8** | 连接信息从 `.env` 读取 |
| 鉴权 | 自建 JWT (HS256) | `PyJWT` 签发，登录态走 HttpOnly cookie |
| Python 环境 | **conda env `food-order`** | 全局规则强制 |
| Node 环境 | **pnpm**（不是 npm / yarn） | 通过 `packageManager` 字段在 `package.json` 锁定 |
| 测试 (后端) | pytest + httpx + pytest-asyncio | 覆盖率门槛 ≥ 80% |
| 测试 (前端) | Vitest + Testing Library + Playwright (E2E) | 覆盖率门槛 ≥ 80% |
| Lint (后端) | ruff (check + format) + mypy | |
| Lint (前端) | ESLint + Prettier | |
| CI（未来） | GitHub Actions | 在 `feat/ci-*` 分支引入 |

> 任何技术变更必须先更新本表与对应 `spec/adr/*.md`，否则不予合并。

---

## 目录结构（固定）

```
food-order/
├── CLAUDE.md                  # 本文件（仓库级指引）
├── README.md                  # 对外的项目说明
├── .env.example               # 环境变量模板
├── .gitignore
│
├── spec/                      # ⭐ SDD 单一事实来源
│   ├── product.md             # 产品目标、用户画像、核心场景
│   ├── features.md            # 功能列表与优先级
│   ├── api.md                 # REST 接口契约
│   ├── data-model.md          # 数据表 / 字段 / 约束
│   ├── roadmap.md             # 里程碑
│   └── adr/                   # 架构决策记录（每条变更一条 ADR）
│
├── backend/                   # FastAPI 后端
│   ├── pyproject.toml
│   ├── requirements.txt
│   ├── alembic.ini
│   ├── migrations/            # Alembic 迁移脚本
│   ├── app/
│   │   ├── main.py            # FastAPI 入口（CORS、middleware）
│   │   ├── core/              # 配置、安全、依赖注入、数据库引擎
│   │   │   ├── config.py
│   │   │   ├── security.py
│   │   │   └── db.py
│   │   ├── api/
│   │   │   └── v1/            # 路由（按业务领域拆分）
│   │   │       ├── auth.py
│   │   │       ├── orders.py
│   │   │       └── ...
│   │   ├── models/            # SQLModel 数据模型（与表一一对应）
│   │   ├── schemas/           # Pydantic 请求/响应模型
│   │   ├── services/          # 业务逻辑（订单、支付、库存……）
│   │   └── utils/
│   └── tests/
│       ├── conftest.py
│       ├── unit/
│       └── integration/
│
├── frontend/                  # Vite + React 前端
│   ├── package.json           # 锁定 pnpm
│   ├── pnpm-lock.yaml
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── index.html
│   ├── public/
│   └── src/
│       ├── main.tsx
│       ├── App.tsx
│       ├── routes/            # 路由级页面
│       ├── components/        # 通用组件
│       ├── features/          # 按业务领域组织（cart / order / shop ...）
│       │   └── <feature>/
│       │       ├── api.ts
│       │       ├── store.ts
│       │       ├── components/
│       │       └── hooks/
│       ├── stores/            # 全局 Zustand stores
│       ├── lib/               # API 客户端、工具
│       ├── types/             # 共享类型
│       └── styles/            # 全局样式 / tokens
│
├── docs/                      # 工程文档（非规格）
│   ├── local-dev.md           # 本地开发环境搭建
│   └── deployment.md          # 部署流程（M2+ 再写）
│
└── scripts/                   # 一次性脚本（数据迁移、种子数据……）
```

**约束：**
- 后端按 `routers / services / models / schemas` 分层；**禁止**在 router 内直接拼 SQL 或调 ORM。
- 前端按 **feature** 切片而非按文件类型；跨 feature 复用才上提 `components/`。
- 函数 < 50 行，文件 < 800 行，嵌套 < 4 层（继承全局规则）。

---

## 代码风格（固定）

### Python
- 遵循 **PEP 8**，由 `ruff` 自动执行；行宽 100。
- 类型注解**强制**（公开函数 / 方法必须有返回类型）；`mypy --strict` 视模块开启。
- 优先 dataclass / Pydantic / SQLModel；**避免裸 dict 传递**。
- **不可变优先**：能返回新对象就不就地变更。
- 错误显式处理：业务异常用自定义 `DomainError` 体系；底层异常在 service 层捕获并重抛。
- 日志用 `logging.getLogger(__name__)`；禁止 `print()` 调试语句混入代码。

### TypeScript / React
- ESLint + Prettier；React 函数组件 + Hooks。
- Props 用 `interface` 而非 `type`（除非联合类型）。
- 命名：组件 PascalCase，hook `use*`，普通函数 camelCase，常量 `UPPER_SNAKE_CASE`。
- 副作用统一在 hook / event handler 中；组件本身保持纯渲染。
- API 调用放 `features/<x>/api.ts`，通过 TanStack Query 暴露 hooks。

### 共用
- 文件 < 800 行，函数 < 50 行，嵌套 < 4 层。
- 早返回替代深层 if/else。
- 任何"魔法数字"提取为命名常量。
- 所有密钥从 `.env` 读取，**禁止**硬编码；启动时校验必需 env 存在。

---

## 开发方法论

### 1. SDD — 规格驱动开发

**`spec/` 是单一事实来源（SSOT）**，CLAUDE.md 与代码不得与之冲突。

| 阶段 | 动作 |
|---|---|
| 收到需求 | 在 `spec/features.md` 增加条目（用户故事 + 验收清单） |
| 设计 API | 在 `spec/api.md` 写路径、请求/响应 schema、错误码 |
| 设计数据 | 在 `spec/data-model.md` 写表结构、约束、索引 |
| 架构变更 | 在 `spec/adr/NNNN-<title>.md` 用 MADR 模板记录决策 |
| 实现对齐 | 代码严格遵循 spec；不一致时**先更新 spec，再改代码** |
| PR 评审 | spec 与 code 一起 review；不允许"暗改" |

**禁止凭空实现**：需求不在 `spec/` 中时，先引导用户补 spec。

### 2. TDD — 测试驱动开发

每个功能 / bug 修复必须按 **RED → GREEN → IMPROVE** 循环：

1. **RED** — 先写**会失败**的测试（单元 + 集成），命名 `test_<行为>_<条件>_<期望>`
2. **GREEN** — 写最小实现让测试通过
3. **IMPROVE** — 重构，保持测试绿，覆盖率不下降

- **覆盖率门槛：≥ 80%**（行 + 分支，按模块统计）
- 测试结构 AAA（Arrange / Act / Assert）
- 修复 bug 同样先写能复现的失败测试
- 主动使用 `tdd-guide` agent 协助

### 3. Git 工作流

#### 分支策略

| 分支前缀 | 用途 | 来源 | 合并目标 |
|---|---|---|---|
| `main` | 稳定分支，受保护 | — | 仅接受 squash merge 来自 PR |
| `feat/*` | 新功能 | `spec/features.md` 中的一项 | `main` |
| `fix/*` | Bug 修复 | issue | `main` |
| `docs/*` | 仅文档 / spec | — | `main` |
| `refactor/*` | 不改行为的重构 | — | `main` |
| `chore/*` | 工具链 / 依赖 / CI | — | `main` |

#### 提交规范（Conventional Commits）

```
<type>: <description>

[optional body]
[optional footer]
```

- **type 保持英文**（`feat` / `fix` / `refactor` / `docs` / `test` / `chore` / `perf` / `ci`）以兼容 commitlint / semantic-release
- **标题与正文使用中文** 说明动机与权衡
- 一个 commit 只做一件事；PR 内的多个 feat 拆多个 commit

#### PR 流程

1. 从分支推到 origin，发 PR（含动机、改动摘要、测试计划 TODO）
2. CI 全绿才能合并
3. 评审至少 1 人；触及鉴权 / 支付 / 数据模型时需 2 人
4. squash merge，commit message 取 PR 标题

## 环境与凭据

- 根目录 `.env` 存放真实凭据；模板见 [`.env.example`](.env.example)
- `.env` 必须加入 `.gitignore`，**绝不**提交
- 所有密钥从环境变量读取，**绝不**硬编码到任何文件
- 启动时校验必需 env 存在；缺失即 fail-fast

---

## 安全基线

- 所有用户输入在后端用 Pydantic 做白名单校验；前端 zod 二次校验
- SQL 全部走 ORM 参数化；**禁止** f-string 拼 SQL
- 密码 `bcrypt` / `argon2` 哈希；JWT secret ≥ 256 bit
- 启用必要 HTTP 安全头（CORS、HSTS、X-Content-Type-Options、Rate Limiting）
- 文件上传做 MIME + 体积 + 扩展名三重校验
- 启用 HTTPS-only cookie；SameSite=Lax

---

## 快速上手（M0）

```bash
# 1. 后端
conda create -n food-order python=3.11 -y
conda run -n food-order pip install -r backend/requirements.txt
conda run -n food-order uvicorn backend.app.main:app --reload --port 8000

# 2. 前端
cd frontend
pnpm install
pnpm dev
```

打开 http://localhost:5173/ 看到 Vite 默认页 → 骨架就绪。

---

## 维护说明（给未来的 Claude）

- 修改本文件前，先在 `spec/adr/` 写一条 ADR 说明"为什么改"
- 不要在本文件重复 `spec/` 内容；只引用、不抄录
- 任何新增工具链 / 命令必须同步更新本文件与 README
- 不确定时**先问**，不要替用户做技术决策