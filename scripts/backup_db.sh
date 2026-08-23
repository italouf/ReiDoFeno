#!/usr/bin/env bash
# Backup do PostgreSQL (executado por cron; retenção local 7 dias).
# Uso: ./scripts/backup_db.sh "$DATABASE_URL" /caminho/da/pasta
set -euo pipefail

DATABASE_URL="${1:?Informe DATABASE_URL}"
DESTINO="${2:-./backups}"

mkdir -p "$DESTINO"
ARQUIVO="$DESTINO/reidofeno-$(date +%Y%m%d-%H%M%S).sql.gz"

pg_dump --no-owner --no-privileges "$DATABASE_URL" | gzip > "$ARQUIVO"
echo "Backup gerado: $ARQUIVO"

# Retenção local de 7 dias
find "$DESTINO" -name 'reidofeno-*.sql.gz' -mtime +7 -delete

# Opcional: enviar ao storage externo (S3/R2)
# aws s3 cp "$ARQUIVO" "s3://SEU-BUCKET/backups/" --sse AES256
