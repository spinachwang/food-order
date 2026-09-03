# food-order

> 餐饮点单 / 外卖方向 Web 应用。**当前阶段：M0 — 骨架**（仅 `/healthz` 可用）。

由 **SDD + TDD + Git** 驱动。完整规则见 [CLAUDE.md](CLAUDE.md)；产品 / 功能 / 数据 / 架构以 [`spec/`](spec/) 为单一事实来源（SSOT）。

---

## ⚡ 5 分钟启动

### 0. 前置依赖

| 工具 | 版本 | 备注 |
|---|---|---|
| conda / miniconda | ≥ 23 | 后端 Python 环境管理 |
| Node.js | ≥ 20 | 前端构建 |
| pnpm | ≥ 9 | 前端包管理（**不要**用 npm / yarn） |
| MySQL 8 | 8.x | **M1 才会用到**；M0 不需要 |

> Windows 用户确保 `conda` / `pnpm` 在 PATH 里。Git Bash 推荐用本文档里的命令。

### 1. 后端（终端 A）

```bash
# 创建并激活 conda 环境（一次性）
conda create -n food-order python=3.11 -y
conda run -n food-order pip install -r backend/requirements.txt

# 启动开发服务器（自动 reload）
cd d:/project/food-order/backend
conda activate food-order
uvicorn app.main:app --reload --port 8000
```

打开 http://localhost:8000/healthz 应返回 `{"status":"ok"}`，访问 http://localhost:8000/docs 看 Swagger UI。

### 2. 前端（终端 B）

```bash
cd frontend
pnpm install            # 第一次或 lockfile 变更时
pnpm dev                # 默认 http://localhost:5173/
```

### 3. 环境变量

```bash
cp .env.example .env    # 仓库根
# 编辑 .env，至少填一个 JWT_SECRET（dev 用 openssl rand -hex 32 生成）
```

> **M0 骨架无需 `.env` 也能启动**（`/healthz` 不依赖任何 env）。M1 起会逐项启用。

---

## 🧪 跑测试 / 静态检查

### 后端

```bash
conda run -n food-order pytest                  # 全部测试
conda run -n food-order pytest --cov=app       # 覆盖率（目标 ≥ 80%）
conda run -n food-order ruff check backend     # lint
conda run -n food-order ruff format backend    # format
conda run -n food-order mypy backend            # 类型检查
```

### 前端

```bash
cd frontend
pnpm test                # Vitest 单测（一次性）
pnpm test:watch          # watch 模式
pnpm typecheck           # tsc -b
pnpm lint                # ESLint（max-warnings 0）
pnpm build               # tsc + vite build，产物在 dist/
pnpm test:e2e            # Playwright E2E（需要先 pnpm exec playwright install）
```

---

## 🧰 常用命令速查

| 场景 | 命令 |
|---|---|
| 看 API 文档 | http://localhost:8000/docs |
| 清后端缓存 | `rm -rf backend/.ruff_cache backend/.mypy_cache backend/.pytest_cache` |
| 清前端缓存 | `cd frontend && rm -rf node_modules .vite dist && pnpm install` |
| 看 conda 环境列表 | `conda env list` |
| 退出 conda 环境 | `conda deactivate` |

---

## 🏗️ 技术栈（固定）

| 层 | 选型 | 版本 |
|---|---|---|
| 前端 | Vite + React 18 + TypeScript | Vite 5 / React 18.3 |
| 前端状态 | Zustand + TanStack Query | Zustand 4 / Query 5 |
| 前端路由 | React Router v6 | 6.x |
| 后端 | FastAPI + Python 3.11+ | FastAPI 0.110+ |
| 后端 ORM | SQLModel（SQLAlchemy 2.0 + Pydantic v2） | latest |
| 后端迁移 | Alembic | 1.13+ |
| 数据库 | MySQL 8 | 8.x |
| 鉴权 | 自建 JWT (HS256) + PyJWT | — |
| 密码哈希 | argon2-cffi | — |
| 测试（后端） | pytest + httpx + pytest-asyncio + pytest-cov | — |
| 测试（前端） | Vitest + Testing Library + Playwright | — |
| Lint（后端） | ruff + mypy | — |
| Lint（前端） | ESLint + Prettier | — |

> 任何技术变更必须先更新 [CLAUDE.md](CLAUDE.md) 的对应表 + [`spec/adr/`](spec/adr/) 写一条 ADR。

---

## 📁 目录结构

