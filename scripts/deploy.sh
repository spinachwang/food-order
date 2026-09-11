#!/usr/bin/env bash
# food-order · 部署脚本（手动跑）
#
# 用法：
#   sudo bash scripts/deploy.sh /tmp/release.tar.gz
#
# 可覆盖默认 HOME（不传则用 /root/food-order）：
#   sudo FOOD_ORDER_HOME=/path/to/home bash scripts/deploy.sh /tmp/release.tar.gz
#
# 流程：
#   1. 校验 tarball + 校验 ${FOOD_ORDER_HOME}/.env 存在
#   2. 备份当前 ${FOOD_ORDER_HOME} 到 ${FOOD_ORDER_HOME}.backup.<ts>/
#   3. 解压新版本到 ${FOOD_ORDER_HOME}/（保留 .env / scripts）
#   4. 装 backend 依赖（conda run pip install）
#   5. alembic upgrade head
#   6. 复制 frontend/dist → /var/www/food-order/dist
#   7. systemctl restart food-order-backend
#   8. nginx -s reload
#   9. 探活 curl http://127.0.0.1:8000/healthz
#
# 任一步骤失败立即非零退出，stderr 打印可读错误。

set -euo pipefail

readonly FOOD_ORDER_HOME="${FOOD_ORDER_HOME:-/root/food-order}"
readonly DIST_DIR="/var/www/food-order/dist"
readonly LOG_DIR="/var/log/food-order"
readonly SERVICE_NAME="food-order-backend.service"
readonly HEALTHCHECK_URL="http://127.0.0.1:8000/healthz"

# ---------- 前置校验 ----------
if [[ $EUID -ne 0 ]]; then
    echo "[ERROR] 必须用 root 跑：sudo bash $0 <release.tar.gz>" >&2
    exit 1
fi

if [[ $# -lt 1 ]]; then
    echo "[ERROR] 用法: $0 <release.tar.gz>" >&2
    exit 1
fi

TARBALL="$1"
if [[ ! -f "$TARBALL" ]]; then
    echo "[ERROR] tarball 不存在: $TARBALL" >&2
    exit 1
fi

if [[ ! -f "${FOOD_ORDER_HOME}/.env" ]]; then
    echo "[ERROR] ${FOOD_ORDER_HOME}/.env 不存在；先 cp .env.example 并填好" >&2
    exit 1
fi

log() { printf '\033[1;34m[deploy]\033[0m %s\n' "$*"; }
err() { printf '\033[1;31m[ERROR]\033[0m %s\n' "$*" >&2; }

TS="$(date -u +%Y%m%d_%H%M%S)"
BACKUP_DIR="${FOOD_ORDER_HOME}.backup.${TS}"

# ---------- 1. 备份当前版本 ----------
log "1/9 备份当前版本 → ${BACKUP_DIR}/"
install -d -m 0755 "${BACKUP_DIR}"

# 用 cp -a 保留权限；排除日志/缓存/venv（不要把运行期产物备份进去）
rsync -a --exclude='.env' --exclude='*.pyc' --exclude='__pycache__' \
    --exclude='.pytest_cache' --exclude='.venv' --exclude='venv' \
    --exclude='node_modules' --exclude='dist' \
    "${FOOD_ORDER_HOME}/" "${BACKUP_DIR}/" \
    || { err "备份失败"; exit 1; }

# ---------- 2. 解压新版本 ----------
log "2/9 解压 ${TARBALL} → ${FOOD_ORDER_HOME}/"
tar -xzf "$TARBALL" -C "${FOOD_ORDER_HOME}/" \
    || { err "解压失败"; exit 1; }

# 确保 .env 没被覆盖（tar 包里不该含 .env，但兜底）
[[ -f "${FOOD_ORDER_HOME}/.env" ]] || {
    err ".env 在解压后丢失；拒绝继续"
    exit 1
}

chown -R food-order:food-order "${FOOD_ORDER_HOME}" || true

# ---------- 3. 装 backend 依赖 ----------
log "3/9 装 backend 依赖"
sudo -u food-order bash -c "
    source /opt/conda/etc/profile.d/conda.sh
    conda activate food-order
    pip install -r '${FOOD_ORDER_HOME}/backend/requirements.txt'
" || { err "pip install 失败"; exit 1; }

# ---------- 4. alembic 迁移 ----------
log "4/9 alembic upgrade head"
sudo -u food-order bash -c "
    source /opt/conda/etc/profile.d/conda.sh
    conda activate food-order
    cd '${FOOD_ORDER_HOME}/backend'
    alembic upgrade head
" || { err "alembic upgrade 失败"; exit 1; }

# ---------- 5. 复制前端产物 ----------
log "5/9 复制 frontend/dist → ${DIST_DIR}"
if [[ -d "${FOOD_ORDER_HOME}/frontend/dist" ]]; then
    install -d -m 0755 -o food-order -g food-order "${DIST_DIR}"
    rsync -a --delete "${FOOD_ORDER_HOME}/frontend/dist/" "${DIST_DIR}/" \
        || { err "复制 dist 失败"; exit 1; }
    chown -R food-order:food-order "${DIST_DIR}"
else
    err "frontend/dist 不存在；前端构建失败或 tarball 不含 dist"
    exit 1
fi

# ---------- 6. 重启后端 ----------
log "6/9 systemctl restart ${SERVICE_NAME}"
systemctl restart "${SERVICE_NAME}" || { err "systemctl restart 失败"; exit 1; }

# ---------- 7. reload nginx ----------
log "7/9 nginx -s reload"
nginx -t && systemctl reload nginx || { err "nginx reload 失败"; exit 1; }

# ---------- 8. 探活 ----------
log "8/9 健康检查 ${HEALTHCHECK_URL}"
# 等待 uvicorn 起来（首次启动会 alembic + 加载 LLM provider，给 60s）
ATTEMPTS=12
SLEEP=5
for i in $(seq 1 $ATTEMPTS); do
    if curl -fsS -m 3 "${HEALTHCHECK_URL}" >/dev/null 2>&1; then
        log "  ✅ healthz OK (attempt $i/${ATTEMPTS})"
        break
    fi
    if [[ $i -eq $ATTEMPTS ]]; then
        err "健康检查失败：${HEALTHCHECK_URL} 无响应"
        err "看日志：journalctl -xeu ${SERVICE_NAME}"
        err "回滚：sudo bash ${FOOD_ORDER_HOME}/scripts/rollback.sh ${TS}"
        exit 1
    fi
    log "  健康检查未就绪，等待 ${SLEEP}s (${i}/${ATTEMPTS})"
    sleep $SLEEP
done

# ---------- 9. 清理 ----------
log "9/9 清理临时文件"
rm -f "$TARBALL"

# 保留最近 5 个备份；老的删掉
ls -1dt "${FOOD_ORDER_HOME}".backup.* 2>/dev/null | tail -n +6 | xargs -r rm -rf

log "✅ 部署完成：${TS}"
log "   回滚：sudo bash ${FOOD_ORDER_HOME}/scripts/rollback.sh ${TS}"
