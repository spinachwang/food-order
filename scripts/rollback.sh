#!/usr/bin/env bash
# food-order · 回滚脚本
#
# 用法：
#   sudo bash scripts/rollback.sh                    # 列出可回滚的版本
#   sudo bash scripts/rollback.sh <timestamp>        # 回滚到指定版本
#
# 例：sudo bash scripts/rollback.sh 20260909_210000
#
# 流程：
#   1. 校验 timestamp 存在 /opt/food-order.backup.<ts>/
#   2. 备份当前版本（防止回滚失败后无法再次回滚）
#   3. 覆盖 /opt/food-order/ ← /opt/food-order.backup.<ts>/
#   4. alembic downgrade -1（如果新版本已经升级过迁移）
#   5. 重启 systemd + reload nginx
#   6. 健康检查

set -euo pipefail

readonly FOOD_ORDER_HOME="/opt/food-order"
readonly SERVICE_NAME="food-order-backend.service"
readonly HEALTHCHECK_URL="http://127.0.0.1:8000/healthz"

if [[ $EUID -ne 0 ]]; then
    echo "[ERROR] 必须用 root 跑：sudo bash $0 [timestamp]" >&2
    exit 1
fi

log() { printf '\033[1;34m[rollback]\033[0m %s\n' "$*"; }
err() { printf '\033[1;31m[ERROR]\033[0m %s\n' "$*" >&2; }

# ---------- 1. 无参：列出可回滚版本 ----------
if [[ $# -eq 0 ]]; then
    log "可回滚版本（最新在前）："
    ls -1dt "${FOOD_ORDER_HOME}".backup.* 2>/dev/null || {
        log "  没有可回滚的备份"
        exit 0
    }
    log ""
    log "回滚：sudo bash $0 <timestamp>"
    exit 0
fi

TS="$1"
TARGET="${FOOD_ORDER_HOME}.backup.${TS}"

if [[ ! -d "$TARGET" ]]; then
    err "备份目录不存在: $TARGET"
    err "  跑 'sudo bash $0' 查看可回滚版本"
    exit 1
fi

# ---------- 2. 备份当前版本（双保险） ----------
NOW_TS="$(date -u +%Y%m%d_%H%M%S)"
SAFETY_BACKUP="${FOOD_ORDER_HOME}.backup.${NOW_TS}_pre_rollback"
log "2/5 备份当前版本 → ${SAFETY_BACKUP}/"
rsync -a --exclude='*.pyc' --exclude='__pycache__' \
    --exclude='.pytest_cache' --exclude='.venv' --exclude='venv' \
    --exclude='node_modules' --exclude='dist' \
    "${FOOD_ORDER_HOME}/" "${SAFETY_BACKUP}/" \
    || { err "安全备份失败"; exit 1; }

# ---------- 3. 覆盖 ----------
log "3/5 覆盖 ${FOOD_ORDER_HOME}/ ← ${TARGET}/"
rsync -a --delete --exclude='.env' "${TARGET}/" "${FOOD_ORDER_HOME}/" \
    || { err "覆盖失败；当前版本已备份在 ${SAFETY_BACKUP}/"; exit 1; }
chown -R food-order:food-order "${FOOD_ORDER_HOME}" || true

# ---------- 4. alembic ----------
log "4/5 alembic downgrade -1（如果新版本已经升过迁移）"
# 注意：downgrade -1 是相对当前 head。如果备份版本和现在 head 不同，
# 这里假设备份版本是"上一稳定版"，尝试 downgrade 一级。
# 如果 backup 版本本身就是当前 head，downgrade 会失败但不影响功能（schema 已就位）。
sudo -u food-order bash -c "
    source /opt/conda/etc/profile.d/conda.sh
    conda activate food-order
    cd '${FOOD_ORDER_HOME}/backend'
    alembic current
    # 尝试 downgrade -1；失败不致命
    alembic downgrade -1 || true
" || true

# ---------- 5. 重启 + 探活 ----------
log "5/5 重启 + 健康检查"
systemctl restart "${SERVICE_NAME}" || { err "systemctl restart 失败"; exit 1; }
nginx -t && systemctl reload nginx || { err "nginx reload 失败"; exit 1; }

ATTEMPTS=12
SLEEP=5
for i in $(seq 1 $ATTEMPTS); do
    if curl -fsS -m 3 "${HEALTHCHECK_URL}" >/dev/null 2>&1; then
        log "  ✅ healthz OK (attempt $i/${ATTEMPTS})"
        break
    fi
    if [[ $i -eq $ATTEMPTS ]]; then
        err "回滚后健康检查失败：${HEALTHCHECK_URL}"
        err "  journalctl -xeu ${SERVICE_NAME}"
        exit 1
    fi
    log "  健康检查未就绪，等待 ${SLEEP}s (${i}/${ATTEMPTS})"
    sleep $SLEEP
done

# 保留最近 5 个备份
ls -1dt "${FOOD_ORDER_HOME}".backup.* 2>/dev/null | tail -n +6 | xargs -r rm -rf

log "✅ 回滚完成：${TS}"
log "   当前版本：${FOOD_ORDER_HOME}/"
log "   上一个版本（pre_rollback）：${SAFETY_BACKUP}/"
