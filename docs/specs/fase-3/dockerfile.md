# Fase 3 — TAREFA 1: imagem Docker do Django

## Objetivo

Produzir uma imagem reproduzível para staging/produção, com Gunicorn, usuário
não-privilegiado, `collectstatic` em tempo de build e inicialização segura
(espera do PostgreSQL + migrations controladas por variável de ambiente).

## Contexto real do repositório

- `requirements.txt` já fixa `psycopg`, `psycopg-binary`, `gunicorn`,
  `whitenoise` e `python-json-logger`.
- O entrypoint de saúde é `/healthz/` (`core.views.healthz`).
- O projeto usa `config.settings.production` com validações estritas
  (ADR-001) e `config.settings.development` no dia a dia.
- Docker não está instalado no ambiente local desta execução; a validação
  autoritativa da imagem roda no job `docker` do GitHub Actions, e as
  invariantes estáticas são cobertas por testes Python.

## Decisões

### Multi-stage

| Stage | Uso | Conteúdo |
|---|---|---|
| `builder` | compila dependências de produção e coleta estáticos | build tools, `requirements.txt`, código |
| `dev` | `docker compose` de desenvolvimento | builder + `requirements-dev.txt`, `runserver` |
| `runtime` | staging/produção | somente runtime (`libpq5`, `curl`, `tzdata`) |

O stage `dev` existe porque o gate exige `docker compose run --rm web pytest`;
sem ele, a imagem final precisaria carregar pytest/ruff/playwright e deixaria
de ser mínima.

### Usuário não-privilegiado

`app` (uid/gid 1000) é criado no stage base e usado em `dev` e `runtime`.
Nenhum processo da aplicação roda como root. O único serviço root do compose
é o `caddy-init` one-shot que ajusta a ownership dos volumes do Caddy.
O Caddy em si roda como uid 1000 com apenas `NET_BIND_SERVICE`.

### Estáticos no build

`collectstatic` roda no builder com `config.settings.build`, que usa
`CompressedManifestStaticFilesStorage` — o mesmo storage de produção. Isso
evita o erro clássico de imagem que sobe com `StaticFilesStorage` e quebra no
primeiro request por falta de manifesto. As variáveis exigidas por
`production.py` (banco, Redis, Mercado Pago) não são necessárias no build.

### Entrypoint

`infra/scripts/entrypoint.sh`:

1. espera o PostgreSQL aceitar conexão (30 tentativas, `connect_timeout=3`);
2. executa `migrate --noinput` quando `RUN_MIGRATIONS=true` (default);
3. faz `exec "$@"` para preservar sinais e o PID 1.

O `cron` sobe com `RUN_MIGRATIONS=false`, pois depende de `web` já saudável.

### IP real atrás do proxy (SEC-03)

Gunicorn roda com `--proxy-protocol=v1` e `--proxy-allow-from=*`; o Caddy
envia PROXY protocol v1 no upstream (`transport http { proxy_protocol v1 }`).
Assim `REMOTE_ADDR` é o IP do cliente, sem confiar em `X-Forwarded-For`
arbitrário. O `proxy-allow-from=*` é seguro porque o `web` não publica porta e
só é alcançável pelas redes internas do Compose.

O healthcheck usa `curl --haproxy-protocol`, exercitando o mesmo caminho do
proxy. O Gunicorn aceita conexões sem o cabeçalho, mas o Caddy sempre o envia.

### Cron

`supercronic` v0.2.51 (binário estático, executa como não-root) é baixado no
stage `supercronic` com verificação SHA-256 por arquitetura (`amd64`/`arm64`).
A crontab versionada em `infra/crontab` reproduz os jobs do blueprint:
`expirar_pedidos` (15 min), `processar_fiscal` (30 min) e
`gerar_avisos_comerciais` (diário às 08:00).

## Critérios de aceite

- [ ] `docker build -f infra/Dockerfile .` conclui sem erro.
- [ ] Imagem final < 500 MB.
- [ ] `id -u` dentro do container runtime retorna `1000`.
- [ ] `collectstatic` ocorre no build, não no entrypoint.
- [ ] `curl --haproxy-protocol` em `/healthz/` retorna 200.
- [ ] Entrypoint aguarda o banco e respeita `RUN_MIGRATIONS`.
- [ ] `.dockerignore` exclui segredos (`.env*`), banco local, mídia e caches.

## Testes

```bash
# build e checks (CI ou máquina com Docker)
docker build -t reidofeno:test -f infra/Dockerfile .
docker run --rm -e RUN_MIGRATIONS=false reidofeno:test id -u
docker run --rm -e RUN_MIGRATIONS=false \
  -e DJANGO_SETTINGS_MODULE=config.settings.build \
  reidofeno:test python manage.py check

# validação estática local (sem Docker)
pytest core/tests/test_infra_contract.py
python -m compileall config/settings infra
sh -n infra/scripts/entrypoint.sh
```

## Riscos e mitigação

| Risco | Mitigação |
|---|---|
| `TARGETARCH` ausente em builders antigos | `# syntax=docker/dockerfile:1.6` + default `amd64` |
| Caddy envia PROXY e healthcheck falha | healthcheck com `curl --haproxy-protocol`; override dev sem PROXY |
| Volume de mídia root-owned | volume nomeado inicializado a partir de `/app/media` (app:app) |
| Migrations concorrentes | apenas `web` roda migrations; `cron` usa `RUN_MIGRATIONS=false` |
