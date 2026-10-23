# Fase 3 — TAREFA 2: orquestração local com Docker Compose

## Objetivo

Subir a mesma stack em desenvolvimento, staging e produção — Django,
PostgreSQL 15, Redis 7, Caddy e jobs agendados — com redes separadas,
volumes persistentes e healthchecks em todos os serviços.

## Topologia

```text
                    Internet
                       │ 80/443
                  ┌────▼─────┐
                  │  caddy   │  front
                  └────┬─────┘
                       │ web:8000 (PROXY protocol v1)
                  ┌────▼─────┐
   front ─────────┤   web    ├───────── back
                  └────┬─────┘            │
                       │                  ├── db (sem porta)
                       │                  └── redis (sem porta)
                  ┌────▼─────┐
                  │   cron   │  front + back (perfil `cron`)
                  └──────────┘
```

Serviços:

| Serviço | Imagem | Rede | Porta publicada | Healthcheck |
|---|---|---|---|---|
| `caddy` | `caddy:2-alpine` | front | 80, 443, 443/udp | admin API `:2019/config/` |
| `web` | build local (`runtime`) | front + back | não | `/healthz/` com PROXY protocol |
| `db` | `postgres:15-alpine` | back | **não** | `pg_isready` |
| `redis` | `redis:7-alpine` | back | **não** | `redis-cli ping` |
| `cron` | build local (`runtime`) | front + back | não | `supercronic -test` |
| `caddy-init` | `alpine:3.20` | none | não | one-shot |

## Decisões

### Redes

- `front`: única rede com saída para a internet e a única ligada ao Caddy.
- `back`: `internal: true`; PostgreSQL e Redis não têm rota para a internet
  nem portas publicadas. `web` e `cron` participam de ambas para alcançar
  banco/cache e, ao mesmo tempo, integrações externas.

### Volumes

- `pgdata`, `redisdata`: persistência.
- `caddy_data`, `caddy_config`: certificados e autosave (preservam Let's
  Encrypt entre restarts).
- `media`: compartilhado entre `web` (escrita) e `caddy` (somente leitura).
  É um volume nomeado para herdar a ownership `app:app` da imagem; bind mount
  de host em Linux criaria diretório root-owned e quebraria uploads.

### Configuração e segredos

- `.env.docker` (raiz, gitignored) carrega segredos do Django via `env_file`.
- `infra/.env` (gitignored) é lido pelo Compose para interpolar
  `DB_PASSWORD`, domínios e `HSTS_MAX_AGE`.
- Nenhuma senha/segredo é hardcoded no compose; o default `reidofeno` é
  apenas para desenvolvimento local e está documentado.

### Staging × produção

O compose usa `config.settings.production` com `DJANGO_ENVIRONMENT=staging`
no exemplo local. O modo staging:

- permite `DATABASE_SSL_REQUIRE=False` (PostgreSQL na rede interna Docker);
- permite `MERCADO_PAGO_FAKE` / `BLING_FAKE`;
- não exige `MERCADOPAGO_COLLECTOR_ID` nem live mode.

Produção continua estrita: `DJANGO_ENVIRONMENT=production` (default),
`DATABASE_SSL_REQUIRE=True`, sem fake e com coletor/live mode obrigatórios.
A relaxação é explícita e coberta por testes em
`core/tests/test_settings_production.py`.

### Migrations

Somente `web` roda `migrate` (`RUN_MIGRATIONS=true`). `cron` espera `web`
ficar healthy e sobe com `RUN_MIGRATIONS=false`. O entrypoint faz `exec`, então
Gunicorn/supercronic são PID 1 e recebem `SIGTERM`.

### Cron

Perfil opcional (`--profile cron`) para não atrasar o loop de desenvolvimento:

| Job | Agenda |
|---|---|
| `expirar_pedidos` | a cada 15 min |
| `processar_fiscal` | a cada 30 min |
| `gerar_avisos_comerciais` | diário às 08:00 |

### Caddy não-root

`caddy-init` (one-shot, root) ajusta a ownership dos volumes; o Caddy roda
como uid 1000, com `cap_drop: ALL`, `cap_add: NET_BIND_SERVICE`,
`no-new-privileges` e filesystem read-only. Em Docker ≥ 20.10 o sysctl
`net.ipv4.ip_unprivileged_port_start=0` já permite as portas 80/443.

## Desenvolvimento

```bash
cp .env.docker.example .env.docker
cp infra/.env.example infra/.env

docker compose -f infra/docker-compose.yml \
               -f infra/docker-compose.override.yml up -d

curl -k https://localhost/healthz/
curl http://localhost:8000/healthz/   # porta direta do runserver
docker compose -f infra/docker-compose.yml \
               -f infra/docker-compose.override.yml run --rm web pytest
```

O override usa o stage `dev` (com `requirements-dev.txt`), monta o repositório
em `/app` para hot-reload e publica `8000:8000`.

## Staging/produção

```bash
# infra/.env com APP_DOMAIN/STAGING_DOMAIN reais e HSTS_MAX_AGE=31536000
# .env.docker com DJANGO_ENVIRONMENT=production e segredos reais
docker compose -f infra/docker-compose.yml --profile cron up -d
```

## Critérios de aceite

- [ ] `docker compose config` válido (base + override).
- [ ] `docker compose up -d` sobe web, db, redis e caddy sem erro.
- [ ] `docker compose ps` mostra todos os serviços de longa duração `healthy`.
- [ ] `docker compose run --rm web pytest` executa a suíte no stage `dev`.
- [ ] `db` e `redis` não publicam portas.
- [ ] Volume `media` persiste entre restarts e é legível pelo Caddy.
- [ ] `curl -k https://localhost/healthz/` retorna `{"status": "ok"}`.

## Validação local desta execução

Docker não está instalado na máquina; a validação estrutural foi feita com
PyYAML e testes de contrato, e o job `docker` do CI executa
`docker compose config` e `docker build` de forma autoritativa.
