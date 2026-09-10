#!/usr/bin/env bash
# food-order · 服务器一次性初始化（幂等）
#
# 在 Ubuntu 22.04 LTS 上跑：
#   sudo bash scripts/setup-server.sh
#
# 做这些事：
#   1. apt update + 装 nginx / mysql-server-8.0 / certbot / python3-pip / ufw / unattended-upgrades
#   2. 创建 food-order 系统用户（非 root 跑后端）
#   3. 创建部署目录 /opt/food-order · /var/www/food-order · /var/log/food-order · /var/backups/food-order
#   4. 装 Miniconda + 建 conda env food-order + 装 backend 依赖
#   5. MySQL 8 绑定 127.0.0.1（不暴露公网）
#   6. ufw 防火墙：22（限 IP）/ 80 / 443
#   7. 安装每日 03:00 的 mysqldump cron
#
# 不会做（需手动）：
#   - 申请 Let's Encrypt 证书（要等 DNS 解析生效）
#   - 复制 nginx / systemd 配置（要等用户填好 .env / 改域名）
#   - 初始化 MySQL 用户（要等用户填 DB_PASSWORD）
#   - alembic upgrade head（要等 .env 配好）

set -euo pipefail

readonly FOOD_ORDER_USER="food-order"
readonly FOOD_ORDER_HOME="/opt/food-order"
readonly DIST_DIR="/var/www/food-order"
readonly LOG_DIR="/var/log/food-order"
readonly BACKUP_DIR="/var/backups/food-order/db"
readonly CONDA_INSTALL_DIR="/opt/conda"
readonly CONDA_ENV_NAME="food-order"

# ---------- 前置校验 ----------
if [[ $EUID -ne 0 ]]; then
    echo "[ERROR] 必须用 root 跑：sudo bash $0" >&2
    exit 1
fi

if ! command -v apt-get >/dev/null 2>&1; then
    echo "[ERROR] 仅支持 Ubuntu/Debian；当前系统没有 apt-get" >&2
    exit 1
fi

# Ubuntu 版本校验（22.04 LTS）
if [[ -r /etc/os-release ]]; then
    . /etc/os-release
    if [[ "${ID:-}" != "ubuntu" ]]; then
        echo "[WARN] 当前 OS=${ID:-?} 不是 ubuntu；脚本假定 Ubuntu 22.04 LTS，其他发行版可能需要适配" >&2
    fi
fi

log() { printf '\033[1;34m[setup]\033[0m %s\n' "$*"; }
err() { printf '\033[1;31m[ERROR]\033[0m %s\n' "$*" >&2; }

# ---------- 1. apt 装包 ----------
log "1/7 apt update + 装系统依赖"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y \
    nginx \
    mysql-server \
    certbot \
    python3-certbot-nginx \
    python3-pip \
    python3-venv \
    ufw \
    unattended-upgrades \
    curl \
    ca-certificates \
    git

# ---------- 2. 创建系统用户 ----------
log "2/7 创建 ${FOOD_ORDER_USER} 系统用户"
if ! id "${FOOD_ORDER_USER}" >/dev/null 2>&1; then
    adduser --system --no-create-home --group --shell /usr/sbin/nologin "${FOOD_ORDER_USER}"
else
    log "  用户 ${FOOD_ORDER_USER} 已存在，跳过"
fi

# ---------- 3. 部署目录 ----------
log "3/7 创建部署目录"
install -d -m 0755 -o root -g root "${FOOD_ORDER_HOME}"
install -d -m 0755 -o "${FOOD_ORDER_USER}" -g "${FOOD_ORDER_USER}" "${DIST_DIR}"
install -d -m 0755 -o "${FOOD_ORDER_USER}" -g "${FOOD_ORDER_USER}" "${LOG_DIR}"
install -d -m 0750 -o root -g "${FOOD_ORDER_USER}" "$(dirname "${BACKUP_DIR}")"
install -d -m 0750 -o root -g "${FOOD_ORDER_USER}" "${BACKUP_DIR}"

# ---------- 4. 装 Miniconda + 建 env ----------
log "4/7 Miniconda + conda env ${CONDA_ENV_NAME}"
if [[ ! -d "${CONDA_INSTALL_DIR}" ]]; then
    log "  下载 Miniconda"
    cd /tmp
    curl -fsSL https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -o miniconda.sh
    bash miniconda.sh -b -p "${CONDA_INSTALL_DIR}"
    rm -f miniconda.sh
    "${CONDA_INSTALL_DIR}/bin/conda" init bash
else
    log "  Miniconda 已装在 ${CONDA_INSTALL_DIR}"
fi

# shellcheck disable=SC1091
source "${CONDA_INSTALL_DIR}/etc/profile.d/conda.sh"

