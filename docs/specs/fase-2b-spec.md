# Fase 2B — Integridade Financeira e Estoque (spec consolidado)

**Branch:** `fase-2b-integridade-estoque`
**Base:** `main` em `f3e3353` (merge da Fase 2A)
**Data:** 2026-10-20
**Objetivo:** estoque confiável e ledger reconstruível, sem regressão das garantias da
Fase 2A.

## Escopo entregue

| ID | Entrega | Artefatos principais |
|---|---|---|
| STO-01 | Ledger imutável com `delta` assinado | `stock/models.py`, `stock/services.py`, migration `stock/0002`, trigger PostgreSQL |
| ADR-003 | Reservas vinculadas a pedido | `stock.ReservaEstoque`, migration `stock/0003`, integração em `sales/services.py` |
| DAT-01 | Check constraints financeiras | `sales/models.py`, migration `sales/0007` |
| CUS-01 | CNPJ alfanumérico | `customers/validators.py`, `customers/models.py`, fiscal e filtro PII |
| ADR-005 | Titularidade sem vazamento | `sales/views.py`, `privacy/services.py`, `privacy/views.py` |
| Atacado | Preço acima de 50 fardos | `catalog.Produto.preco_atacado`, migration `catalog/0002`, `sales/services.py` |

## Invariantes

1. `Estoque.quantidade == SUM(MovimentoEstoque.delta)` para cada par (produto, unidade)
   após a migration; toda escrita nova passa pelo serviço transacional.
2. `delta != 0` e o sinal é coerente com o tipo; movimentos existentes não podem ser
   alterados/excluídos por instância, QuerySet, bulk ou SQL direto no PostgreSQL.
3. `SUM(ReservaEstoque.quantidade WHERE status='ativa') +
   SUM(BloqueioLegado.quantidade WHERE resolvido_em IS NULL) ==
   Estoque.quantidade_bloqueada`; consumir/liberar são idempotentes e bloqueios sem
   dono ficam em quarentena explícita.
4. Cancelar/aprovar/expirar A nunca reduz reserva/bloqueio de B; sem prova, a baixa usa
   somente saldo livre e registra pendência auditada.
5. `Pedido.total == Pedido.subtotal + Pedido.frete`; valores financeiros e quantidades
   não podem ser negativos (ou zero, no caso da quantidade). A igualdade é comparada
   com arredondamento de 2 casas para ser portátil entre SQLite e PostgreSQL. NaN e
   Infinity são rejeitados no serviço e por limites de coluna.
5. CPF, CNPJ numérico e CNPJ alfanumérico são aceitos; letras são preservadas em
   maiúsculas e o DV oficial é validado.
6. `meus-pedidos` e exportação LGPD exigem `vinculo_verificado` e pedido do próprio
   titular; pedidos de visitante não aparecem.
7. Preço de atacado só se aplica a cliente ATACADO com vínculo comprovado (ou pedido
   criado por vendedor interno), produto em fardo, quantidade > 50 e `preco_atacado`
   preenchido; o preço é congelado no `ItemPedido`.

## Migrations aditivas

- `stock/0002_sto01_delta_assinado`: schema do `delta` (default temporário 0), sem DML
  posterior na mesma transação.
- `stock/0003_adr003_reservas`: cria `ReservaEstoque` e aloca bloqueio legado; não libera
  bloqueio sem dono.
- `stock/0004_remediacao_quarentena`: cria `BloqueioLegado`/`ReconciliacaoEstoqueLegado`,
  quarentena excedente e registra reservas parciais.
- `stock/0005_sto01_dados_legado`: calcula `delta` do sentinela 0, registra evidências e
  falha com diagnóstico para movimento zero.
- `stock/0006_sto01_constraints_trigger`: constraints e trigger idempotentes para bancos
  já migrados.
- `sales/0007_dat01_check_constraints` + `sales/0008_limites_finitos`: checks
  financeiros e limites contra NaN/Infinity.
- `catalog/0002_produto_preco_atacado`: adiciona `preco_atacado` nulo.

Nenhuma migration aplicada em produção foi reescrita; a compatibilidade com bancos que
já aplicaram a versão anterior da 0002/0003 é tratada por 0004–0006 idempotentes.

## Estratégia de testes

- SQLite local (`transaction_mode=IMMEDIATE`): serviços, constraints, CNPJ,
  titularidade, atacado.
- Migração histórica: o comando `validar_migracao_legado` cria estoque, movimentos
  legados (entrada/ajuste) e reserva parcial no schema 0001, migra até HEAD e valida
  `SUM(delta)`, `SUM(reservas ativas)` e a alocação parcial.
- PostgreSQL 15 (CI): trigger do ledger, row-lock e concorrência
  aprovação/cancelamento/consumo de reserva. Testes marcados `@pytest.mark.postgres`
  são ignorados no SQLite por `conftest.py`.

## Decisões e limites registrados

- A migração de `AJUSTE` legado tenta recuperar o sinal via `LogAuditoria`; sem prova,
  assume saída e cria movimento de reconciliação para preservar o saldo operacional.
- Pedidos legados sem reserva identificada usam o caminho agregado de compatibilidade
  até serem migrados; novos pedidos sempre criam reserva.
- O carrinho pré-checkout exibe `preco_online`; o checkout recalcula o preço final. O
  pedido e o pagamento usam o preço correto.
- Outbox de efeitos externos permanece pendente para a Fase 2B/operação (não implementado
  nesta entrega); ver `docs/security/fase2a-remediation-spec.md` §14.

## Gate de saída

- [x] STO-01, ADR-003, DAT-01, CUS-01, ADR-005 e atacado implementados e testados.
- [x] Suíte local: 455 passed, 9 skipped (6 PostgreSQL + 1 Redis + 1 cache), 238
      subtests.
- [x] Migração histórica 0001 → HEAD validada em SQLite e PostgreSQL 15 (ledger,
      reservas, quarentena e evidências).
- [x] PostgreSQL real: 51 testes críticos (B01/B03/H02/H03/H05) + 5 concorrência
      passaram em Neon PostgreSQL 15.
- [ ] Rodada integral PostgreSQL no novo SHA/CI.
- [x] `ruff check`, `manage.py check`, `makemigrations --check --dry-run`.
- [x] Migration completa em banco SQLite vazio.
- [ ] Trigger/concorrência PostgreSQL validados na CI (workflow inclui o branch).
- [x] Specs em `docs/specs/fase-2b/` e ADRs 003/013/014.
- [x] Cobertura: `stock/services.py` 99,02%, `sales/services.py` 93,89%,
      `customers/services.py` 94,55%, total do escopo 91,41%.
- [x] Bandit: 0 medium/high; pip-audit: 0 vulnerabilidades; `ruff`: limpo.
