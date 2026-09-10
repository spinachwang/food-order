# ADR 0004 — 部署架构（极光云单机一体 · 首次上线）

- **状态**：Accepted
- **日期**：2026-09-09
- **决策者**：项目负责人
- **关联**：CLAUDE.md §「技术栈」、[roadmap.md M1 验收清单](../roadmap.md)、[F060 部署上线](../features/F060-deployment.md)

## 背景

M1 Agent MVP 的功能模块已落地（14 菜系专家 / 高德 MCP / 总结 / 聊天壳），但**生产部署基础设施全无**：

- 无 `Dockerfile` / `docker-compose.yml`
- 无 `docs/deployment.md`
- 无 `scripts/deploy.sh` 等运维脚本
- 无 systemd unit / nginx 配置
- `.env.example` 已就位，但缺少"生产部署 checklist"
- 后端端口 `8000` 当前直接由开发服务器监听，无反代、无 HTTPS、无速率限制

首次上云的硬约束：

1. M1 质量门（mypy 65 / ruff 238 / Playwright 6 failed）**本次先不上**，M2 补齐 —— 所以上线版本接受已知 lint/test 红
2. 预算敏感 —— 上云走**最小成本**：单台云主机 + 同机 MySQL，不上 RDS / k8s / 容器编排
3. 极光云（国内云厂商）—— 跟阿里云 / 腾讯云在 API 层面通用，但需要避免海外服务（Vercel / Cloudflare Workers / AWS SES）
4. CI/CD 用**手动脚本**，暂不接 GitHub Actions

## 决策

### 1. 单机一体架构

```
┌────────────────────────────────────────────────────┐
│            极光云 Ubuntu 22.04 LTS（单台）           │
│                                                    │
│   Nginx :443 / :80 (Let's Encrypt)                 │
│     ├─ /api/*       → uvicorn :8000  (127.0.0.1)   │
│     └─ /*           → /var/www/food-order/dist/     │
│                                                    │
│   uvicorn (systemd: food-order-backend.service)    │
│     └─ conda env food-order · python -m uvicorn    │
│                                                    │
│   MySQL 8 (systemd: mysql.service)                 │
│     └─ 数据库 food_order + food_order_test          │
│                                                    │
│   日志: /var/log/food-order/app.log (JSON, 轮转)    │
└────────────────────────────────────────────────────┘
```

### 2. 进程边界（端口只暴露 80/443）

| 端口 | 服务 | 监听 |
|---|---|---|
| **80 / 443** | nginx | `0.0.0.0`（对外） |
| **8000** | uvicorn | `127.0.0.1`（仅本机反代可达） |
| **3306** | MySQL | `127.0.0.1`（仅本机） |
| **22** | ssh | 限 IP 白名单 |

> **理由**：后端 8000 不直接对外；MySQL 不开公网。安全组只放 80/443/22。

### 3. 部署目录约定（服务器上）

```
/opt/food-order/                    ← 代码（git clone）
  ├── backend/
  ├── frontend/
  ├── spec/
  ├── scripts/
  └── .env                           ← 生产环境变量（chmod 600）

/var/www/food-order/dist/            ← 前端构建产物（nginx 直接 serve）

/var/log/food-order/                 ← 日志（RotatingFileHandler 落盘）
  └── app.log

/var/backups/food-order/db/          ← mysqldump 备份
  └── food_order_YYYYMMDD_HHMMSS.sql.gz

/etc/nginx/sites-available/food-order.conf
/etc/systemd/system/food-order-backend.service
```

### 4. systemd unit（uvicorn 守护）

- **user**：`food-order`（新建系统用户，非 root）
- **WorkingDirectory**：`/opt/food-order/backend`
- **ExecStart**：`conda run -n food-order uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 2`
- **Restart**：`on-failure`，`RestartSec=5`
- **EnvironmentFile**：`/opt/food-order/.env`（不要 `Environment=` 内嵌密钥）
- 日志走 `journalctl -u food-order-backend` + 文件落盘（`LOG_FILE_PATH=/var/log/food-order/app.log`）

### 5. nginx 反代要点

- `/api/*` 反代到 `http://127.0.0.1:8000`，加 `proxy_set_header X-Forwarded-Proto/Host/For`
- `/*` 静态 SPA，`try_files $uri /index.html`（React Router）
- `client_max_body_size 10M`（F050 聊天消息 + 未来图片上传）
- 启用 gzip；启用 HTTPS（Let's Encrypt，certbot timer 自动续期）
- 安全头：`X-Content-Type-Options nosniff` / `X-Frame-Options DENY` / `Referrer-Policy strict-origin-when-cross-origin`
- `Strict-Transport-Security: max-age=31536000; includeSubDomains`

### 6. MySQL 8 同机

- `apt install mysql-server-8.0`（Ubuntu 22.04 默认源），**绑定 127.0.0.1**
- 字符集 `utf8mb4` / 排序 `utf8mb4_0900_ai_ci`（与 `database_url` 一致）
- 建库：`food_order`（生产）+ `food_order_test`（CI 用；权限收紧）
- **备份**：`/etc/cron.daily/food-order-backup` → `mysqldump` → gzip → `/var/backups/food-order/db/`；保留 7 天

