# Changelog

Todas as mudanças relevantes deste projeto são registradas aqui.

## [Fase 2A — remediação da auditoria independente] — 2026-10-20

- **R1/PAY-02:** contrato financeiro completo (tentativa local, ID
  consultado/retornado, valor, BRL, recebedor e `live_mode`) antes de
  qualquer mutação; divergência gera auditoria e não altera estoque/pedido.
- **R2:** pedido estornado/cancelado/pendente não avança para separação,
  pronto, enviado ou concluído.
- **R3:** transição operacional centralizada em serviço com
  `select_for_update`, releitura e autorização por objeto.
- **R4:** `Pedido.nome_contato` e `identidade_verificada` separam contato de
  identidade; checkout não expõe nome canônico nem grava consentimento em
  cadastro não comprovado.
- **R5/R10:** prova de vínculo com nonce hasheado, uso único, expiração,
  POST/CSRF e invalidação por e-mail; vínculos legados exigem revisão
  administrativa com justificativa e auditoria.
- **R6:** rate limiting migrado para Redis com incremento atômico; início de
  pagamento virou POST limitado e idempotente; CI com PostgreSQL/Redis.
- **R7:** timestamp de webhook aceita segundos/milissegundos; query/body/ID
  precisam concordar; eventos ignorados preservam todos os modelos.
- **R8:** criação de pedido/reserva auditada atomicamente; liberação de
  reserva auditada; comando `inventariar_legado` para conciliação read-only.

### Migrations

- `sales.0003_pedido_consentimento_compras_and_more`: snapshot de contato,
  identidade verificada e flags de consentimento do pedido.
- `sales.0004_pagamento_init_point`: reuso idempotente de preferência.
- `customers.0004_cliente_vinculo_verificado_vinculoclientetoken`: estado de
  vínculo comprovado e provas de uso único.

### Documentação

- `docs/security/fase2a-remediation-spec.md`
- ADR-001/ADR-002 e runbook atualizados para VPS, Redis e revisão de legado.

## [Fase 2A] — 2026-10-19 — Contenção de segurança crítica

### Segurança

- **SEC-01:** `/gestao/pedidos/<pk>/status/` rejeita `pago`,
  `pagamento_pendente` e `falhou` com HTTP 403; tentativas são registradas em
  `LogAuditoria` com a ação `tentativa_bloqueada_transicao_financeira`.
- **SEC-02:** o checkout não vincula mais `Cliente.usuario` por CPF/CNPJ.
  Novos clientes também nascem sem vínculo. O vínculo exige link assinado e
  expirável enviado ao e-mail já cadastrado (`/accounts/vincular-cliente/`),
  com auditoria `cliente.vinculo_confirmado`.
- **SEC-03:** novo helper `core.auditoria.auditar_atomicamente()` grava a
  alteração e o `LogAuditoria` na mesma transação. Transições de pedido,
  pagamentos, movimentos de estoque e notas fiscais foram cobertos. O IP é
  capturado de `REMOTE_ADDR`; `X-Forwarded-For` não é aceito diretamente.
- **Rate limiting:** login (`5/m` por IP), checkout (`10/h` por sessão e
  `30/h` por IP), início de pagamento (`10/m` por IP) e webhook (`60/m` por
  IP) retornam HTTP 429 com `Retry-After`.
  `django-ratelimit==4.1.0` adicionado. Em produção o cache é compartilhado
  via `DatabaseCache`.
- **PAY-01:** webhook aceita o formato oficial `ts=...,v1=...` (e o legado
  com `;`), exige `MERCADOPAGO_WEBHOOK_SECRET` no modo real, valida
  `x-request-id`, `data_id` canônico e timestamp dentro de
  `MERCADOPAGO_WEBHOOK_TOLERANCE_SECONDS` (padrão 300s).
- `AXES_FAILURE_LIMIT` ajustado para 6 para que o limite efetivo de 5
  tentativas/minuto seja aplicado pelo rate limiting, mantendo o bloqueio
  temporário do django-axes.
- Produção rejeita `MERCADO_PAGO_FAKE=True` e `BLING_FAKE=True`.
- Serviços de pagamento/cancelamento re-leem o pedido com
  `select_for_update()`; a expiração nunca cancela pedido pago concorrente.
- Eventos oficiais `rejected` e `refunded` são mapeados; eventos fora de
  ordem não rebaixam `Pagamento` aprovado. `in_mediation` e status
  desconhecidos são auditados.
- Migration prioriza estados cumpridos sobre pagamentos recusados antigos.
- Checkout ganhou limite secundário por IP (`30/h`); início de pagamento é
  limitado (`10/m`) e auditado.
- CRUD de `Unidade` passou a ser auditado atomicamente.

### Banco de dados e infraestrutura

- **ADR-001:** produção exige `DATABASE_URL` PostgreSQL, rejeita SQLite e
  força `sslmode=require`. `conn_max_age=600` e health checks ativos.
- **ADR-002:** novo campo `Pedido.status_financeiro`
  (`pendente`, `pago`, `estornado`, `cancelado`).
  - A aprovação do pagamento altera apenas o financeiro e baixa o estoque;
    o andamento permanece em `aguardando_pagamento`.
  - A transição para `em_separacao` exige financeiro `pago`.
  - `transicionar()` não aceita mais estados financeiros legados.
  - Eventos `pending`/`refused`/`cancelled` posteriores a um pagamento
    aprovado são ignorados e auditados, sem rebaixar o financeiro.
  - Migration `sales.0002_pedido_status_financeiro` preserva os dados
    existentes.
- CI passa a falhar com cobertura global abaixo de 80%
  (`pytest --cov-fail-under=80`).
- Deploy passa a exigir `python manage.py createcachetable`.

### Documentação

- `docs/adrs/ADR-001-postgres-local.md`
- `docs/adrs/ADR-002-status-financeiro.md`
- `README.md` atualizado com variáveis de ambiente, produção e segurança.
- `docs/runbook.md` atualizado com cache compartilhado e PostgreSQL/TLS.

### Testes

- Novas suítes: `sales/tests/test_sec01.py`, `sales/tests/test_sec02.py`,
  `customers/tests/test_vinculo.py`, `core/tests/test_sec03.py`,
  `sales/tests/test_sec03.py`, `accounts/tests/test_rate_limiting.py`,
  `core/tests/test_settings_production.py`,
  `sales/tests/test_status_financeiro.py`,
  `sales/tests/test_migracao_status_financeiro.py`.
- Cobertura dos consumidores de status financeiro em `analytics`, `fiscal`,
  `core`, `customers` e `sales`.
