#!/usr/bin/env bash
# Retenção local: mantém últimos 7 dias de dumps, mídias e configs criptografadas.
# Semanais (4) e mensais (3/12) são gerenciados pela política de lifecycle offsite (R2/B2).
set -euo pipefail

DIR="${1:-/var/backups/reidofeno}"
RETENTION_DAYS="${BACKUP_LOCAL_RETENTION_DAYS:-7}"

if [ ! -d "$DIR" ]; then
    echo "Diretório de backup inexistente: $DIR" >&2
    exit 1
fi

find "$DIR" -maxdepth 1 -type f -name 'db-*.dump' -mtime +"$RETENTION_DAYS" -delete
find "$DIR" -maxdepth 1 -type f -name 'media-*.tar.gz' -mtime +"$RETENTION_DAYS" -delete
find "$DIR" -maxdepth 1 -type f -name 'config-*.tar.gz.age' -mtime +"$RETENTION_DAYS" -delete