### 7. 部署流程（手动脚本驱动）

```
本地:
  1. pnpm build                                # 产出 frontend/dist/
  2. tar czf release.tar.gz backend/ frontend/dist scripts/ deploy/ .env
  3. scp release.tar.gz user@server:/tmp/

服务器:
  4. /opt/food-order/scripts/deploy.sh /tmp/release.tar.gz
       ├─ 备份旧版 (/opt/food-order.backup.YYYYMMDD_HHMMSS/)
       ├─ 解压到 /opt/food-order/
       ├─ conda run -n food-order alembic upgrade head
       ├─ 重载 systemd: systemctl restart food-order-backend
       ├─ 重载 nginx: nginx -s reload
       └─ 健康检查: curl -fsS http://127.0.0.1:8000/healthz
```

### 8. 回滚

`scripts/rollback.sh [YYYYMMDD_HHMMSS]` —— 把 `/opt/food-order.backup.<ts>/` 覆盖回 `/opt/food-order/`，重跑迁移降级（`alembic downgrade -1`），重启。

### 9. 不在本次范围（明确推迟）

| 项 | 推迟到 |
|---|---|
| `Dockerfile` / `docker-compose.yml` | M2+ 看是否需要迁移 / 多环境 |
| GitHub Actions CI/CD | 团队规模 / 部署频率上来再说 |
| Redis 短期对话缓存 | M2 体验增强 |
| 多 LLM 兜底 / 多城市 | M3 商业化 |
| 对象存储 / SMS / 微信支付 | 业务真正用到再开 |
| mypy 65 / ruff 238 / Playwright 6 全绿 | M2 收口 |
| HSTS preload / WAF | 流量上来再说 |

## 理由

- **KISS**：单机一体最小可上线，1 台云主机的月成本可控；MySQL 同机避免跨主机延迟
- **可逆**：回滚脚本 + 部署前自动备份，错误上线 5 分钟内恢复
- **边界清晰**：8000 / 3306 不开公网，security group 只放 80/443/22，攻击面最小
- **与 ADR 0001 一致**：延续 conda env `food-order` / pnpm / FastAPI / SQLModel 技术栈
- **CLAUDE.md 合规**：不引入未在新 ADR 中声明的工具链；脚本走 `conda run` 而非裸 python

## 后果

- **新增文件**：
  - `spec/features/F060-deployment.md`（用户故事 + 验收清单）
  - `docs/deployment.md`（端到端部署手册）
  - `deploy/nginx/food-order.conf`（nginx 站点配置）
  - `deploy/systemd/food-order-backend.service`（systemd unit）
  - `deploy/env/food-order.env.production`（生产 env 模板）
  - `scripts/setup-server.sh`（一次性安装 nginx / mysql / conda / certbot）
  - `scripts/deploy.sh`（应用部署）
  - `scripts/rollback.sh`（回滚到上一版本）
  - `scripts/backup-db.sh`（手动 / 定时触发 mysqldump）
- **更新**：
  - `spec/features.md` 新增 F060 条目
  - `spec/roadmap.md` M2 状态更新（部署收尾）
  - `README.md` 新增部署章节，指向 `docs/deployment.md`
  - `CLAUDE.md` 引用 `docs/deployment.md`
  - `.env.example` 顶部加「生产部署必读」注释块
- **运维责任**：
  - 服务器系统补丁：`unattended-upgrades`
  - 证书续期：`certbot.timer`（装好即默认）
  - 备份保留：≥ 7 天异地 / OSS 同步（v2 再说）
  - `/healthz` 探针：极光云负载均衡健康检查

## 备选方案

- **直接 docker-compose 一体**：放弃 —— 没补 Dockerfile / compose 是一次大改动；本次优先"今天能上"
- **阿里云 / 腾讯云 RDS**：放弃 —— M1 流量小，单机 MySQL 已足够；上 RDS 是 M3 规模再说
- **GitHub Actions 自动部署**：放弃 —— 团队单开发 + 低频部署，手动 scp 更可控；触发多了再升
- **前置必须修 mypy/ruff/Playwright**：放弃 —— 用户明确"只部署，质量门后补"；M1 接受已知红
- **k3s / k8s**：过度工程

## 待澄清（执行中跟进）

- 极光云是否提供"内网域名解析"内网访问 RDS？本次 MySQL 同机不涉及，但 v2 上 RDS 时需要
- 备份是否同步到对象存储？本次只落本机 `/var/backups/`；M2 看是否接 OSS
- 是否需要"灰度发布 / 蓝绿"？本次单实例不支持；M2 流量起来再说

## 参考

- ADR 0001 初始技术栈：[`./0001-initial-stack.md`](./0001-initial-stack.md)
- ADR 0003 提示词资产：[`./0003-prompts-as-first-class-assets.md`](./0003-prompts-as-first-class-assets.md)
- F060 部署上线 spec：[`../features/F060-deployment.md`](../features/F060-deployment.md)
- 部署手册：[`../../docs/deployment.md`](../../docs/deployment.md)
- `.env.example`：[`../../.env.example`](../../.env.example)
- CLAUDE.md：[`../../CLAUDE.md`](../../CLAUDE.md)

---

## 修订记录

（暂无）
