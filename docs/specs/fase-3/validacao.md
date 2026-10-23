# Fase 3 — validação local

Data: 2026-10-23. Máquina sem Docker Engine/WSL; build, containers, HTTPS,
IP real, cron e persistência ficam no CI. O que foi executado localmente está
separado do que permanece pendente.

## Executado e aprovado

| Verificação | Resultado |
|---|---|
| `pytest -q` (SQLite/development) | **699 passed, 24 skipped, 240 subtests** |
| Testes focados (infra + CI + healthz + settings + shell) | **54 passed** |
| Classe de settings com pai limpo | **16 passed** |
| Classe de settings com pai staging do Compose | **16 passed** |
| `ruff check .` | limpo |
| `manage.py check` | sem issues |
| `makemigrations --check --dry-run` | sem mudanças |
| `check --deploy` (produção estrita) | sem issues |
| `bandit` | 0 findings |
| `node --test static/js/relatorios.test.mjs` | 2/2 |
| `caddy validate` (runtime e dev) | `Valid configuration` |
| `hadolint infra/Dockerfile` | limpo |
| `bash -n` nos scripts de smoke | sintaxe válida |
| `sh -n` entrypoints | sintaxe válida |
| Compose CLI v5.6.1 base/dev/cron/smoke | `config --quiet` ok |
| Smoke isolado: projeto/volumes/portas no modelo final | `reidofeno_smoke`, `reidofeno_smoke_*`, 8080/8443 |
| Recusa de `SMOKE_PROJECT_NAME=reidofeno` | exit 1 antes de Compose/mutação |
| `COMPOSE_PROJECT_NAME=reidofeno` + `--project-name` smoke | modelo permanece `reidofeno_smoke` |
| Django 5.2.17: `shell -c` sem flag | banner + `1` |
| Django 5.2.17: `shell --verbosity 0 -c` | somente `1` |

## Pendente de execução (CI/Docker)

- `docker build` runtime/dev e tamanho final < 500 MB.
- `docker compose up` com todos os healthchecks `healthy`.
- `infra/scripts/test-smoke-isolation.sh`: sentinela, sucesso, falha após seed
  e recusa do projeto de dev.
- HTTPS em `https://localhost:8443`, página, estático, IP real/`XFF` forjado,
  cron e persistência no projeto `reidofeno_smoke`.
- Suíte full no container dev com PostgreSQL/Redis reais.
- CI remoto verde no SHA corrigido. Nenhuma alegação de sucesso remoto é feita
  enquanto isso não ocorrer.

## Reprodução local

```bash
pytest -q
pytest core/tests/test_infra_contract.py core/tests/test_ci_workflow.py \
       core/tests/test_healthz.py core/tests/test_settings_production.py \
       core/tests/test_smoke_contract.py -q
ruff check .
```

Ambiente pai staging (reproduz o comando documentado do Compose):

```bash
export DJANGO_SETTINGS_MODULE=config.settings.development
export DJANGO_ENVIRONMENT=staging DATABASE_SSL_REQUIRE=False
export MERCADO_PAGO_FAKE=True BLING_FAKE=True
export MERCADOPAGO_COLLECTOR_ID= MERCADOPAGO_LIVE_MODE=False
pytest core/tests/test_settings_production.py -q
```

Compose sem daemon (exemplo):

```bash
docker-compose --project-name reidofeno_smoke \
  --env-file infra/.env.smoke \
  -f infra/docker-compose.yml -f infra/docker-compose.smoke.yml \
  --profile cron config --quiet
```
