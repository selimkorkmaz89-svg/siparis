#!/bin/sh
# Daily PostgreSQL backup. Add to the host crontab, e.g.:
#   0 2 * * * /opt/siparis/docker/backup.sh >> /var/log/siparis-backup.log 2>&1
set -eu

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BACKUP_DIR="${BACKUP_DIR:-$PROJECT_DIR/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"
STAMP="$(date +%Y%m%d-%H%M%S)"

mkdir -p "$BACKUP_DIR"
cd "$PROJECT_DIR"

# shellcheck disable=SC1091
[ -f .env ] && . ./.env

docker compose exec -T db pg_dump -U "${POSTGRES_USER:-siparis}" "${POSTGRES_DB:-siparis}" \
    | gzip > "$BACKUP_DIR/db-$STAMP.sql.gz"

# Uploaded receipts and profile photos.
docker compose run --rm -T web tar -czf - -C /app media > "$BACKUP_DIR/media-$STAMP.tar.gz"

find "$BACKUP_DIR" -name 'db-*.sql.gz' -mtime "+$RETENTION_DAYS" -delete
find "$BACKUP_DIR" -name 'media-*.tar.gz' -mtime "+$RETENTION_DAYS" -delete

echo "Backup completed: $BACKUP_DIR/db-$STAMP.sql.gz"
