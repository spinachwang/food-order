# F060 — 部署上线（极光云单机一体）

> 用户故事 + 验收清单。架构决策见 [ADR 0004](../adr/0004-deployment-on-jaguar-cloud.md)，端到端手册见 [`docs/deployment.md`](../../docs/deployment.md)。

## 用户故事

**作为** 项目负责人，  
**我想要** 把 M1 Agent MVP 部署到极光云 Ubuntu 单机，  
**以便于** 真实用户能在公网域名上体验完整链路（聊天 → 偏好 → 推荐 → 餐厅 → 天气 → 总结），同时保留回滚能力。

---

## 范围

### ✅ In scope（首次上线必须）

1. 一台 Ubuntu 22.04 LTS 云主机（极光云）
2. **同机**部署：Nginx（反代）+ uvicorn（systemd 守护）+ MySQL 8
3. 前端构建产物由 Nginx 静态托管
4. Let's Encrypt HTTPS（certbot 自动续期）
5. 手动部署脚本 `scripts/deploy.sh` / `scripts/rollback.sh`
6. MySQL 每日 mysqldump 备份（保留 7 天）
7. `.env.production` 模板 + 部署前 checklist
8. systemd unit `food-order-backend.service`

### ❌ Out of scope（推迟到 M2+）

- Dockerfile / docker-compose
- GitHub Actions 自动部署
- Redis 短期对话缓存
- 多 LLM 兜底
- 对象存储 / SMS / 微信支付
- 内网 RDS
- mypy 65 / ruff 238 / Playwright 6 全绿（M2 收口）
- 灰度发布 / 蓝绿
- HSTS preload / WAF

---

## 验收清单

### A. 服务器初始化（一次性）

- [ ] `food-order` 系统用户创建（非 root 部署）
- [ ] `/root/food-order/` 代码目录（git clone）
- [ ] `/var/www/food-order/dist/` 前端产物
- [ ] `/var/log/food-order/` 日志目录
- [ ] `/var/backups/food-order/db/` 备份目录
- [ ] `conda` 已安装 + `food-order` 环境已创建 + 依赖装齐
- [ ] `nginx` 已装 + 站点配置已软链到 `sites-enabled/`
- [ ] `mysql-server-8.0` 已装 + 绑定 127.0.0.1
- [ ] `certbot` 已装 + 证书已申请（前端域 + 后端 API 域）
- [ ] `unattended-upgrades` 启用
- [ ] 防火墙（ufw）只开 22（限 IP）/ 80 / 443

> 操作入口：`scripts/setup-server.sh`（一次性；幂等）

### B. 服务能起

- [ ] `systemctl status food-order-backend` 显示 `active (running)`
- [ ] `journalctl -u food-order-backend -n 50` 无 traceback
- [ ] `curl -fsS http://127.0.0.1:8000/healthz` 返回 `{"status":"ok"}`
- [ ] `mysql -ufood_order -p food_order -e 'SELECT 1'` 成功
- [ ] `alembic current` 显示 head (`8b3c2f1a4d5e`)
- [ ] `nginx -t` 通过 + `systemctl status nginx` 显示 `active`

### C. 公网域名通

- [ ] `https://app.example.com/` 返回前端 SPA（HTML）
- [ ] `https://app.example.com/chat` 渲染 F050 聊天壳
- [ ] `https://api.example.com/docs` 显示 FastAPI Swagger UI
- [ ] `https://api.example.com/api/v1/preferences` PUT/GET 闭环（M1 测试已覆盖）
- [ ] HTTPS 证书有效 + `certbot renew --dry-run` 成功

### D. 端到端链路

- [ ] 用户在 `app.example.com` 输入「想吃辣的」
- [ ] 前端调 `POST /api/v1/agent/route`（F002）→ 至少 1 个菜系专家被选中
- [ ] 菜系专家 Node 触发 F003 调用，回包符合契约 schema
- [ ] F030 调用高德 MCP 餐厅搜索，返回 ≥ 3 家
- [ ] F031 调用高德 MCP 天气查询，返回温度 / 天气 / 降水概率
- [ ] F040 summary agent 渲染最终推荐（含 ≥ 2 备选 + 原因 + 是否外卖）
- [ ] 前端流式渲染最终结果（F050）

### E. 安全 / 反代

- [ ] 后端 8000 / MySQL 3306 **只监听 127.0.0.1**
- [ ] `curl http://<公网IP>:8000` 失败（连接拒绝）
- [ ] `curl http://api.example.com/` 不带 API 前缀时返回 404（不泄漏后端信息）
- [ ] `curl -I https://app.example.com/` 返回 `Strict-Transport-Security` / `X-Content-Type-Options: nosniff` / `X-Frame-Options: DENY`
- [ ] `CORS_ALLOW_ORIGINS=https://app.example.com`（不是 localhost）

