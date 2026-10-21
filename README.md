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
python manage.py semear_estoque_demo
# Fora do SQLite, exige confirmação explícita:
ALLOW_DEMO_SEED=1 python manage.py semear_estoque_demo
```

O comando ajusta o saldo via ledger, preserva reservas/bloqueios e é idempotente.

Testes e qualidade:

```bash
pytest
pytest --cov --cov-report=term-missing
ruff check .
bandit -r . -ll
pip-audit -r requirements.txt
```

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

## Produção

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

- `docs/adrs/ADR-001-postgres-local.md`
- `docs/adrs/ADR-002-status-financeiro.md`
- `docs/runbook.md`
- `docs/incidentes.md`
- `rfenodocs/docs/technical-audit.md` (material de auditoria, não versionado)

## Preço de atacado

- Clientes com categoria **ATACADO** recebem `Produto.preco_atacado` quando
  compram **mais de 50 fardos** de um produto cuja unidade de medida é `fardo`.
- A tabela exige vínculo comprovado do titular ou pedido criado por vendedor
  interno; visitante que informa CNPJ alheio usa o preço online.
- O limiar é estrito: 50 fardos usam o preço-base do canal.
- Clientes VAREJO, produtos que não são fardos e produtos sem preço de atacado
  usam o preço-base (loja: `preco_online`; atacadista: `preco_balcao`).
- O preço é congelado em `ItemPedido.preco_unitario` no checkout.