```
food-order/
├── CLAUDE.md              # 仓库级指引（开发规则、风格、提交规范）
├── README.md              # 本文件
├── .env.example           # 环境变量模板（.env 已 gitignore）
│
├── spec/                  # ⭐ SDD 单一事实来源
│   ├── product.md         # 产品目标、用户画像、核心场景
│   ├── features.md        # 功能列表 + 优先级
│   ├── api.md             # REST 接口契约
│   ├── data-model.md      # 数据表 / 字段 / 约束
│   ├── roadmap.md         # 里程碑
│   ├── features/          # 每个 feature 一份 spec（含验收清单）
│   └── adr/               # 架构决策记录（MADR 模板）
│
├── backend/               # FastAPI 后端
│   ├── app/
│   │   ├── main.py        # FastAPI 入口
│   │   ├── core/          # config / security / db engine / DI
│   │   ├── api/v1/        # 路由（按业务领域拆分）
│   │   ├── models/        # SQLModel 数据模型
│   │   ├── schemas/       # Pydantic 请求/响应模型
│   │   ├── services/      # 业务逻辑
│   │   └── utils/
│   ├── tests/             # 单元 + 集成测试
│   ├── migrations/        # Alembic 迁移脚本
│   ├── pyproject.toml     # ruff + mypy + pytest 配置
│   └── requirements.txt
│
├── frontend/              # Vite + React 前端
│   ├── src/
│   │   ├── main.tsx       # 入口
│   │   ├── routes/        # 路由级页面
│   │   ├── components/    # 通用组件
│   │   ├── features/      # 按业务领域切片（cart / order / shop ...）
│   │   │   └── <feature>/
│   │   │       ├── api.ts
│   │   │       ├── store.ts
│   │   │       ├── components/
│   │   │       └── hooks/
│   │   ├── stores/        # 全局 Zustand stores
│   │   ├── lib/           # API 客户端、工具
│   │   ├── types/         # 共享类型
│   │   └── styles/        # 全局样式 / tokens
│   ├── package.json       # 锁定 pnpm
│   └── vite.config.ts
│
├── prototype/             # UI 原型参考（HTML 静态文件，不进构建）
├── docs/                  # 工程文档
│   └── local-dev.md       # 本地开发环境细节
└── scripts/               # 一次性脚本（种子数据、迁移等）
```

---

## 🔄 开发方法论

### SDD — 规格驱动

`spec/` 是 SSOT。任何代码改动前，需求先在 `spec/` 落字。`CLAUDE.md` / `README.md` / 代码不得与 `spec/` 冲突——不一致时**先更新 spec，再改代码**。

### TDD — 测试驱动

每个功能 / bug 修复：**RED（先写失败测试）→ GREEN（最小实现）→ IMPROVE（重构）**。

- 覆盖率门槛：**≥ 80%**（行 + 分支，按模块统计）
- 测试结构 AAA（Arrange / Act / Assert）
- 命名：`test_<行为>_<条件>_<期望>`

### Git 工作流

- 分支前缀：`feat/` `fix/` `docs/` `refactor/` `chore/`
- 提交规范：Conventional Commits（`feat:` `fix:` `refactor:` `docs:` `test:` `chore:` `perf:` `ci:`）
- 标题中文，正文中文，**type 保持英文**
- PR 评审 ≥ 1 人；触及鉴权 / 支付 / 数据模型时 ≥ 2 人

详见 [CLAUDE.md](CLAUDE.md)。

---

## 🚧 当前状态：M0 骨架

✅ 已就绪：
- 后端 FastAPI 工厂 + `/healthz` + CORS 中间件
- 后端 `Settings` 配置加载（pydantic-settings，从 `.env`）
- 后端 pytest 框架 + healthz 测试
- 前端 Vite + React + TS 基础配置
- 前端 Vitest + Testing Library 配置
- 前端 ESLint + Prettier 配置

⏳ 待 M1 启动：
- MySQL 数据库 + Alembic 初始迁移
- JWT 鉴权中间件
- 用户 / 店铺 / 菜单 / 订单数据模型
- 路由 / LLM 统一层（详见 [`spec/features/F002`](spec/features) [F003](spec/features)）

里程碑完整规划见 [`spec/roadmap.md`](spec/roadmap.md)。

---

## 🆘 故障排查

<details>
<summary><b>conda 命令在 Git Bash 里找不到</b></summary>

初始化 shell：`conda init bash` 然后重启终端。Windows 推荐用 "Anaconda Prompt" 或确保 PATH 里含 `~/miniconda3/Scripts`。
</details>

<details>
<summary><b>pnpm install 报 ERESOLVE</b></summary>

删 lockfile 重装（仅在 lockfile 与 package.json 冲突时）：
```bash
cd frontend && rm pnpm-lock.yaml && pnpm install
```
</details>

<details>
<summary><b>uvicorn 启动报 "Address already in use"</b></summary>

8000 端口被占。改端口：`uvicorn app.main:app --port 8001`，或在 `vite.config.ts` 把前端 `server.port` 同步改成 8001 + 改 `VITE_API_BASE_URL`。
</details>

<details>
<summary><b>前端报 "CORS policy" 跨域</b></summary>

后端 `CORS_ALLOW_ORIGINS` 没包含前端地址。`.env` 里改成：
```
CORS_ALLOW_ORIGINS=http://localhost:5173
```
</details>

<details>
<summary><b>mypy / ruff 在编辑器里不生效</b></summary>

VS Code 推荐装 `ms-python.mypy-pyright` + `charliermarsh.ruff`；Pylance 配置 `python.analysis.typeCheckingMode = "strict"`。
</details>

<details>
<summary><b>pytest 找不到 app 模块</b></summary>

在 `backend/` 目录下运行（`pyproject.toml` 里 `pythonpath = ["."]`）。或显式：`PYTHONPATH=backend conda run -n food-order pytest`。
</details>

---

## 📚 进一步阅读

- [CLAUDE.md](CLAUDE.md) — 开发规则、风格、安全基线
- [spec/product.md](spec/product.md) — 产品定位与核心场景
- [spec/features.md](spec/features.md) — 功能列表与优先级
- [spec/api.md](spec/api.md) — REST 接口契约
- [spec/data-model.md](spec/data-model.md) — 数据模型
- [spec/roadmap.md](spec/roadmap.md) — 里程碑
- [spec/adr/](spec/adr/) — 架构决策记录
- [docs/local-dev.md](docs/local-dev.md) — 本地开发细节

---

## 📝 License

TBD（仓库初始化阶段，license 待定）。
