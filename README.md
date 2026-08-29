# food-order

餐饮点单 / 外卖方向 Web 应用。

> 仓库由 **SDD + TDD + Git** 驱动。完整规则见 [CLAUDE.md](CLAUDE.md)。

## 技术栈

- **Frontend**: Vite + React 18 + TypeScript ([frontend/](frontend/))
- **Backend**: FastAPI + Python 3.11（conda env `food-order`）([backend/](backend/))
- **Database**: MySQL 8
- **鉴权**: 自建 JWT (HS256)

规格、功能、数据模型以 [`spec/`](spec/) 为单一事实来源。

## 快速开始

### 1. 后端

```bash
conda create -n food-order python=3.11 -y
conda run -n food-order pip install -r backend/requirements.txt
conda run -n food-order uvicorn backend.app.main:app --reload --port 8000
```

健康检查：`curl http://localhost:8000/healthz` → `{"status":"ok"}`

### 2. 前端

```bash
cd frontend
pnpm install
pnpm dev
```

打开 http://localhost:5173/

### 3. 环境变量

复制 `.env.example` → `.env` 并填入真实值（**`.env` 已 gitignore**）。

| 变量 | 何时需要 | 用途 |
|---|---|---|
| `DB_*` | M1 | MySQL 连接 |
| `JWT_SECRET` | M1 | HS256 签名（`openssl rand -hex 32` 生成） |
| `CORS_ALLOW_ORIGINS` | M1 | 逗号分隔前端源 |
| `VITE_API_BASE_URL` | M1 | 前端 → 后端 base URL |
| `WECHAT_*` | M2+ | 微信登录 / 支付 |
| `STORAGE_*` | M2+ | 对象存储（菜品图） |
| `AMAP_API_KEY` | M2+ | 地图 / 配送 |
| `SMS_*` | M3+ | 短信通知 |

M0 骨架无需 `.env` 即可启动。

## 开发流程

详见 [CLAUDE.md](CLAUDE.md)。

- **SDD**：先写 `spec/`，再写代码
- **TDD**：RED → GREEN → IMPROVE，覆盖率 ≥ 80%
- **Conventional Commits**：`feat:` / `fix:` / `refactor:` / `docs:` / `test:` / `chore:` / `perf:` / `ci:`

## 目录

```
food-order/
├── backend/         # FastAPI
├── frontend/        # Vite + React
├── spec/            # 规格（单一事实来源）
├── docs/            # 工程文档
└── scripts/         # 一次性脚本
```

## 里程碑

详见 [`spec/roadmap.md`](spec/roadmap.md)。当前：**M0 — 骨架阶段**。