if ! conda env list | grep -q "^${CONDA_ENV_NAME}\s"; then
    log "  创建 conda env ${CONDA_ENV_NAME} (Python 3.11)"
    conda create -n "${CONDA_ENV_NAME}" python=3.11 -y
else
    log "  conda env ${CONDA_ENV_NAME} 已存在"
fi

# 装 backend 依赖（如果 /opt/food-order/backend/requirements.txt 存在）
if [[ -f "${FOOD_ORDER_HOME}/backend/requirements.txt" ]]; then
    log "  装 backend 依赖（pip install -r backend/requirements.txt）"
    conda run -n "${CONDA_ENV_NAME}" pip install -r "${FOOD_ORDER_HOME}/backend/requirements.txt"
else
    log "  WARN: ${FOOD_ORDER_HOME}/backend/requirements.txt 不存在；手动 conda run -n ${CONDA_ENV_NAME} pip install -r backend/requirements.txt"
fi

# ---------- 5. MySQL 8 绑定 127.0.0.1 ----------
log "5/7 MySQL 8 绑定 127.0.0.1"
# Ubuntu 22.04 默认 MySQL 配置已绑定 127.0.0.1（/etc/mysql/mysql.conf.d/mysqld.cnf）
# 这里仅做兜底确认 + 修改
if [[ -f /etc/mysql/mysql.conf.d/mysqld.cnf ]]; then
    if grep -qE "^bind-address\s*=\s*127\.0\.0\.1" /etc/mysql/mysql.conf.d/mysqld.cnf; then
        log "  bind-address 已是 127.0.0.1"
    else
        sed -i 's/^bind-address\s*=.*/bind-address = 127.0.0.1/' /etc/mysql/mysql.conf.d/mysqld.cnf
        log "  已把 bind-address 改为 127.0.0.1"
    fi
fi
systemctl enable --now mysql.service
systemctl restart mysql.service

# ---------- 6. ufw 防火墙 ----------
log "6/7 ufw 防火墙（默认 deny + 开 22/80/443）"
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
# 22 默认放行；用户可后续限 IP（ufw allow from <ip> to any port 22）
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable
ufw status

# ---------- 7. cron 备份 ----------
log "7/7 每日 03:00 mysqldump 备份 cron"
cat > /etc/cron.d/food-order-backup <<'EOF'
# food-order 每日 mysqldump 备份（保留 7 天）
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

0 3 * * *  root  bash /opt/food-order/scripts/backup-db.sh >> /var/log/food-order/backup.log 2>&1
EOF
chmod 644 /etc/cron.d/food-order-backup

# ---------- 收尾 ----------
log "✅ 服务器初始化完成"
cat <<'EOF'

================================================================
 后续手动步骤（脚本没做）：
================================================================
  1. 配置 /opt/food-order/.env：
       sudo cp /opt/food-order/.env.example /opt/food-order/.env
       sudo -u food-order vi /opt/food-order/.env    # 填 JWT_SECRET/DB_PASSWORD/API_KEY
       sudo chmod 600 /opt/food-order/.env

  2. 初始化 MySQL 用户 + 数据库：
       sudo mysql -e "CREATE USER 'food_order'@'127.0.0.1' IDENTIFIED BY '<password>';"
       sudo mysql -e "GRANT ALL ON food_order.* TO 'food_order'@'127.0.0.1';"
       sudo mysql -e "GRANT ALL ON food_order_test.* TO 'food_order'@'127.0.0.1';"
       sudo mysql -e "FLUSH PRIVILEGES;"

  3. 跑 alembic 迁移：
       sudo -u food-order conda run -n food-order \
           bash -c "cd /opt/food-order/backend && alembic upgrade head"

  4. 复制 nginx / systemd 配置 + 启动：
       sudo cp /opt/food-order/deploy/nginx/food-order.conf /etc/nginx/sites-available/
       sudo ln -sf /etc/nginx/sites-available/food-order.conf /etc/nginx/sites-enabled/
       sudo rm -f /etc/nginx/sites-enabled/default
       sudo sed -i 's/example.com/<你的域名>/g' /etc/nginx/sites-available/food-order.conf
       sudo nginx -t

       sudo cp /opt/food-order/deploy/systemd/food-order-backend.service /etc/systemd/system/
       sudo systemctl daemon-reload
       sudo systemctl enable --now food-order-backend.service

  5. 申请 Let's Encrypt 证书：
       sudo certbot --nginx -d app.example.com -d api.example.com \
           --non-interactive --agree-tos -m you@example.com

  6. 公网域名解析到本机公网 IP（DNS A 记录）

  7. 健康检查：
       curl -fsS http://127.0.0.1:8000/healthz
       curl -fsS https://app.example.com/
       curl -fsS https://api.example.com/docs

================================================================
EOF
