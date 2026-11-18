#!/usr/bin/env bash
set -euo pipefail

# ─────────────────────────────────────────────────────────────
# Restore automatizado do ReiDoFeno (DRILL / Disaster Recovery)
# Uso:
#   ./restore.sh --dump <file> --media <file> [--config <file> --config-key <key>] --target <dir>
# ─────────────────────────────────────────────────────────────

DUMP=""
MEDIA=""
CONFIG=""
CONFIG_KEY=""
TARGET=""

while [ $# -gt 0 ]; do
    case "$1" in
        --dump) DUMP="$2"; shift 2 ;;
        --media) MEDIA="$2"; shift 2 ;;
        --config) CONFIG="$2"; shift 2 ;;
        --config-key) CONFIG_KEY="$2"; shift 2 ;;
        --target) TARGET="$2"; shift 2 ;;
        *)
            echo "Argumento desconhecido: $1" >&2
            exit 1
            ;;
    esac
done

[ -n "$DUMP" ] && [ -f "$DUMP" ] || { echo "Dump não encontrado: $DUMP" >&2; exit 1; }
[ -n "$MEDIA" ] && [ -f "$MEDIA" ] || { echo "Mídia não encontrada: $MEDIA" >&2; exit 1; }
[ -n "$TARGET" ] || { echo "Informe --target <dir>" >&2; exit 1; }

if command -v pg_restore >/dev/null 2>&1; then
    pg_restore --list "$DUMP" >/dev/null || { echo "Dump inválido: $DUMP" >&2; exit 1; }
fi

mkdir -p "$TARGET"

CONTAINER_NAME="reidofeno-restore-db-$$"
CONFIG_TAR_TMP=""
cleanup() {
    if [ -n "$CONFIG_TAR_TMP" ] && [ -f "$CONFIG_TAR_TMP" ]; then
        rm -f "$CONFIG_TAR_TMP" || true
    fi
    docker stop "$CONTAINER_NAME" >/dev/null 2>&1 || true
}
trap cleanup EXIT

# 1. Restaurar mídia
echo "Restaurando mídia em $TARGET..."
tar -xzf "$MEDIA" -C "$TARGET"

# 2. Descriptografar e restaurar configuração (se fornecida)
if [ -n "$CONFIG" ]; then
    [ -f "$CONFIG" ] || { echo "Config não encontrada: $CONFIG" >&2; exit 1; }
    [ -n "$CONFIG_KEY" ] && [ -f "$CONFIG_KEY" ] || {
        echo "Chave age (--config-key) obrigatória para descriptografar $CONFIG" >&2
        exit 1
    }
    echo "Descriptografando configuração..."
    CONFIG_TAR_TMP="$TARGET/config.tar.gz"
    age --decrypt -i "$CONFIG_KEY" -o "$CONFIG_TAR_TMP" "$CONFIG"
    tar -xzf "$CONFIG_TAR_TMP" -C "$TARGET"
    rm -f "$CONFIG_TAR_TMP"
    CONFIG_TAR_TMP=""
fi

# 3. Subir PostgreSQL temporário e restaurar dump
DUMP_ABS="$(cd "$(dirname "$DUMP")" && pwd)/$(basename "$DUMP")"
echo "Subindo PostgreSQL temporário ($CONTAINER_NAME)..."
docker run --rm -d --name "$CONTAINER_NAME" \
    -e POSTGRES_DB=reidofeno \
    -e POSTGRES_USER=reidofeno \
    -e POSTGRES_PASSWORD=restore_temp \
    -v "$DUMP_ABS:/dump.dump:ro" \
    postgres:15-alpine >/dev/null

for _ in $(seq 1 30); do
    if docker exec "$CONTAINER_NAME" pg_isready -U reidofeno -d reidofeno >/dev/null 2>&1; then
        break
    fi
    sleep 1
done

echo "Restaurando dump PostgreSQL..."
docker exec -i "$CONTAINER_NAME" pg_restore \
    -U reidofeno -d reidofeno --no-owner --no-acl /dump.dump

echo "Validando contagens básicas..."
docker exec "$CONTAINER_NAME" psql -U reidofeno -d reidofeno -c \
    "SELECT 'Pedidos: ' || count(*) FROM sales_pedido
     UNION ALL
     SELECT 'Clientes: ' || count(*) FROM customers_cliente
     UNION ALL
     SELECT 'Movimentos: ' || count(*) FROM stock_movimentoestoque
     UNION ALL
     SELECT 'Notas: ' || count(*) FROM fiscal_notafiscal;"

echo "Restore concluído em: $TARGET"
echo "Próximo passo: subir a stack com o volume restaurado e executar 'python manage.py validar_restore'."