### F. 备份 / 回滚

- [ ] `scripts/backup-db.sh` 执行成功，产出 `/var/backups/food-order/db/food_order_<ts>.sql.gz`
- [ ] `/etc/cron.d/food-order-backup` 已配（每日 03:00）
- [ ] `ls /var/backups/food-order/db/` 显示至少 1 个 ≤ 7 天前的备份文件
- [ ] `scripts/rollback.sh <ts>` 在 staging 上演练通过（恢复旧版本 + 重启 + 健康检查绿）

### G. 部署流程

- [ ] 本地：`pnpm build` 产出 `frontend/dist/`
- [ ] 本地：`tar czf release.tar.gz backend frontend/dist scripts deploy .env`
- [ ] 本地：`scp release.tar.gz user@server:/tmp/`
- [ ] 服务器：`bash /root/food-order/scripts/deploy.sh /tmp/release.tar.gz` 全程无人工干预
- [ ] 部署脚本失败时**非零退出码** + stderr 可读错误（不静默吞）

### H. 文档

- [ ] `docs/deployment.md` 端到端可跟做（含前置依赖 / 凭据 / 排错）
- [ ] `README.md` 指向 `docs/deployment.md`
- [ ] `CLAUDE.md` 引用 `docs/deployment.md`
- [ ] `.env.example` 顶部加生产部署 checklist 注释

---

## 凭据清单（部署前必须凑齐）

详见 [.env.example](../../.env.example) 与 [ADR 0004 §4](../adr/0004-deployment-on-jaguar-cloud.md)。

| 项 | 来源 | 备注 |
|---|---|---|
| 极光云主机 SSH | 极光云控制台 | 公钥登录，禁密码 |
| 域名（前端 + 后端） | 万网 / 极光云 DNS | 解析到主机公网 IP |
| `JWT_SECRET` | `openssl rand -hex 32` | ≥ 256 bit，绝不提交 |
| `DB_USER` / `DB_PASSWORD` | 部署时设置 | MySQL 8 用户，非 root |
| `AMAP_API_KEY` | 你已有 | 已在 `.env` |
| `MINIMAX_API_KEY` | 你已有 | 已在 `.env` |
| Let's Encrypt 邮箱 | 任意 | certbot 通知用 |

---

## 失败 / 排错速查

| 症状 | 排查 |
|---|---|
| `/healthz` 502 | `systemctl status food-order-backend` + `journalctl -xeu food-order-backend` |
| 502 后端启动失败 | 99% 是 env 缺失；检查 `/root/food-order/.env` 是否齐 + `journalctl` 看 stack |
| Alembic 升级失败 | `alembic -c /root/food-order/backend/alembic.ini current` + 看 head |
| 前端 404 | 检查 `/var/www/food-order/dist/` 是否被部署脚本复制 + nginx `root` 路径 |
| HTTPS 证书失效 | `certbot renew --dry-run` + 看 certbot.timer 是否 active |
| 数据库连接失败 | `mysql -u... -p... -h 127.0.0.1`；`bind-address = 127.0.0.1` 不能误改 |
| CORS 拒绝 | 检查 `CORS_ALLOW_ORIGINS=https://app.example.com`（**不能**是 localhost） |
| LLM 调用 4xx | `MINIMAX_API_KEY` 是否过期 / `MINIMAX_BASE_URL` 是否国内 |
| 餐厅搜索无结果 | 检查 `AMAP_API_KEY` 是否对应该服务（Web 服务类型）；M1 测试基线已验证 |
| 前端构建失败 | `pnpm install --frozen-lockfile` 优先 + node >= 18 |
| 部署脚本卡住 | 看哪个 step 失败；脚本里每个 step 都 `set -e` 早退 |

---

## 与其他功能的关系

| F060 步骤 | 依赖 |
|---|---|
| `alembic upgrade head` | F001 schema 已迁移 |
| 后端启动 | F002 router + F003 14 专家 + F030/F031 AMAP + F040 summary + F050 API 全部就绪 |
| 前端构建 | F050 + F051 组件 |
| 反代 `/api/*` | 后端 `app.main:app` 已挂到 `/api/v1` |

> **M1 状态已知红**（用户决定本次不修）：
> - 后端 `mypy --strict` 65 errors（主要在 `graph.py` add_node 重载 + 测试 fixture 类型）
> - 后端 `ruff check` 238 errors（RUF002/003 全角符号；项目级放宽）
> - 前端 `playwright` 6 failed（依赖真实 Amap API 数据 / UI 状态）
> - 后端 `pytest` 1 个 pre-existing failure（`test_render_base_prompt_includes_hard_constraint_chinese_only`，属 F003 历史遗留）
>
> 这些不影响功能，但**应在部署后第一时间记录到 ops runbook**，M2 收口时一次性补。
