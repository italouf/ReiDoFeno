# ADR-001 — PostgreSQL local na VPS

- **Status:** Aceito
- **Data:** 2026-10-19
- **Fase:** 2A — Contenção de Segurança Crítica
- **Referências:** `rfenodocs/docs/technical-audit.md` (P0/P1 e ADR-001)

## Contexto

O `config/settings/base.py` mantinha fallback para SQLite quando
`DATABASE_URL` não estava definida. Em produção, uma variável ausente podia
fazer a aplicação subir silenciosamente com SQLite, contrariando os requisitos
de concorrência, backup e integridade do sistema financeiro. A auditoria também
registrou que a conexão não exigia TLS.

A decisão de infraestrutura da Fase 2A é operar PostgreSQL **local na VPS**,
sem depender de Neon/Supabase. O contrato de configuração continua sendo
`DATABASE_URL`, o que permite migrar o host sem alterar código.

## Decisão

1. `config/settings/production.py` exige `DATABASE_URL`; sem ela, a aplicação
   falha na inicialização com `ImproperlyConfigured`.
2. Apenas o engine PostgreSQL é aceito em produção. URLs `sqlite://` são
   rejeitadas explicitamente.
3. A conexão usa `ssl_require=True` e força `OPTIONS["sslmode"] = "require"`,
   inclusive se a URL tentar desabilitar TLS.
4. `conn_max_age=600` e `conn_health_checks=True` são habilitados.
5. O fallback SQLite permanece apenas em desenvolvimento/testes, onde é
   adequado ao ciclo local.
6. O cache de rate limiting em produção usa a tabela `reidofeno_cache`
   (`DatabaseCache`), compartilhada entre workers. O deploy deve executar
   `python manage.py createcachetable`.

## Consequências

- O deploy precisa provisionar PostgreSQL com TLS habilitado e definir
  `DATABASE_URL` (ex.: `postgres://usuario:senha@host:5432/reidofeno`).
- Uma configuração ausente ou incorreta falha cedo, em vez de degradar para
  SQLite.
- Backups, restauração e testes de concorrência passam a ser responsabilidade
  da operação da VPS. O runbook deve registrar RPO/RTO e evidência de restore.
- O `render.yaml` existente descreve um PostgreSQL gerenciado do Render e é
  mantido apenas como blueprint legado. Ele não é a fonte da decisão de
  infraestrutura desta fase; se for usado, deve apontar `DATABASE_URL` para o
  banco correto. A remoção/ajuste do blueprint pertence à Fase 3 (Docker/VPS).

## Validação

Testes automatizados em `core/tests/test_settings_production.py`:

- ausência de `DATABASE_URL` → falha;
- `sqlite://` → falha com mensagem de PostgreSQL;
- URL PostgreSQL → engine `django.db.backends.postgresql` e `sslmode=require`.

## Riscos residuais

- PostgreSQL local sem TLS configurado impedirá a conexão; isso é intencional
  e deve ser resolvido na infraestrutura, não no código.
- Rate limiting com `DatabaseCache` exige a tabela criada no deploy. O build
  deve executar `createcachetable` antes de liberar tráfego.
- A decisão não define RPO/RTO; esses números continuam pendentes de aprovação
  da operação e devem constar no runbook antes do go-live.
