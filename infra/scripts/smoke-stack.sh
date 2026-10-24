#!/usr/bin/env bash
# Smoke destrutivo, limitado ao projeto descartável "reidofeno_smoke".
# Nunca opera no projeto de desenvolvimento "reidofeno".
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$RAIZ"

BASE="infra/docker-compose.yml"
SMOKE="infra/docker-compose.smoke.yml"
ENV_SMOKE="infra/.env.smoke"
ENV_DOCKER_SMOKE=".env.docker.smoke"
PROJETO_SMOKE="${SMOKE_PROJECT_NAME:-reidofeno_smoke}"
SERVICOS_RUNTIME=(caddy web db redis cron)

erro() {
    echo "ERRO: $*" >&2
    exit 1
}

case "$PROJETO_SMOKE" in
    reidofeno|"")
        erro "projeto de smoke não pode ser 'reidofeno' (projeto de desenvolvimento)"
        ;;
    *[!a-z0-9_-]*|*[A-Z]*)
        erro "nome de projeto inválido para smoke: $PROJETO_SMOKE"
        ;;
esac

[ -f "$ENV_SMOKE" ] \
    || erro "ausente: $ENV_SMOKE (copie de infra/.env.smoke.example)"
[ -f "$ENV_DOCKER_SMOKE" ] \
    || erro "ausente: $ENV_DOCKER_SMOKE (copie de .env.docker.smoke.example)"

# Exclusão mútua do projeto fixo: uma segunda execução do smoke (manual ou
# pelo harness) não pode interromper a primeira.
SMOKE_LOCK_DIR="${SMOKE_LOCK_DIR:-${TMPDIR:-/tmp}/${PROJETO_SMOKE}.lock}"
if ! mkdir "$SMOKE_LOCK_DIR" 2>/dev/null; then
    erro "smoke já está em execução para o projeto $PROJETO_SMOKE"
fi
trap 'rmdir "$SMOKE_LOCK_DIR" >/dev/null 2>&1 || true' EXIT

# Força valores isolados; variáveis herdadas do shell não podem redirecionar
# o smoke para credenciais/portas/arquivos do desenvolvimento.
export APP_ENV_FILE=.env.docker.smoke
export DB_PASSWORD=smoke-only
export APP_DOMAIN=localhost
export STAGING_DOMAIN=staging.localhost
export ACME_EMAIL=admin@example.invalid
export HSTS_MAX_AGE=0
export CADDY_HTTP_PORT=8080
export CADDY_HTTPS_PORT=8443
PORTA_HTTPS=8443

COMPOSE=(
    docker compose
    --project-name "$PROJETO_SMOKE"
    --env-file "$ENV_SMOKE"
    -f "$BASE"
    -f "$SMOKE"
)

compose() {
    "${COMPOSE[@]}" "$@"
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

# Recusa antes da primeira mutação se o modelo não estiver isolado.
validar_isolamento() {
    local config volume
    config="$(compose config)"

    case "$config" in
        *"name: $PROJETO_SMOKE"*) ;;
        *) erro "modelo Compose não usa o projeto $PROJETO_SMOKE" ;;
    esac

    for volume in pgdata redisdata caddy_data caddy_config media; do
        case "$config" in
            *"name: ${PROJETO_SMOKE}_${volume}"*) ;;
            *) erro "volume $volume não está isolado no projeto $PROJETO_SMOKE" ;;
        esac
        case "$config" in
            *"name: reidofeno_${volume}"*)
                erro "volume de desenvolvimento detectado no smoke: reidofeno_${volume}"
                ;;
        esac
    done

    case "$config" in
        *'published: "8080"'*) ;;
        *) erro "porta HTTP de smoke 8080 não está publicada" ;;
    esac
    case "$config" in
        *'published: "8443"'*) ;;
        *) erro "porta HTTPS de smoke 8443 não está publicada" ;;
    esac

    echo "ISOLAMENTO_OK projeto=$PROJETO_SMOKE"
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
    local caminho="$1"
    shift
    curl --noproxy '*' -kfsS \
        --resolve "localhost:${PORTA_HTTPS}:127.0.0.1" \
        "https://localhost:${PORTA_HTTPS}${caminho}" "$@"
}

curl_headers() {
    local caminho="$1"
    curl --noproxy '*' -kfsS -I \
        --resolve "localhost:${PORTA_HTTPS}:127.0.0.1" \
        "https://localhost:${PORTA_HTTPS}${caminho}"
}

