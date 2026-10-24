# ReiDoFeno

Sistema de gestão e loja online para a Rei do Feno (Django 5.2, PostgreSQL,
WhiteNoise/Gunicorn). O repositório cobre catálogo, estoque, vendas, custos,
fiscal, privacidade/LGPD e o fluxo de pagamento com Mercado Pago.

## Requisitos

- Python 3.12+ (o ambiente de desenvolvimento atual usa 3.14)
- PostgreSQL em produção; SQLite apenas em desenvolvimento/testes
- Variáveis de ambiente para segredos (nunca versionadas)

## Desenvolvimento

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements-dev.txt
python manage.py migrate
python manage.py seed_groups
python manage.py runserver
```

Estoque demo (somente banco descartável):

```bash
ALLOW_DEMO_SEED=1 python manage.py semear_estoque_demo
```

O comando ajusta o saldo via ledger, preserva reservas/bloqueios e é idempotente.
A variável é obrigatória também no SQLite para evitar execução acidental.

Testes e qualidade:

```bash
pytest
pytest --cov --cov-report=term-missing
ruff check .
bandit -r . -ll
pip-audit -r requirements.txt
```

## Docker (Fase 3 — homologação local)

A stack de homologação local usa a mesma imagem runtime para Django/Gunicorn,
com PostgreSQL 15, Redis 7, Caddy (HTTPS local) e jobs agendados. Ela **não**
representa um staging público nem dois ambientes isolados: `APP_DOMAIN` e
`STAGING_DOMAIN` apontam para o mesmo `web`, banco e integrações.

```bash
# ambiente de desenvolvimento
cp .env.docker.example .env.docker     # segredos locais (gitignored)
cp infra/.env.example infra/.env       # domínios/senha do compose

# desenvolvimento (runserver + hot-reload; porta 8000 em loopback)
docker compose --project-name reidofeno \
               -f infra/docker-compose.yml \
               -f infra/docker-compose.override.yml up -d

# classe de settings no ambiente documentado do Compose
docker compose --project-name reidofeno \
               -f infra/docker-compose.yml \
               -f infra/docker-compose.override.yml \
               run --rm web pytest core/tests/test_settings_production.py

# suíte completa com PostgreSQL/Redis reais e settings de teste
docker compose --project-name reidofeno \
               -f infra/docker-compose.yml \
               -f infra/docker-compose.override.yml \
               run --rm -e DJANGO_SETTINGS_MODULE=config.settings.test \
               -e REDIS_URL=redis://redis:6379/0 web pytest

# smoke isolado: projeto reidofeno_smoke, portas 8080/8443
cp .env.docker.smoke.example .env.docker.smoke
cp infra/.env.smoke.example infra/.env.smoke
IMAGE_TAG=local docker compose --project-name reidofeno \
               -f infra/docker-compose.yml build web
IMAGE_TAG=local bash infra/scripts/smoke-stack.sh
```

O smoke usa um projeto Compose próprio (`reidofeno_smoke`), volumes
`reidofeno_smoke_*`, arquivos `.env.smoke`/`.env.docker.smoke` e portas
8080/8443. Ele **recusa** o projeto `reidofeno` e nunca remove volumes do
desenvolvimento. Para validar também o isolamento e a falha deliberada:

```bash
IMAGE_TAG=local bash infra/scripts/test-smoke-isolation.sh
```

O script sobe o perfil `cron`, exige todos os healthchecks, executa as três
rotinas com dados sintéticos e recria os containers preservando os volumes do
próprio smoke.

- `https://localhost/` (dev) e `https://localhost:8443/` (smoke) usam a CA
  interna do Caddy; aceite o certificado ou use `curl -k`. A porta `8000` do
  dev é publicada apenas no override e, por padrão, em `127.0.0.1`; use
  `DOCKER_DEV_BIND=0.0.0.0` somente para acesso pela rede.
- PostgreSQL e Redis não publicam portas: só existem na rede `back`
  (`internal: true`).
- `DJANGO_ENVIRONMENT=staging` permite simuladores e PostgreSQL interno sem
  TLS. Isso é adequado à homologação local; **não** torna a stack pronta para
  produção.
- O Caddy envia PROXY protocol v1 ao Gunicorn, preservando `REMOTE_ADDR`
  (SEC-03). O endpoint `/healthz/ip/` só existe com `SMOKE_DIAGNOSTICS=True`
  em staging e é usado exclusivamente pelo smoke.
