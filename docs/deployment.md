# 部署手册（极光云 · Ubuntu 22.04 · 单机一体）

> 首次上线 M1 Agent MVP。架构决策见 [spec/adr/0004-deployment-on-jaguar-cloud.md](../spec/adr/0004-deployment-on-jaguar-cloud.md)，验收清单见 [spec/features/F060-deployment.md](../spec/features/F060-deployment.md)。

## 0. 一图流

```
┌─────────────────────────────────────────────────────┐
│       极光云 Ubuntu 22.04 LTS（单台 2C4G 起步）        │
│                                                     │
│   Nginx :80/:443 (Let's Encrypt)                    │
│     ├─ /api/* → 127.0.0.1:8000 (uvicorn · systemd)  │
│     └─ /*      → /var/www/food-order/dist/ (SPA)    │
│                                                     │
│   uvicorn  ← systemd: food-order-backend.service    │
│     └─ conda env food-order · 2 workers              │
│                                                     │
│   MySQL 8 (127.0.0.1:3306, 仅本机)                   │
│     └─ food_order + food_order_test                  │
│                                                     │
│   日志 /var/log/food-order/app.log (JSON · 轮转)     │
│   备份 /var/backups/food-order/db/  (·7 天保留)      │
└─────────────────────────────────────────────────────┘
```

## 1. 前置准备（你必须先凑齐的）

### 1.1 云主机

- 极光云控制台开一台 **Ubuntu 22.04 LTS**，规格 ≥ **2 vCPU / 4 GB RAM / 80 GB SSD**
- 公网带宽 ≥ 3 Mbps
- 安全组：**只放 22 / 80 / 443**（22 限你公司 IP）
- 用 **SSH 公钥** 登录（禁用密码登录）

### 1.2 域名

你需要 2 个（或一个泛域证书）：

| 域名 | 用途 | 解析 |
|---|---|---|
| `app.example.com` | 前端 SPA | A 记录 → 云主机公网 IP |
| `api.example.com` | 后端 API | A 记录 → 云主机公网 IP |

### 1.3 凭据清单（部署时填 `.env`）

- `JWT_SECRET`：`openssl rand -hex 32`
- `DB_USER` / `DB_PASSWORD`：自定义的 MySQL 用户（非 root）
- `AMAP_API_KEY`：你已有
- `MINIMAX_API_KEY`：你已有
- Let's Encrypt 邮箱：任意可接收通知的邮箱

## 2. 服务器初始化（一次性）

### 2.1 用 `scripts/setup-server.sh` 一把梭

```bash
# 在本地：先 clone 仓库到服务器（推荐做法）
ssh ubuntu@<server-ip>
sudo -i
git clone <your-git-repo> /root/food-order
cd /root/food-order

# 跑一次性安装脚本（幂等，可重跑）
bash scripts/setup-server.sh
```

> 这个脚本会做：装 nginx / mysql-server / certbot / unattended-upgrades + 建 `food-order` 系统用户 + 建 `/root/food-order` `/var/www/food-order` `/var/log/food-order` `/var/backups/food-order` + 装 conda + 建 `food-order` conda env + 装 backend 依赖。

### 2.2 配置生产 `.env`

```bash
sudo cp /root/food-order/.env.example /root/food-order/.env
sudo -u food-order vi /root/food-order/.env
sudo chmod 600 /root/food-order/.env
sudo chown food-order:food-order /root/food-order/.env
```

**生产必须改的字段：**

| 字段 | 生产值 |
|---|---|
| `DB_HOST` | `127.0.0.1` |
| `DB_USER` | 不要用 `root` |
| `DB_PASSWORD` | 高强度 |
| `JWT_SECRET` | `openssl rand -hex 32` |
| `CORS_ALLOW_ORIGINS` | `https://app.example.com`（**不要** localhost） |
| `VITE_API_BASE_URL` | `https://api.example.com` |
| `LOG_LEVEL` | `INFO` |
| `LOG_FORMAT` | `json` |
| `LOG_PROMPT_DEBUG` | `false`（生产不开 prompt 落盘） |
| `LOG_FILE_PATH` | `/var/log/food-order/app.log` |
| `BACKEND_HOST` | `127.0.0.1`（仅本机） |
| `BACKEND_PORT` | `8000` |

### 2.3 初始化数据库

