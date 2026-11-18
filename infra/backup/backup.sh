#!/usr/bin/env bash
set -euo pipefail

# ─────────────────────────────────────────────────────────────
# Backup noturno do ReiDoFeno
# - Dump PostgreSQL (formato custom -Fc + pg_restore --list)
# - Mídia (volume Docker `media` ou bind-mount local)
# - Configuração crítica (criptografada com age)
# - Retenção local (7 diários)
# - Upload para Cloudflare R2 ou Backblaze B2 via rclone + checksum SHA-256
# ─────────────────────────────────────────────────────────────

DRY_RUN=0
for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=1 ;;
        *)
            echo "Argumento desconhecido: $arg" >&2
            exit 1
            ;;
    esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="${PROJECT_DIR:-/opt/reidofeno}"
COMPOSE_FILE="${COMPOSE_FILE:-$PROJECT_DIR/infra/docker-compose.yml}"
STAMP="${BACKUP_STAMP:-$(date +%F_%H%M)}"
BACKUP_LOCAL="${BACKUP_LOCAL:-/var/backups/reidofeno}"
if [ "$DRY_RUN" -eq 1 ] && [ "${BACKUP_LOCAL}" = "/var/backups/reidofeno" ]; then
    BACKUP_LOCAL="/tmp/backup-test"
fi
BACKUP_LOG="${BACKUP_LOG:-/var/log/reidofeno/backup.log}"
RCLONE_REMOTE="${BACKUP_REMOTE:-b2:reidofeno-backups}"
PG_USER="${BACKUP_PG_USER:-reidofeno}"
PG_DB="${BACKUP_PG_DB:-reidofeno}"

mkdir -p "$BACKUP_LOCAL" "$(dirname "$BACKUP_LOG")"

CONFIG_TAR=""
cleanup() {
    if [ -n "$CONFIG_TAR" ] && [ -f "$CONFIG_TAR" ]; then
        rm -f "$CONFIG_TAR" || true
    fi
}
trap cleanup EXIT

log() {
    printf '[%s] %s\n' "$(date '+%F %T')" "$*" | tee -a "$BACKUP_LOG"
}

fail() {
    local reason="$*"
    log "CRITICAL: BACKUP_FAILED: $reason"
    if [ "$DRY_RUN" -eq 0 ] && command -v docker >/dev/null 2>&1 && [ -f "$COMPOSE_FILE" ]; then
        docker compose -f "$COMPOSE_FILE" exec -T web \
            python manage.py reportar_backup_falha --motivo "$reason" >/dev/null 2>&1 || true
    fi
    exit 1
}

if [ "$DRY_RUN" -eq 1 ]; then
    DB_FILE="$BACKUP_LOCAL/db.dump"
    MEDIA_FILE="$BACKUP_LOCAL/media.tar.gz"
    CONFIG_TAR="$BACKUP_LOCAL/config.tar.gz"
    CONFIG_AGE="$BACKUP_LOCAL/config.tar.gz.age"
else
    DB_FILE="$BACKUP_LOCAL/db-$STAMP.dump"
    MEDIA_FILE="$BACKUP_LOCAL/media-$STAMP.tar.gz"
    CONFIG_TAR="$BACKUP_LOCAL/config-$STAMP.tar.gz"
    CONFIG_AGE="$BACKUP_LOCAL/config-$STAMP.tar.gz.age"
fi

# 1. Dump PostgreSQL
log "Iniciando dump PostgreSQL..."
docker compose -f "$COMPOSE_FILE" exec -T db \
    pg_dump -U "$PG_USER" -Fc "$PG_DB" \
    > "$DB_FILE" \
    || fail "pg_dump_failed"

[ -s "$DB_FILE" ] || fail "dump_vazio"
pg_restore --list "$DB_FILE" > /dev/null \
    || fail "dump_invalido"

# 2. Mídia (prefere container web/volume; fallback para diretório host)
log "Arquivando mídia..."
if [ -d "$PROJECT_DIR/media" ] && [ "${BACKUP_MEDIA_SOURCE:-auto}" = "host" ]; then
    tar -czf "$MEDIA_FILE" -C "$PROJECT_DIR" media \
        || fail "tar_media_failed"
else
    if docker compose -f "$COMPOSE_FILE" exec -T web \
        tar -cz -C /app media > "$MEDIA_FILE" 2>/dev/null; then
        :
    elif [ -d "$PROJECT_DIR/media" ]; then
        tar -czf "$MEDIA_FILE" -C "$PROJECT_DIR" media \
            || fail "tar_media_failed"
    else
        fail "media_source_unavailable"
    fi
fi

# 3. Configuração crítica (criptografada com age)
log "Arquivando configuração..."
CONFIG_FILES=()
for rel in .env .env.docker infra/.env infra/docker-compose.yml infra/Caddyfile infra/transport.caddy infra/crontab; do
    if [ -f "$PROJECT_DIR/$rel" ]; then
        CONFIG_FILES+=("$rel")
    fi
done
[ "${#CONFIG_FILES[@]}" -gt 0 ] || fail "no_config_files_found"

tar -czf "$CONFIG_TAR" -C "$PROJECT_DIR" "${CONFIG_FILES[@]}" \
    || fail "tar_config_failed"

if [ -n "${BACKUP_AGE_RECIPIENT:-}" ]; then
    age -r "$BACKUP_AGE_RECIPIENT" -o "$CONFIG_AGE" "$CONFIG_TAR" \
        || fail "age_encryption_failed"
    rm -f "$CONFIG_TAR"
    CONFIG_TAR=""
elif [ "$DRY_RUN" -eq 1 ] && command -v age-keygen >/dev/null 2>&1; then
    EPHEMERAL_KEY="$BACKUP_LOCAL/.dry-run-age.key"
    age-keygen -o "$EPHEMERAL_KEY" >/dev/null 2>&1 || fail "age_keygen_failed"
    RECIPIENT="$(grep -o 'age1[a-z0-9]*' "$EPHEMERAL_KEY" | head -n1)"
    age -r "$RECIPIENT" -o "$CONFIG_AGE" "$CONFIG_TAR" \
        || fail "age_encryption_failed"
    rm -f "$CONFIG_TAR" "$EPHEMERAL_KEY"
    CONFIG_TAR=""
else
    fail "backup_age_recipient_missing"
fi

# 4. Retenção local
if [ "$DRY_RUN" -eq 0 ]; then
    log "Aplicando retenção local..."
    RETENTION_BIN="${RETENTION_SCRIPT:-$SCRIPT_DIR/apply-retention.sh}"
    bash "$RETENTION_BIN" "$BACKUP_LOCAL" || fail "retention_failed"
fi

# 5. Upload offsite + verificação SHA-256
if [ "$DRY_RUN" -eq 0 ] && [ "${BACKUP_OFFSITE:-true}" != "false" ]; then
    log "Enviando para $RCLONE_REMOTE/$STAMP/..."
    CHECKSUM_LOCAL="$(sha256sum "$DB_FILE" | cut -d' ' -f1)"

    rclone copy "$BACKUP_LOCAL" "$RCLONE_REMOTE/$STAMP/" \
        --transfers 4 --checkers 8 \
        || fail "rclone_upload_failed"

    CHECKSUM_REMOTE="$(rclone cat "$RCLONE_REMOTE/$STAMP/$(basename "$DB_FILE")" \
        | sha256sum | cut -d' ' -f1)" \
        || fail "rclone_verify_failed"

    [ "$CHECKSUM_LOCAL" = "$CHECKSUM_REMOTE" ] \
        || fail "checksum_mismatch"
fi

log "SUCCESS: backup completo ($STAMP)"
