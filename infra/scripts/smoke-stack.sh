#!/usr/bin/env bash
# Smoke destrutivo e limitado ao projeto Compose "reidofeno".
# Requer .env.docker e infra/.env (copiados dos exemplos) e a imagem runtime.
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$RAIZ"

BASE="infra/docker-compose.yml"
SMOKE="infra/docker-compose.smoke.yml"
OVERRIDE="infra/docker-compose.override.yml"
FRONT="reidofeno_front"
SERVICOS_RUNTIME=(caddy web db redis cron)

compose() {
    docker compose -f "$BASE" -f "$SMOKE" "$@"
}

compose_cron() {
    compose --profile cron "$@"
}

falhar() {
    echo "ERRO: $*" >&2
    compose_cron ps || true
    compose_cron logs --no-color --tail=150 || true
    exit 1
}

esperar_saudavel() {
    local servicos=("$@")
    local tentativa servico ok cid status
    for tentativa in $(seq 1 90); do
        ok=1
        for servico in "${servicos[@]}"; do
            cid="$(compose_cron ps -q "$servico" || true)"
            if [ -z "$cid" ]; then
                ok=0
                break
            fi
            status="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$cid")"
            if [ "$status" != "healthy" ]; then
                ok=0
                break
            fi
        done
        if [ "$ok" -eq 1 ]; then
            return 0
        fi
        sleep 2
    done
    falhar "serviços não ficaram saudáveis: ${servicos[*]}"
}

curl_local() {
    curl --noproxy '*' -kfsS --resolve localhost:443:127.0.0.1 "$@"
}

ip_da_rede_front() {
    docker inspect -f '{{(index .NetworkSettings.Networks "'"$FRONT"'").IPAddress}}' "$1"
}

extrair_ip() {
    printf '%s' "$1" | sed -n 's/.*"remote_addr": *"\([^"]*\)".*/\1/p'
}

echo "== subindo stack runtime + cron =="
compose_cron up -d --no-build
esperar_saudavel "${SERVICOS_RUNTIME[@]}"

echo "== dados sintéticos =="
compose exec -T web python manage.py shell -c '
from core.models import Unidade
from catalog.models import Categoria, Produto

Unidade.objects.get_or_create(
    nome="Feira de Santana",
    defaults={"cidade": "Feira de Santana", "uf": "BA"},
)
Unidade.objects.get_or_create(
    nome="Iaçu",
    defaults={"cidade": "Iaçu", "uf": "BA"},
)
categoria, _ = Categoria.objects.get_or_create(nome="SMOKE-CATEGORIA")
Produto.objects.get_or_create(
    nome="Feno Smoke",
    defaults={
        "categoria": categoria,
        "unidade_medida": "fardo",
        "custo": 1,
        "preco_balcao": 2,
        "preco_online": 3,
    },
)
print("SMOKE_SEED_OK")
' || falhar "seed sintético falhou"
compose exec -T -e ALLOW_DEMO_SEED=1 web python manage.py semear_estoque_demo \
    || falhar "semeadura de estoque demo falhou"

echo "== HTTPS, página representativa e estático =="
healthz="$(curl_local https://localhost/healthz/)"
case "$healthz" in
    *'"status": "ok"'*) ;;
    *) falhar "healthz não respondeu 200" ;;
esac

html="$(curl_local https://localhost/)"
case "$html" in
    *"Feno Smoke"*) ;;
    *) falhar "produto sintético não apareceu na vitrine" ;;
esac

static_url="$(printf '%s' "$html" | grep -oE '/static/[^" ]+\.css' | head -n1 || true)"
[ -n "$static_url" ] || falhar "CSS com hash não encontrado no HTML"

headers="$(curl_local -I "https://localhost$static_url")"
grep -qi '^content-type: text/css' <<< "$headers" \
    || falhar "estático não retornou text/css: $static_url"
static_body="$(curl_local "https://localhost$static_url")"
[ -n "$static_body" ] || falhar "estático vazio: $static_url"

echo "== SEC-03: REMOTE_ADDR real e X-Forwarded-For forjado =="
caddy_id="$(compose ps -q caddy)"
caddy_ip="$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "$caddy_id")"
[ -n "$caddy_ip" ] || falhar "IP do Caddy não encontrado"

web_id="$(compose ps -q web)"
cron_id="$(compose ps -q cron)"
web_ip="$(ip_da_rede_front "$web_id")"
cron_ip="$(ip_da_rede_front "$cron_id")"
[ -n "$web_ip" ] || falhar "IP do web não encontrado"
[ -n "$cron_ip" ] || falhar "IP do cron não encontrado"

resposta_web="$(compose exec -T web curl --noproxy '*' -kfsS \
    --resolve "localhost:443:$caddy_ip" \
    -H 'X-Forwarded-For: 203.0.113.99' \
    https://localhost/healthz/ip/)"
resposta_cron="$(compose exec -T cron curl --noproxy '*' -kfsS \
    --resolve "localhost:443:$caddy_ip" \
    https://localhost/healthz/ip/)"

ip_web="$(extrair_ip "$resposta_web")"
ip_cron="$(extrair_ip "$resposta_cron")"
[ -n "$ip_web" ] || falhar "web não retornou remote_addr"
[ -n "$ip_cron" ] || falhar "cron não retornou remote_addr"
[ "$ip_web" = "$web_ip" ] || falhar "web: esperado $web_ip, recebido $ip_web"
[ "$ip_cron" = "$cron_ip" ] || falhar "cron: esperado $cron_ip, recebido $ip_cron"
[ "$ip_web" != "$ip_cron" ] || falhar "origens distintas tiveram o mesmo REMOTE_ADDR"
[ "$ip_web" != "203.0.113.99" ] || falhar "X-Forwarded-For forjado foi aceito"

echo "== cron: PID 1 e rotinas versionadas =="
pid1="$(compose_cron exec -T cron sh -c 'tr "\000" " " < /proc/1/cmdline')"
case "$pid1" in
    *supercronic*) ;;
    *) falhar "supercronic não é o PID 1 do cron" ;;
esac

for comando in expirar_pedidos processar_fiscal gerar_avisos_comerciais; do
    echo "executando $comando"
    compose_cron exec -T \
        -e MERCADO_PAGO_FAKE=True \
        -e BLING_FAKE=True \
        -e MERCADOPAGO_LIVE_MODE=False \
        -e EMAIL_BACKEND=django.core.mail.backends.locmem.EmailBackend \
        cron python manage.py "$comando" \
        || falhar "rotina $comando falhou"
done

echo "== persistência de dados e mídia =="
compose exec -T web sh -c 'printf "smoke-media" > /app/media/smoke.txt'

contar_produto() {
    compose exec -T web python manage.py shell -c \
        "from catalog.models import Produto; print(Produto.objects.filter(nome='Feno Smoke').count())"
}

[ "$(contar_produto)" = "1" ] || falhar "produto sintético não existe antes do restart"

compose_cron down
compose_cron up -d --no-build
esperar_saudavel "${SERVICOS_RUNTIME[@]}"

[ "$(contar_produto)" = "1" ] || falhar "dados não persistiram após recriar containers"
[ "$(compose exec -T web sh -c 'cat /app/media/smoke.txt')" = "smoke-media" ] \
    || falhar "arquivo de mídia não persistiu"
html_depois="$(curl_local https://localhost/)"
case "$html_depois" in
    *"Feno Smoke"*) ;;
    *) falhar "página não voltou após recriar containers" ;;
esac

echo "SMOKE_OK"
compose_cron down -v --remove-orphans