```bash
sudo -i -u food-order
cd /root/food-order/backend
conda run -n food-order python -c "
from app.core.config import get_settings
from sqlalchemy import create_engine, text
s = get_settings()
admin = create_engine(s.admin_database_url, isolation_level='AUTOCOMMIT')
with admin.connect() as c:
    c.execute(text(f\"CREATE DATABASE IF NOT EXISTS \`{s.db_name}\` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci\"))
    c.execute(text(f\"CREATE DATABASE IF NOT EXISTS \`{s.db_name_test}\` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci\"))
print('OK:', s.db_name, s.db_name_test)
"
conda run -n food-order alembic upgrade head
```

### 2.4 装 nginx 站点 + systemd unit

```bash
# nginx 站点
sudo cp deploy/nginx/food-order.conf /etc/nginx/sites-available/
sudo ln -sf /etc/nginx/sites-available/food-order.conf /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t

# systemd unit
sudo cp deploy/systemd/food-order-backend.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable food-order-backend.service
```

### 2.5 申请 Let's Encrypt 证书

```bash
# 先临时用 HTTP-only 站点做 ACME 校验
sudo certbot --nginx -d app.example.com -d api.example.com \
    --non-interactive --agree-tos -m you@example.com
# certbot 会自动改 nginx 配置 + 加 HTTPS + 加续期 timer
```

### 2.6 启动服务

```bash
sudo systemctl restart food-order-backend
sudo systemctl reload nginx
sudo systemctl status food-order-backend
sudo systemctl status nginx
```

## 3. 健康检查

```bash
# 本地 8000
curl -fsS http://127.0.0.1:8000/healthz
# {"status":"ok"}

# 公网前端
curl -fsS https://app.example.com/

# 公网 API 文档
curl -fsS https://api.example.com/docs
```

## 4. 部署流程（每次发布）

### 4.1 本地构建 + 打包

```bash
# 在仓库根
cd frontend && pnpm install --frozen-lockfile && pnpm build && cd ..
# 产物在 frontend/dist/

cd /path/to/food-order
tar czf release.tar.gz \
    backend frontend/dist scripts deploy \
    --exclude=backend/.venv --exclude=backend/__pycache__ \
    --exclude='**/.pytest_cache' --exclude='**/node_modules'

scp release.tar.gz ubuntu@<server-ip>:/tmp/
```

### 4.2 服务器上一键部署

```bash
ssh ubuntu@<server-ip>
sudo bash /root/food-order/scripts/deploy.sh /tmp/release.tar.gz
```

`deploy.sh` 会做：

1. 备份当前版本到 `/root/food-order.backup.<ts>/`
2. 解压新版本到 `/root/food-order/`
3. `conda run -n food-order pip install -r backend/requirements.txt`
4. `conda run -n food-order alembic upgrade head`
5. 复制 `frontend/dist/` → `/var/www/food-order/dist/`
6. `systemctl restart food-order-backend`
7. `nginx -s reload`
8. `curl http://127.0.0.1:8000/healthz` 探活
9. 任何一步失败立即非零退出，**不静默吞**

> **可覆盖 HOME**：脚本支持 `FOOD_ORDER_HOME=/path/to/home` 覆盖默认 `/root/food-order`。

## 5. 回滚

```bash
ssh ubuntu@<server-ip>
sudo bash /root/food-order/scripts/rollback.sh
# 列出可回滚的版本
sudo bash /root/food-order/scripts/rollback.sh 20260909_210000
# 回滚到指定时间戳版本
```

`rollback.sh` 会做：

1. 把 `/root/food-order.backup.<ts>/` 覆盖回 `/root/food-order/`
2. 重跑 alembic（如需 downgrade：`alembic downgrade -1` 后再 upgrade）
3. 重启 systemd + reload nginx
4. 健康检查

## 6. 备份

### 6.1 手动备份

```bash
sudo bash /root/food-order/scripts/backup-db.sh
# /var/backups/food-order/db/food_order_YYYYMMDD_HHMMSS.sql.gz
```

### 6.2 定时备份

`setup-server.sh` 已装 `/etc/cron.d/food-order-backup`：每日 03:00 执行 `backup-db.sh`，保留 7 天。

### 6.3 异地同步（M2+）

v2 接阿里云 OSS / 极光云对象存储时再加。当前只落本机 `/var/backups/`。

## 7. 监控 / 告警

