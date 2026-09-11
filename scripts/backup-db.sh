#!/usr/bin/env bash
# food-order · MySQL 备份脚本
#
# 用法：
#   sudo bash scripts/backup-db.sh
#
# 可覆盖默认 HOME（不传则用 /root/food-order）：
#   sudo FOOD_ORDER_HOME=/path/to/home bash scripts/backup-db.sh
#
# 读 ${FOOD_ORDER_HOME}/.env 里的 DB_* 变量
# 产出：/var/backups/food-order/db/food_order_<ts>.sql.gz
# 保留 7 天（老的删掉）
#
# 也被 /etc/cron.d/food-order-backup 每日 03:00 触发

set -euo pipefail

readonly FOOD_ORDER_HOME="${FOOD_ORDER_HOME:-/root/food-order}"
readonly BACKUP_DIR="/var/backups/food-order/db"
readonly ENV_FILE="${FOOD_ORDER_HOME}/.env"

if [[ $EUID -ne 0 ]]; then
    echo "[ERROR] 必须用 root 跑：sudo bash $0" >&2
    exit 1
fi

if [[ ! -r "$ENV_FILE" ]]; then
    echo "[ERROR] 读不到 $ENV_FILE" >&2
    exit 1
fi

log() { printf '\033[1;34m[backup]\033[0m %s\n' "$*"; }
err() { printf '\033[1;31m[ERROR]\033[0m %s\n' "$*" >&2; }

# 从 .env 读 DB_* 变量（仅 DB_ 前缀，避免泄漏 JWT_SECRET 之类）
declare -A DB
while IFS='=' read -r key value; do
    [[ "$key" =~ ^DB_ ]] || continue
    DB["$key"]="$value"
done < <(grep -E '^DB_[A-Z_]+=' "$ENV_FILE" || true)

: "${DB[DB_HOST]:=127.0.0.1}"
: "${DB[DB_PORT]:=3306}"
: "${DB[DB_USER]:=root}"
: "${DB[DB_NAME]:=food_order}"

# mysqldump 不接受密码在命令行；走 ~/.my.cnf 或环境变量
# 用 MYSQL_PWD（不写入 history）
export MYSQL_PWD="${DB[DB_PASSWORD]:-}"

install -d -m 0750 "$BACKUP_DIR"

TS="$(date -u +%Y%m%d_%H%M%S)"
OUT="${BACKUP_DIR}/${DB[DB_NAME]}_${TS}.sql.gz"

log "导出 ${DB[DB_NAME]} @ ${DB[DB_HOST]}:${DB[DB_PORT]} → ${OUT}"
mysqldump \
    --host="${DB[DB_HOST]}" \
    --port="${DB[DB_PORT]}" \
    --user="${DB[DB_USER]}" \
    --single-transaction \
    --quick \
    --routines \
    --triggers \
    --events \
    --default-character-set=utf8mb4 \
    "${DB[DB_NAME]}" \
    | gzip -9 \
    > "$OUT" \
    || { err "mysqldump 失败"; rm -f "$OUT"; exit 1; }

chmod 0640 "$OUT"
chown root:food-order "$OUT"

log "✅ 备份完成：$(du -h "$OUT" | cut -f1)"

# 清理 > 7 天的备份
DELETED=$(find "$BACKUP_DIR" -maxdepth 1 -name "${DB[DB_NAME]}_*.sql.gz" -mtime +7 -print -delete | wc -l)
log "清理 ${DELETED} 个 > 7 天的备份"

# 列出当前保留
log "当前备份："
ls -1lh "$BACKUP_DIR"/"${DB[DB_NAME]}"_*.sql.gz 2>/dev/null | tail -10 || true
