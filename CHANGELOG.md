# Changelog

Todas as mudanças relevantes deste projeto são registradas aqui.

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
- **Rate limiting:** login (`5/m` por IP), checkout (`10/h` por sessão) e
  webhook (`60/m` por IP) retornam HTTP 429 com `Retry-After`.
  `django-ratelimit==4.1.0` adicionado. Em produção o cache é compartilhado
  via `DatabaseCache`.
- `AXES_FAILURE_LIMIT` ajustado para 6 para que o limite efetivo de 5
  tentativas/minuto seja aplicado pelo rate limiting, mantendo o bloqueio
  temporário do django-axes.

### Banco de dados e infraestrutura

- **ADR-001:** produção exige `DATABASE_URL` PostgreSQL, rejeita SQLite e
  força `sslmode=require`. `conn_max_age=600` e health checks ativos.
- **ADR-002:** novo campo `Pedido.status_financeiro`
  (`pendente`, `pago`, `estornado`, `cancelado`).
  - A aprovação do pagamento altera apenas o financeiro e baixa o estoque;
    o andamento permanece em `aguardando_pagamento`.
  - A transição para `em_separacao` exige financeiro `pago`.
  - `transicionar()` não aceita mais estados financeiros legados.
  - Migration `sales.0002_pedido_status_financeiro` preserva os dados
    existentes.
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
