#!/bin/bash
# Ежедневный бэкап SQLite базы бота.
# Запускается из cron под юзером `bible`. Использует `sqlite3 .backup` —
# WAL-safe online backup, не блокирует работающий бот.
#
# Установка (под юзером bible):
#   crontab -e
#   0 3 * * * /home/bible/bible_bot/deploy/backup.sh >> /home/bible/backups/backup.log 2>&1

set -euo pipefail

DB_PATH="/home/bible/bible_bot/bot.db"
BACKUP_DIR="/home/bible/backups"
RETENTION_DAYS=30

mkdir -p "$BACKUP_DIR"

STAMP=$(date +%F_%H%M)
DEST="$BACKUP_DIR/bot-${STAMP}.db"

# Online-backup через sqlite3 (безопасно при работающем боте, WAL-aware).
sqlite3 "$DB_PATH" ".backup '$DEST'"

# Сжимаем (экономит ~70%)
gzip -f "$DEST"

# Чистка старых: удаляем бэкапы старше RETENTION_DAYS дней.
find "$BACKUP_DIR" -name 'bot-*.db.gz' -mtime "+$RETENTION_DAYS" -delete

echo "[$(date +%F\ %T)] backup ok → ${DEST}.gz ($(du -h "${DEST}.gz" | cut -f1))"