- Jobs: `expirar_pedidos` (15 min), `processar_fiscal` (30 min) e
  `gerar_avisos_comerciais` (08:00), via perfil `cron`.

### Limites desta entrega

- **Sem CD:** o workflow não faz deploy. Push em `main` executa CI, não sobe
  staging. O PostgreSQL/Redis do job `tests` são service containers efêmeros
  do runner, não a VPS nem um banco gerenciado.
- **Sem staging público:** DNS, VPS e Let's Encrypt público não foram
  provisionados nem validados.
- **PostgreSQL interno sem TLS:** o Compose não configura certificados no
  banco. Produção estrita continua exigindo TLS; trocar apenas
  `DJANGO_ENVIRONMENT`/`DATABASE_SSL_REQUIRE` não prepara esse banco.
- **Dois domínios, uma instância:** os blocos do Caddy são aliases do mesmo
  backend, não isolamento de dados/credenciais.
- **HSTS:** o Compose local usa `HSTS_MAX_AGE=0`; a política pública
  (`31536000`) deve ser habilitada somente no ambiente público real.
- **Reprodutibilidade:** dependências Python são fixadas; tags de imagens base
  ainda são mutáveis. Pin por digest fica para uma entrega posterior.

Detalhes em `docs/specs/fase-3/` (inclui `correcao-aceite.md`).

## Variáveis de ambiente

| Variável | Obrigatória em produção | Uso |
|---|---|---|
| `DJANGO_SECRET_KEY` | sim | Segredo criptográfico do Django |
| `DATABASE_URL` | sim | PostgreSQL, com TLS (`sslmode=require`) |
| `DJANGO_ALLOWED_HOSTS` | sim | Hosts permitidos, separados por vírgula |
| `CSRF_TRUSTED_ORIGINS` | recomendada | Origens confiáveis para CSRF |
| `SITE_URL` | recomendada | URL pública usada em e-mails/links |
| `MERCADOPAGO_ACCESS_TOKEN` | sim (modo real) | Credencial do Mercado Pago |
| `MERCADOPAGO_COLLECTOR_ID` | sim (modo real) | Recebedor esperado na validação |
| `MERCADOPAGO_LIVE_MODE` | sim (produção) | Exige ambiente live no webhook |
| `MERCADOPAGO_WEBHOOK_SECRET` | sim (modo real) | Segredo de assinatura do webhook |
| `MERCADOPAGO_WEBHOOK_TOLERANCE_SECONDS` | não | Tolerância do timestamp (padrão 300) |
| `MERCADO_PAGO_FAKE` | não | `True` apenas em desenvolvimento/testes |
| `BLING_API_KEY` | sim (modo real) | Integração fiscal Bling |
| `BLING_FAKE` | não | `True` apenas em desenvolvimento/testes |
| `SENTRY_DSN` | não | Monitoramento de erros |
| `EMAIL_*` / `DEFAULT_FROM_EMAIL` | sim (envio real) | SMTP transacional |
| `PEDIDO_TIMEOUT_MINUTOS` | não | Expiração de pedidos (padrão 240) |
| `RECOMPRA_DIAS` | não | Janela de recompra (padrão 30) |
| `FISCAL_ALERTA_HORAS_SEM_NFE` | não | Alerta fiscal (padrão 24) |
| `RATELIMIT_LOGIN` | não | Limite de login (padrão `5/m`) |
| `RATELIMIT_CHECKOUT` | não | Limite de checkout por sessão (padrão `10/h`) |
| `RATELIMIT_CHECKOUT_IP` | não | Limite de checkout por IP (padrão `30/h`) |
| `RATELIMIT_PAGAMENTO` | não | Limite de início de pagamento (padrão `10/m`) |
| `RATELIMIT_VINCULO_EMISSAO` | não | Emissão de prova de vínculo (padrão `3/h`) |
| `RATELIMIT_VINCULO_CONSUMO` | não | Consumo de prova de vínculo (padrão `10/h`) |
| `RATELIMIT_WEBHOOK` | não | Limite do webhook (padrão `60/m`) |
| `REDIS_URL` | sim (produção) | Cache compartilhado com incremento atômico |

## Produção (não provisionada nesta entrega)

- O caminho de deploy planejado usa `infra/docker-compose.yml`: Caddy (TLS
  automático) → Gunicorn → PostgreSQL/Redis. O Caddy envia PROXY protocol v1
  ao Gunicorn, que roda com `--proxy-protocol=v1`; assim o IP real do cliente
  chega em `REMOTE_ADDR` (SEC-03). A porta do `web` não deve ser publicada.