| 项 | 接入方式 |
|---|---|
| 服务存活 | `curl http://127.0.0.1:8000/healthz`（极光云负载均衡探针） |
| systemd 状态 | `systemctl status food-order-backend`（异常会 failed） |
| 日志聚合 | `LOG_FORMAT=json` + 接入 Loki / 极光云日志服务 |
| HTTPS 证书 | `certbot.timer`（装好即默认；`certbot renew --dry-run` 自检） |
| 系统补丁 | `unattended-upgrades` 自动 |
| 磁盘 | `df -h /var`（备份目录满了会失败；建议 cron 加告警） |

## 8. 排错速查

| 症状 | 排查 |
|---|---|
| `/healthz` 502 / curl 失败 | `systemctl status food-order-backend` + `journalctl -xeu food-order-backend` |
| 后端启动报错 | 99% 是 env 缺失；检查 `/root/food-order/.env` 是否齐 |
| Alembic 升级失败 | `alembic -c /root/food-order/backend/alembic.ini current` 看 head |
| 前端 404 | 检查 `/var/www/food-order/dist/` 是否被部署脚本复制 + nginx `root` |
| HTTPS 证书失效 | `certbot renew --dry-run` + `systemctl status certbot.timer` |
| MySQL 连不上 | `mysql -u... -p... -h 127.0.0.1`；`bind-address = 127.0.0.1` 不能误改 |
| CORS 拒绝 | `CORS_ALLOW_ORIGINS=https://app.example.com`（不能是 localhost） |
| LLM 4xx | `MINIMAX_API_KEY` 是否过期 / `MINIMAX_BASE_URL` 国内 |
| 餐厅无结果 | `AMAP_API_KEY` 是否对应该服务（Web 服务类型） |
| 前端 build 失败 | `pnpm install --frozen-lockfile` + node ≥ 18 |
| 部署脚本卡住 | 每个 step 都 `set -e` 早退，看 stderr 定位 |
| 端口 8000 被占 | `ss -tlnp | grep 8000` + 检查是否有遗留 uvicorn |

## 9. 安全 checklist（部署后逐项过一遍）

- [ ] SSH 密码登录已禁用（`PasswordAuthentication no` in `/etc/ssh/sshd_config`）
- [ ] SSH 端口可考虑改成非 22
- [ ] root 登录禁用（`PermitRootLogin no`）
- [ ] ufw 只开 22（限 IP）/ 80 / 443
- [ ] MySQL 监听 `127.0.0.1`（不是 `0.0.0.0`）
- [ ] `.env` 是 `chmod 600` + `chown food-order:food-order`
- [ ] `JWT_SECRET` ≥ 256 bit（`openssl rand -hex 32` 输出长度正好 64 hex = 256 bit）
- [ ] nginx 站点强制 HTTPS（HTTP → HTTPS 重定向）
- [ ] `LOG_PROMPT_DEBUG=false`（生产不落盘 LLM prompt/response）
- [ ] `LOG_FORMAT=json`（便于日志聚合）
- [ ] `/healthz` 不暴露内部信息（当前返回 `{"status":"ok"}`，OK）

## 10. 不在本次范围（M2+ 再说）

- Dockerfile / docker-compose
- GitHub Actions 自动部署
- Redis 短期对话缓存
- 多 LLM 兜底 / 多城市
- 对象存储 / SMS / 微信支付
- 内网 RDS
- mypy 65 / ruff 238 / Playwright 6 全绿（M2 收口）
- 灰度 / 蓝绿
- HSTS preload / WAF
- 异地备份到 OSS

## 11. 相关文件

- 架构决策：[`spec/adr/0004-deployment-on-jaguar-cloud.md`](../spec/adr/0004-deployment-on-jaguar-cloud.md)
- 验收清单：[`spec/features/F060-deployment.md`](../spec/features/F060-deployment.md)
- nginx 配置：[`deploy/nginx/food-order.conf`](../deploy/nginx/food-order.conf)
- systemd unit：[`deploy/systemd/food-order-backend.service`](../deploy/systemd/food-order-backend.service)
- env 模板：[`.env.example`](../.env.example)
- 一次性安装：[`scripts/setup-server.sh`](../scripts/setup-server.sh)
- 部署：[`scripts/deploy.sh`](../scripts/deploy.sh)
- 回滚：[`scripts/rollback.sh`](../scripts/rollback.sh)
- 备份：[`scripts/backup-db.sh`](../scripts/backup-db.sh)