nome_rede_front() {
    local redes nome
    redes="$(docker inspect -f \
        '{{range $nome, $_ := .NetworkSettings.Networks}}{{$nome}} {{end}}' "$1")"
    for nome in $redes; do
        case "$nome" in
            *_front)
                printf '%s' "$nome"
                return 0
                ;;
        esac
    done
    return 1
}

ip_na_rede() {
    docker inspect -f \
        '{{(index .NetworkSettings.Networks "'"$2"'").IPAddress}}' "$1"
}

extrair_ip() {
    printf '%s' "$1" |
        sed -n 's/.*"remote_addr": *"\([^"]*\)".*/\1/p'
}

validar_isolamento

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

if [ "${SMOKE_TEST_FAIL_AFTER_SEED:-}" = "1" ]; then
    falhar "falha deliberada para teste de isolamento"
fi

echo "== HTTPS, página representativa e estático =="
healthz="$(curl_local /healthz/)"
case "$healthz" in
    *'"status": "ok"'*) ;;
    *) falhar "healthz não respondeu 200" ;;
esac

html="$(curl_local /)"
case "$html" in
    *"Feno Smoke"*) ;;
    *) falhar "produto sintético não apareceu na vitrine" ;;
esac

static_url="$(printf '%s' "$html" | grep -oE '/static/[^" ]+\.css' | head -n1 || true)"
[ -n "$static_url" ] || falhar "CSS com hash não encontrado no HTML"

headers="$(curl_headers "$static_url")"
grep -qi '^content-type: text/css' <<< "$headers" \
    || falhar "estático não retornou text/css: $static_url"
static_body="$(curl_local "$static_url")"
[ -n "$static_body" ] || falhar "estático vazio: $static_url"

echo "== SEC-03: REMOTE_ADDR real e X-Forwarded-For forjado =="
caddy_id="$(compose ps -q caddy)"
web_id="$(compose ps -q web)"
cron_id="$(compose ps -q cron)"
[ -n "$caddy_id" ] || falhar "container do Caddy não encontrado"
[ -n "$web_id" ] || falhar "container web não encontrado"
[ -n "$cron_id" ] || falhar "container cron não encontrado"

rede_front="$(nome_rede_front "$web_id")" \
    || falhar "rede front do web não encontrada"
[ "$(nome_rede_front "$cron_id")" = "$rede_front" ] \
    || falhar "web e cron não compartilham a rede front"
[ "$(nome_rede_front "$caddy_id")" = "$rede_front" ] \
    || falhar "Caddy não está na rede front"

caddy_ip="$(ip_na_rede "$caddy_id" "$rede_front")"
web_ip="$(ip_na_rede "$web_id" "$rede_front")"
cron_ip="$(ip_na_rede "$cron_id" "$rede_front")"
[ -n "$caddy_ip" ] || falhar "IP do Caddy não encontrado"
[ -n "$web_ip" ] || falhar "IP do web não encontrado"
[ -n "$cron_ip" ] || falhar "IP do cron não encontrado"

resposta_web="$(compose exec -T web curl --noproxy '*' -kfsS \
    --resolve "localhost:443:$caddy_ip" \
    -H 'X-Forwarded-For: 203.0.113.99' \
    "https://localhost/healthz/ip/")"
resposta_cron="$(compose exec -T cron curl --noproxy '*' -kfsS \
    --resolve "localhost:443:$caddy_ip" \
    "https://localhost/healthz/ip/")"

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
    local saida
    saida="$(compose exec -T web python manage.py shell --verbosity 0 -c \
        "from catalog.models import Produto; print(Produto.objects.filter(nome='Feno Smoke').count())")" \
        || return 1
    printf '%s' "$saida"
}

[ "$(contar_produto)" = "1" ] || falhar "produto sintético não existe antes do restart"

compose_cron down
compose_cron up -d --no-build
esperar_saudavel "${SERVICOS_RUNTIME[@]}"

[ "$(contar_produto)" = "1" ] || falhar "dados não persistiram após recriar containers"
[ "$(compose exec -T web sh -c 'cat /app/media/smoke.txt')" = "smoke-media" ] \
    || falhar "arquivo de mídia não persistiu"
html_depois="$(curl_local /)"
case "$html_depois" in
    *"Feno Smoke"*) ;;
    *) falhar "página não voltou após recriar containers" ;;
esac

echo "SMOKE_OK"
compose_cron down -v --remove-orphans
