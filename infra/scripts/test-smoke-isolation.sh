#!/usr/bin/env bash
# Prova que o smoke não toca em recursos do projeto de desenvolvimento.
# Cria somente recursos sintéticos com prefixo próprio; nunca usa dados reais.
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$RAIZ"

BASE="infra/docker-compose.yml"
SMOKE="infra/docker-compose.smoke.yml"
ENV_SMOKE="infra/.env.smoke"
PROJETO_SMOKE="reidofeno_smoke"
SENTINELA="reidofeno_sentinel_smoke_test"
VOLUME_SENTINELA="reidofeno_sentinel_smoke_test_dados"
IMAGEM="${IMAGE_TAG:?defina IMAGE_TAG (imagem runtime já construída)}"

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

limpar_sentinela() {
    docker rm -f "$SENTINELA" >/dev/null 2>&1 || true
    docker volume rm "$VOLUME_SENTINELA" >/dev/null 2>&1 || true
}

trap 'limpar_smoke; limpar_sentinela' EXIT

if docker volume inspect "$VOLUME_SENTINELA" >/dev/null 2>&1; then
    erro "volume sentinela já existe; remova-o manualmente antes do teste"
fi
if docker container inspect "$SENTINELA" >/dev/null 2>&1; then
    erro "container sentinela já existe; remova-o manualmente antes do teste"
fi

docker volume create "$VOLUME_SENTINELA" >/dev/null
docker run -d --name "$SENTINELA" \
    --label "com.docker.compose.project=reidofeno" \
    -v "$VOLUME_SENTINELA:/dados" \
    alpine:3.20 sh -c 'printf sentinel > /dados/marcador; sleep 3600' >/dev/null

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

verificar_sentinela

echo "== smoke de sucesso (projeto $PROJETO_SMOKE) =="
IMAGE_TAG="$IMAGEM" bash infra/scripts/smoke-stack.sh
verificar_sentinela
echo "SENTINELA_OK_APOS_SUCESSO"

echo "== falha deliberada após o seed =="
if IMAGE_TAG="$IMAGEM" SMOKE_TEST_FAIL_AFTER_SEED=1 \
    bash infra/scripts/smoke-stack.sh; then
    erro "a falha deliberada do smoke não ocorreu"
fi
verificar_sentinela
limpar_smoke
echo "SENTINELA_OK_APOS_FALHA"

echo "== recusa de projeto compartilhado =="
if IMAGE_TAG="$IMAGEM" SMOKE_PROJECT_NAME=reidofeno \
    bash infra/scripts/smoke-stack.sh; then
    erro "o smoke aceitou o projeto de desenvolvimento reidofeno"
fi
verificar_sentinela
echo "SENTINELA_OK_APOS_RECUSA"

echo "ISOLAMENTO_SMOKE_OK"
