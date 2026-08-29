# 本地开发环境搭建

## 一、依赖

| 工具 | 版本 | 安装 |
|---|---|---|
| Git | ≥ 2.40 | https://git-scm.com/ |
| Conda | Miniconda / Miniforge | https://conda-forge.org/miniforge/ |
| Node.js | ≥ 20 | https://nodejs.org/ |
| pnpm | ≥ 9 | `npm install -g pnpm` |
| MySQL | 8.x | 本地或 Docker |

> **MySQL 与 Ollama 仅 M1 起才需要**，M0 骨架阶段可跳过。

## 二、克隆与初始化

```bash
git clone <repo-url> food-order
cd food-order

# 后端
conda create -n food-order python=3.11 -y
conda run -n food-order pip install -r backend/requirements.txt

# 前端
cd frontend
pnpm install
cd ..
```

## 三、配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填入 DB_PASSWORD、JWT_SECRET 等
```

M0 无需 `.env` 即可启动（默认值即可）。

## 四、启动

```bash
# 后端
conda run -n food-order uvicorn backend.app.main:app --reload --port 8000

# 前端（新终端）
cd frontend && pnpm dev
```

访问：
- 后端健康检查：http://localhost:8000/healthz
- 后端 API 文档：http://localhost:8000/docs
- 前端：http://localhost:5173/