# Fase 3 — validação local

Data: 2026-10-23. Máquina sem Docker Engine/WSL; a validação de build, stack,
HTTPS, cron e persistência fica no job `docker` do CI. O que foi executado
localmente está separado do que permanece pendente.

## Executado e aprovado

| Verificação | Resultado |
|---|---|
| `pytest -q` (SQLite/development) | **695 passed, 24 skipped, 240 subtests** |
| Testes de contrato/settings/endpoint | **50 passed** |
| Classe de produção com pai limpo | **16 passed** |
| Classe de produção com pai staging do Compose | **16 passed** |
| `ruff check .` | limpo |
| `manage.py check` | sem issues |
| `makemigrations --check --dry-run` | sem mudanças |
| `check --deploy` (produção estrita) | sem issues |
| `bandit` | 0 findings |
| `node --test static/js/relatorios.test.mjs` | 2/2 |
| `caddy validate` (transporte runtime) | `Valid configuration` |
| `caddy validate` (transporte dev) | `Valid configuration` |
| `hadolint infra/Dockerfile` | limpo |
| `bash -n infra/scripts/smoke-stack.sh` | sintaxe válida |
| `sh -n` entrypoints | sintaxe válida |
| Docker Compose CLI v5.6.1 `config --quiet` (base) | ok |
| Docker Compose CLI v5.6.1 (base + override) | ok |
| Docker Compose CLI v5.6.1 (cron) | ok |
| Docker Compose CLI v5.6.1 (override + cron) | ok |
| Docker Compose CLI v5.6.1 (smoke + cron) | ok |
| Caminhos `--mount` do Caddy no workflow | regressão resolve arquivos reais |

## Pendente de execução (CI/Docker)

- `docker build` runtime/dev e tamanho final < 500 MB.
- `docker compose up` com todos os healthchecks `healthy`.
- HTTPS local, página representativa, estático com hash, IP real/`XFF`
  forjado, cron e persistência: `infra/scripts/smoke-stack.sh`.
- Suíte completa no container dev com PostgreSQL/Redis reais.
- CI remoto verde no SHA corrigido. Nenhuma alegação de sucesso remoto é
  feita enquanto isso não ocorrer.

## Reprodução local

```bash
pytest -q
pytest core/tests/test_infra_contract.py core/tests/test_ci_workflow.py \
       core/tests/test_healthz.py core/tests/test_settings_production.py -q
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
