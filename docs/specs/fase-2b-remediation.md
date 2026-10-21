# Remediação da Fase 2B — invariantes de estoque, migração e evidência

**Branch:** `fase-2b-integridade-estoque`
**Base auditada:** `db3c610`
**Objetivo:** fechar B01–B05 e os riscos P2 relevantes (H02–H06), sem regredir a Fase 2A.

## Matriz achado → invariante → teste → implementação → evidência

| Achado | Invariante | Teste de aceite | Implementação | Evidência |
|---|---|---|---|---|
| B01 fallback sem dono | Cancelar/aprovar/expirar A nunca altera bloqueio de B; sem prova, só saldo livre ou pendência auditada | Estoque 10, B reserva 10, A legado item 3; cancelar/aprovar A mantém bloqueio 10 e registra pendência | `_baixar_estoque_do_pedido` sem fallback de bloqueio; `cancelar_pedido` só libera reservas; `Aviso`/`LogAuditoria` de pendência | Testes `test_b01_*` SQLite/PostgreSQL |
| B02 migração histórica | Base histórica migra com segurança e repetibilidade; nenhuma migration posterior esconde passo anterior | Sequência CI `sales 0001 → stock 0001 → fixtures → migrate → verificar` em PostgreSQL 15 | 0002 só schema + delta default 0; 0004 quarentena; 0005 dados/evidência; 0006 constraints/trigger idempotentes | Comando `validar_migracao_legado --criar/--verificar` em Neon PostgreSQL 15 |
| B03 contrato de reserva | Reserva respeita pedido, produto, unidade, quantidade agregada e estado; baixa nunca excede o devido | Reserva cancelada/produto divergente/quantidade maior rejeitadas; reserva consumida não baixa de novo; over-reserva não baixa | `reservar` valida contrato sob lock; `consumir_reserva` valida devido; `_baixar_estoque...` considera consumidas e registra pendência | Testes `test_b03_*` |
| B04 escritores alternativos | Toda alteração de saldo passa por serviço/ledger; seed não zera bloqueio nem altera saldo sem evento | Rodar seed com estoque/ledger/reserva; saldo e ledger reconciliam; seed recusa ambiente não descartável | Comando `semear_estoque_demo` via `registrar_ajuste`; guarda `ALLOW_DEMO_SEED=1` para não-SQLite | Teste do comando + docs |
| B05 evidência histórica | Não inventar 0,01; preservar dados/proveniência; baseline e quarentena explícitas | Fixtures com ajuste sem auditoria, transferência ambígua, zero, reserva parcial e bloqueio sem dono | `ReconciliacaoEstoqueLegado`, `BloqueioLegado`, delta 0 como sentinela, falha diagnosticada para zero | `validar_migracao_legado` + testes de migração |
| H02 deadlock | Ordem global de locks em transferências e múltiplos produtos | Duas transferências A→B/B→A e checkouts inversos terminam sem deadlock | Prelock ordenado por `(produto_id, unidade_id)`; retry só na borda transacional | Teste `@pytest.mark.postgres` |
| H03 defesa do ledger | `_update_permitido` só altera `movimento_par`; par válido, sem auto-vínculo; TRUNCATE bloqueado | SQL direto TRUNCATE/par inválido rejeitado; Python rejeita outros campos | QuerySet restrito; trigger valida tipo/par e `BEFORE TRUNCATE` | Teste PostgreSQL |
| H04 PII | Documentos formatados/minúsculos mascarados | `_mascarar` cobre CPF/CNPJ formatados e alfanumérico minúsculo | Regex ampliada | Teste unitário |
| H05 não finitos | Valores financeiros/quantidades finitos | `NaN`/`Infinity` rejeitados no serviço e no banco | `Decimal.is_finite()` + checks de limite superior | Teste SQLite + PostgreSQL |
| H06 cotação | Carrinho e checkout usam a mesma cotação | Carrinho de atacadista verificado mostra o preço final | `sales/pricing.py` compartilhado; carrinho consulta cliente verificado | Teste de carrinho/checkout |

## Invariantes mínimos

