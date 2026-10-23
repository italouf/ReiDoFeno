# Fase 3 — TAREFA 4: CI com PostgreSQL real e validação da imagem

## Contexto real

O workflow já usava `postgres:15` + `redis:7` como service containers desde a
Fase 2B. Esta tarefa consolida o contrato:

- testes passam a usar `config.settings.test`, em vez de herdar
  `config.settings.development` por acidente;
- `makemigrations --check` entra no gate;
- cobertura é publicada no Codecov;
- um job novo constrói a imagem Docker, verifica non-root, tamanho, Caddyfile e
  o Compose.

O gate histórico `0001 → HEAD` em PostgreSQL e o `check --deploy` continuam
inalterados.

## `config/settings/test.py`

- PostgreSQL via `DATABASE_URL` (default local
  `postgres://reidofeno:reidofeno@localhost:5432/test_reidofeno`).
- Redis via `REDIS_URL`; sem a variável, LocMem (permite rodar o settings em
  máquinas sem Redis, mas o CI sempre define).
- `MD5PasswordHasher` para reduzir tempo de hashing.
- Logging desligado e checks de rate limiting silenciados (o backend
  compartilhado é validado pelo `check --deploy`, não por este settings).
- `pytest` local continua em SQLite/development; o settings de teste é
  opt-in (`DJANGO_SETTINGS_MODULE=config.settings.test`).

## Workflow

### Job `tests`

- service containers `postgres:15` e `redis:7` com healthchecks;
- `DJANGO_SETTINGS_MODULE=config.settings.test`;
- `pytest --cov --cov-fail-under=80 --cov-report=xml:reports/coverage.xml`;
- `makemigrations --check --dry-run`;
- upload para Codecov (`fail_ci_if_error: false`);
- `check --deploy` com `config.settings.production` (TLS/segredos exigidos);
- migração histórica `0001 → HEAD` em banco separado.

### Job `docker`

1. `docker build --target runtime -f infra/Dockerfile .`
2. `docker run ... id -u` deve retornar `1000`.
3. `python manage.py check` com `config.settings.build`.
4. tamanho da imagem < 500 MB.
5. `caddy validate` no Caddyfile.
6. `docker compose config` com base + override.

### Jobs existentes

`lint` (Ruff + testes Node dos gráficos), `security` (Bandit + pip-audit) e
`semgrep` permanecem. O trigger ganhou a branch `fase-3-docker-staging`.

## Critérios de aceite

- [ ] Workflow é YAML válido e dispara em push/PR.
- [ ] Testes rodam contra PostgreSQL 15 real, incluindo `@pytest.mark.postgres`.
- [ ] Redis real é usado no rate limiting dos testes.
- [ ] `makemigrations --check` não detecta mudanças.
- [ ] Cobertura XML é gerada e enviada.
- [ ] Build da imagem e `caddy validate` passam no job `docker`.
- [ ] `docker compose config` aceita base + override sem `.env.docker` real.

## Validação local

Sem Docker e sem PostgreSQL nesta máquina, a validação executável foi:

```text
python -m pytest core/tests/test_infra_contract.py core/tests/test_ci_workflow.py
python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"
DJANGO_SETTINGS_MODULE=config.settings.test python -c "django.setup(); ..."
```

A execução integrada (PostgreSQL/Redis/Docker) acontece no GitHub Actions.
