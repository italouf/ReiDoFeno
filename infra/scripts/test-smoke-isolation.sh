#!/usr/bin/env bash
# Prova que o smoke não toca em recursos do projeto de desenvolvimento.
# Cria somente recursos sintéticos com prefixo próprio; nunca usa dados reais.
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$RAIZ"

BASE="infra/docker-compose.yml"
SMOKE="infra/docker-compose.smoke.yml"
ENV_SMOKE="${SMOKE_ISOLATION_ENV_SMOKE:-infra/.env.smoke}"
ENV_DOCKER_SMOKE="${SMOKE_ISOLATION_ENV_DOCKER:-.env.docker.smoke}"
PROJETO_SMOKE="reidofeno_smoke"
SENTINELA="reidofeno_sentinel_smoke_test"
VOLUME_SENTINELA="reidofeno_sentinel_smoke_test_dados"
LOCK_DIR="${SMOKE_ISOLATION_LOCK_DIR:-${TMPDIR:-/tmp}/reidofeno-smoke-isolation.lock}"
IMAGEM="${IMAGE_TAG:?defina IMAGE_TAG (imagem runtime já construída)}"

OWN_SMOKE=0
OWN_SENTINELA_CONTAINER=0
OWN_SENTINELA_VOLUME=0
LOCK_HELD=0

erro() {
    echo "ERRO: $*" >&2
    exit 1
}

limpar_smoke() {
    docker compose --project-name "$PROJETO_SMOKE" \
        --env-file "$ENV_SMOKE" \
        -f "$BASE" -f "$SMOKE" --profile cron \
        down -v --remove-orphans >/dev/null 2>&1 || true
}

cleanup() {
    local status=$?
    trap - EXIT

    if [ "$OWN_SMOKE" = "1" ]; then
        limpar_smoke
    fi
    if [ "$OWN_SENTINELA_CONTAINER" = "1" ]; then
        docker rm -f "$SENTINELA" >/dev/null 2>&1 || true
    fi
    if [ "$OWN_SENTINELA_VOLUME" = "1" ]; then
        docker volume rm "$VOLUME_SENTINELA" >/dev/null 2>&1 || true
    fi
    if [ "$LOCK_HELD" = "1" ]; then
        rmdir "$LOCK_DIR" >/dev/null 2>&1 || true
    fi

    exit "$status"
}

[ -f "$ENV_SMOKE" ] \
    || erro "ausente: $ENV_SMOKE (copie de infra/.env.smoke.example)"
[ -f "$ENV_DOCKER_SMOKE" ] \
    || erro "ausente: $ENV_DOCKER_SMOKE (copie de .env.docker.smoke.example)"

# Exclusão mútua do harness sentinela: uma segunda execução não pode
# interromper a primeira. A lock só é removida se esta execução a criou.
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    erro "outra execução de isolamento está ativa em $LOCK_DIR"
fi
LOCK_HELD=1
trap cleanup EXIT

# Guards de propriedade: nenhum recurso é criado/removido antes destas
# verificações. Existência de nome fixo não prova propriedade.
if docker volume inspect "$VOLUME_SENTINELA" >/dev/null 2>&1; then
    erro "volume sentinela já existe; remova-o manualmente antes do teste"
fi
if docker container inspect "$SENTINELA" >/dev/null 2>&1; then
    erro "container sentinela já existe; remova-o manualmente antes do teste"
fi

containers="$(docker ps -aq \
    --filter "label=com.docker.compose.project=$PROJETO_SMOKE")" \
    || erro "não foi possível consultar containers do projeto de smoke"
[ -z "$containers" ] \
    || erro "projeto $PROJETO_SMOKE já está ocupado por outra execução"

volumes="$(docker volume ls -q \
    --filter "label=com.docker.compose.project=$PROJETO_SMOKE")" \
    || erro "não foi possível consultar volumes do projeto de smoke"
[ -z "$volumes" ] \
    || erro "projeto $PROJETO_SMOKE já possui volumes de outra execução"

# Cinto e suspensórios para volumes nomeados, caso labels estejam ausentes.
for volume in pgdata redisdata caddy_data caddy_config media; do
    if docker volume inspect "${PROJETO_SMOKE}_${volume}" >/dev/null 2>&1; then
        erro "volume ${PROJETO_SMOKE}_${volume} já existe; projeto ocupado"
    fi
done

# A criação é registrada individualmente; uma falha parcial só autoriza
# remover o recurso comprovadamente criado por esta execução.
docker volume create "$VOLUME_SENTINELA" >/dev/null
OWN_SENTINELA_VOLUME=1

docker run -d --name "$SENTINELA" \
    --label "com.docker.compose.project=reidofeno" \
    -v "$VOLUME_SENTINELA:/dados" \
    alpine:3.20 sh -c 'printf sentinel > /dados/marcador; sleep 3600' >/dev/null
OWN_SENTINELA_CONTAINER=1

verificar_sentinela() {
    local conteudo rodando
    conteudo="$(docker exec "$SENTINELA" cat /dados/marcador)"
    [ "$conteudo" = "sentinel" ] \
        || erro "marcador sentinela foi alterado"
    rodando="$(docker inspect -f '{{.State.Running}}' "$SENTINELA")"
    case "$rodando" in
        true) ;;
        *) erro "container sentinela não está rodando" ;;
    esac
}

executar_smoke() {
    # O hook abaixo existe apenas para as regressões com Docker simulado.
    # Em uso normal/CI, executa o smoke real.
    if [ -n "${SMOKE_ISOLATION_COMMAND:-}" ]; then
        bash -c "$SMOKE_ISOLATION_COMMAND"
    else
        IMAGE_TAG="$IMAGEM" bash infra/scripts/smoke-stack.sh
    fi
}

verificar_sentinela

echo "== smoke de sucesso (projeto $PROJETO_SMOKE) =="
OWN_SMOKE=1
executar_smoke
verificar_sentinela
limpar_smoke
OWN_SMOKE=0
echo "SENTINELA_OK_APOS_SUCESSO"

echo "== falha deliberada após o seed =="
OWN_SMOKE=1
if SMOKE_TEST_FAIL_AFTER_SEED=1 executar_smoke; then
    erro "a falha deliberada do smoke não ocorreu"
fi
verificar_sentinela
limpar_smoke
OWN_SMOKE=0
echo "SENTINELA_OK_APOS_FALHA"

echo "== recusa de projeto compartilhado =="
if SMOKE_PROJECT_NAME=reidofeno executar_smoke; then
    erro "o smoke aceitou o projeto de desenvolvimento reidofeno"
fi
verificar_sentinela
echo "SENTINELA_OK_APOS_RECUSA"

echo "ISOLAMENTO_SMOKE_OK"
