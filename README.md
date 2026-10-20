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
| `MERCADOPAGO_WEBHOOK_SECRET` | sim (modo real) | Segredo de assinatura do webhook |
| `MERCADO_PAGO_FAKE` | não | `True` apenas em desenvolvimento/testes |
| `BLING_API_KEY` | sim (modo real) | Integração fiscal Bling |
| `BLING_FAKE` | não | `True` apenas em desenvolvimento/testes |
| `SENTRY_DSN` | não | Monitoramento de erros |
| `EMAIL_*` / `DEFAULT_FROM_EMAIL` | sim (envio real) | SMTP transacional |
| `PEDIDO_TIMEOUT_MINUTOS` | não | Expiração de pedidos (padrão 240) |
| `RECOMPRA_DIAS` | não | Janela de recompra (padrão 30) |
| `FISCAL_ALERTA_HORAS_SEM_NFE` | não | Alerta fiscal (padrão 24) |
| `RATELIMIT_LOGIN` | não | Limite de login (padrão `5/m`) |
| `RATELIMIT_CHECKOUT` | não | Limite de checkout (padrão `10/h`) |
| `RATELIMIT_WEBHOOK` | não | Limite do webhook (padrão `60/m`) |

## Produção

- `config/settings/production.py` exige `DATABASE_URL` PostgreSQL e força
  `sslmode=require`; não há fallback para SQLite (ADR-001).
- O rate limiting usa `DatabaseCache` em produção. Execute
  `python manage.py createcachetable` no deploy.
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

## Documentação

- `docs/adrs/ADR-001-postgres-local.md`
- `docs/adrs/ADR-002-status-financeiro.md`
- `docs/runbook.md`
- `docs/incidentes.md`
- `rfenodocs/docs/technical-audit.md` (material de auditoria, não versionado)
