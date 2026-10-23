#!/bin/sh
# Entrypoint único para web, cron e comandos avulsos (`docker compose run`).
set -eu

if [ -n "${DATABASE_URL:-}" ]; then
    echo "Aguardando PostgreSQL..."
    python - <<'PY'
import os
import sys
import time

import psycopg

url = os.environ["DATABASE_URL"]

for tentativa in range(1, 31):
    try:
        with psycopg.connect(url, connect_timeout=3):
            print("PostgreSQL pronto.")
            break
    except psycopg.OperationalError as exc:
        # Nunca imprime a URL (pode conter senha).
        print(f"Tentativa {tentativa}/30 falhou: {type(exc).__name__}")
        time.sleep(1)
else:
    print("ERRO: PostgreSQL não respondeu em 30s.", file=sys.stderr)
    sys.exit(1)
PY
fi

if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
    echo "Executando migrations..."
    python manage.py migrate --noinput
fi

exec "$@"