- O PostgreSQL interno do Compose **não tem TLS configurado**. Para produção,
  provisione Postgres com TLS e use `DJANGO_ENVIRONMENT=production` e
  `DATABASE_SSL_REQUIRE=True`; apenas trocar variáveis não supre o certificado.
- Não há CD no workflow. Publicação em VPS, DNS e Let's Encrypt público exigem
  uma entrega/ambiente separado e não foram executados aqui.
- `config/settings/production.py` exige `DATABASE_URL` PostgreSQL e força
  `sslmode=require`; não há fallback para SQLite (ADR-001).
- O rate limiting usa Redis com incremento atômico em produção. `REDIS_URL`
  é obrigatório; não use `DatabaseCache` para contadores.
- Produção rejeita `MERCADO_PAGO_FAKE=True` e `BLING_FAKE=True`; o simulador
  só existe em desenvolvimento/testes.
- O webhook exige `MERCADOPAGO_WEBHOOK_SECRET` no modo real e aceita o
  formato oficial `ts=...,v1=...`.
- Se houver proxy reverso, configure-o para preservar o IP real em
  `REMOTE_ADDR`. Não aceite `X-Forwarded-For` de origem não controlada
  (SEC-03); ajuste o proxy, não o código, para que login/webhook tenham
  limites por cliente.
- Aplique `python manage.py migrate --noinput` antes de liberar tráfego.
- Consulte `docs/runbook.md` para deploy, backups, restore e resposta a
  incidentes.

## Segurança — Fase 2A

- **SEC-01:** o endpoint interno de status rejeita transições financeiras com
  HTTP 403 e audita a tentativa.
- **SEC-02:** checkout não vincula `Cliente.usuario`; o vínculo exige
  comprovação por e-mail assinado ou administração auditada.
- **SEC-03:** mudanças críticas (pedido, pagamento, estoque e fiscal) gravam
  `LogAuditoria` na mesma transação; IP usa `REMOTE_ADDR`.
- **Rate limiting:** login, checkout e webhook retornam HTTP 429 com
  `Retry-After`.
- **ADR-002:** `Pedido.status_financeiro` é independente do andamento
  operacional.
- **Legado:** `Pedido.financeiro_conciliado` bloqueia avanço/fiscal de pedido
  pago sem prova; use `python manage.py inventariar_legado --json` e
  `python manage.py reconciliar_pedido_financeiro <numero> --justificativa`.
- **Pagamento:** criação de preferência é POST, limitada e idempotente por
  `Pagamento.idempotency_key`; o provedor recebe `X-Idempotency-Key`.

## Documentação

- `docs/specs/fase-3/dockerfile.md`
- `docs/specs/fase-3/docker-compose.md`
- `docs/specs/fase-3/caddy.md`
- `docs/specs/fase-3/ci-postgres.md`
- `docs/specs/fase-3/validacao.md`
- `docs/specs/fase-3/correcao-aceite.md`
- `docs/specs/fase-2b-spec.md`
- `docs/specs/fase-2b-remediation.md`
- `docs/audit/fase-2b-conclusao.md`
- `docs/adrs/ADR-001-postgres-local.md`
- `docs/adrs/ADR-002-status-financeiro.md`
- `docs/adrs/ADR-003-reservas-vinculadas.md`
- `docs/adrs/ADR-013-ledger-imutavel.md`
- `docs/adrs/ADR-014-cnpj-alfanumerico.md`
- `docs/adrs/ADR-015-obrigacao-estoque.md`
- `docs/runbook.md`
- `docs/incidentes.md`
- `rfenodocs/docs/technical-audit.md` (material de auditoria, não versionado; não é fonte canônica)

## Preço de atacado

- Clientes com categoria **ATACADO** recebem `Produto.preco_atacado` quando
  compram **mais de 50 fardos** de um produto cuja unidade de medida é `fardo`.
- A tabela exige vínculo comprovado do titular ou pedido criado por vendedor
  interno; visitante que informa CNPJ alheio usa o preço online.
- O limiar é estrito: 50 fardos usam o preço-base do canal.
- Clientes VAREJO, produtos que não são fardos e produtos sem preço de atacado
  usam o preço-base (loja: `preco_online`; atacadista: `preco_balcao`).
- O preço é congelado em `ItemPedido.preco_unitario` no checkout.