1. `0 <= quantidade_bloqueada <= quantidade` e `quantidade >= 0`.
2. `quantidade == SUM(delta)` por (produto, unidade), com baseline explícita.
3. `quantidade_bloqueada == SUM(reservas ativas) + SUM(bloqueios legados ativos)`.
4. Operações de A não reduzem reserva/bloqueio de B.
5. Baixa acumulada por pedido/produto nunca excede o devido e não repete.
6. Reservas novas exigem pedido/produto/unidade/quantidade coerentes e estado pré-pagamento.
7. Valores são finitos; checks de negativos e total permanecem.
8. Fase 2A (titularidade, financeiro, exportação) não regride.

## Política de migração

- `stock/0002`: schema apenas; `delta` entra não nulo com default temporário 0, sem
  `ALTER TABLE` após DML.
- `stock/0003`: reservas; não libera bloqueio sem dono.
- `stock/0004`: cria `BloqueioLegado` e `ReconciliacaoEstoqueLegado`; quarentena o
  excedente de bloqueio sem reserva, sem alterar o agregado.
- `stock/0005`: calcula `delta` apenas para o sentinela 0; registra evidência; falha
  com diagnóstico para movimento de quantidade zero; baseline explícita para residual.
- `stock/0006`: constraints e trigger idempotentes (compatível com bancos que já
  aplicaram a 0002 antiga).
- `sales/0008`: limites superiores para rejeitar NaN/Infinity.

## Decisões de negócio pendentes

- A regra comercial de atacado (50 fardos, base balcão/online, elegibilidade) permanece
  a implementada na Fase 2B; divergências com o Documento de Operação devem ser
  confirmadas pela operação. Não foram adicionadas novas regras comerciais.

## Execução e evidências

- **B01:** `sales/tests/test_b01_bloqueio_sem_dono.py` — cancelamento, expiração,
  aprovação e reserva parcial com terceiro; reserva de B permanece ativa e bloqueio
  intacto; aprovação gera `Aviso` e `pedido.estoque_pendente`.
- **B02:** sequência `migrate sales 0001 → stock 0001 → validar_migracao_legado --criar
  → migrate → --verificar` passou em SQLite e PostgreSQL 15 (Neon), incluindo
  quarentena, baseline, reserva parcial e evidências. Reaplicação de 0005/0006 em banco
  já migrado é idempotente.
- **B03:** `stock/tests/test_b03_contrato_reserva.py` — estados, produto, unidade,
  quantidade, over-reserva, reserva consumida e PROTECT de item/pedido.
- **B04:** `stock/tests/test_seed_estoque.py` — seed via ledger, bloqueio preservado,
  idempotência e recusa de banco não SQLite sem `ALLOW_DEMO_SEED=1`.
- **B05:** evidências `ajuste_sem_prova`, `transferencia_ambigua`, `baseline`,
  `reserva_parcial` e `bloqueio_quarentena` verificadas no comando histórico.
- **H02:** `stock/tests/test_concurrency_postgres.py` — transferências A→B/B→A sem
  deadlock.
- **H03:** teste PostgreSQL de UPDATE/DELETE, TRUNCATE e par inválido; `_update_permitido`
  restrito a `movimento_par`.
- **H04:** `core/tests/test_hardening.py` cobre CPF/CNPJ formatados e CNPJ minúsculo.
- **H05:** `clean()` e limites de coluna rejeitam NaN/Infinity; teste SQL direto no
  PostgreSQL.
- **H06:** `sales/tests/test_regra_atacado.py` valida carrinho e checkout com a mesma
  cotação.

## Limitações e riscos residuais

- O trigger de `TRUNCATE` é bloqueado em produção, mas testes habilitam o GUC
  `stock.permitir_truncate` para o flush do Django. Superusuário/DBA com
  `session_replication_role=replica` ainda pode contornar; o limite de confiança é o
  papel de runtime, não o proprietário da base.
- Bancos que já aplicaram a 0003 antiga tiveram bloqueios sem dono liberados antes desta
  correção; a 0004 só consegue quarentenar o excedente ainda presente. Bases novas
  preservam a evidência desde o início.
- A aprovação financeira pode ficar paga com baixa pendente quando não há saldo livre;
  isso é intencional e observável em `Aviso.Tipo.ESTOQUE_PENDENTE` e na auditoria.
- A regra comercial de atacado continua pendente de confirmação formal da operação.

