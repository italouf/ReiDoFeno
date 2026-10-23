# Fase 3 — validação local

Data: 2026-10-23. Máquina sem Docker/WSL; a validação de build/stack fica no
job `docker` do CI.

## Executado e aprovado

| Verificação | Resultado |
|---|---|
| `pytest -q` (SQLite/development) | **685 passed, 24 skipped, 240 subtests** |
| `pytest core/tests/test_infra_contract.py core/tests/test_ci_workflow.py core/tests/test_settings_production.py` | **40 passed** |
| `ruff check .` | limpo |
| `python manage.py check` | sem issues (2 silenciados em dev/build) |
| `python manage.py makemigrations --check --dry-run` | sem mudanças |
| `check --deploy` (produção estrita) | sem issues |
| `bandit -c pyproject.toml -r . -ll` | 0 findings |
| `node --test static/js/relatorios.test.mjs` | 2/2 |
| `caddy validate` (Caddy 2.11.7, transporte de produção) | `Valid configuration` |
| `caddy validate` (variante de dev, sem PROXY) | `Valid configuration` |
| `caddy adapt` | `proxy_protocol: v1`, `handle_path /media`, headers presentes |
| `hadolint infra/Dockerfile` | limpo |
| `sh -n` nos dois entrypoints | sintaxe válida |
| `collectstatic` com `config.settings.build` | 147 arquivos, 427 pós-processados |
| YAML de compose/override/CI | parse válido + invariantes verificadas |
| Caddy prod/CI JSON | `proxy_protocol v1`, HSTS/CSP, `handle_path` de mídia |

## Não executado localmente (CI)

- `docker build` e medição do tamanho final da imagem.
- `docker compose up`, healthchecks e HTTPS em `https://localhost/healthz/`.
- Suíte completa contra PostgreSQL 15 + Redis (inclui `@pytest.mark.postgres`).
- Migração histórica `0001 → HEAD` em PostgreSQL.

Esses itens estão automatizados no job `docker` e no job `tests` do workflow.
Nenhuma alegação de sucesso local é feita para eles.
