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
3. `SUM(ReservaEstoque.quantidade WHERE status='ativa') ==
   Estoque.quantidade_bloqueada` para reservas criadas pela aplicação; consumir/liberar
   são idempotentes.
4. `Pedido.total == Pedido.subtotal + Pedido.frete`; valores financeiros e quantidades
   não podem ser negativos (ou zero, no caso da quantidade).
5. CPF, CNPJ numérico e CNPJ alfanumérico são aceitos; letras são preservadas em
   maiúsculas e o DV oficial é validado.
6. `meus-pedidos` e exportação LGPD exigem `vinculo_verificado` e pedido do próprio
   titular; pedidos de visitante não aparecem.
7. Preço de atacado só se aplica a cliente ATACADO, produto em fardo, quantidade > 50 e
   `preco_atacado` preenchido; o preço é congelado no `ItemPedido`.

## Migrations aditivas

- `stock/0002_sto01_delta_assinado`: adiciona `delta`, preenche legado, reconcilia saldo
  via ledger, adiciona constraints e trigger PostgreSQL.
- `stock/0003_adr003_reservas`: cria `ReservaEstoque`, aloca bloqueio legado a pedidos
  pendentes e libera bloqueios sem identidade.
- `sales/0007_dat01_check_constraints`: valida dados existentes e adiciona checks de
  Pedido/ItemPedido/Pagamento.
- `catalog/0002_produto_preco_atacado`: adiciona `preco_atacado` nulo.

Nenhuma migration aplicada foi reescrita.

## Estratégia de testes

- SQLite local (`transaction_mode=IMMEDIATE`): serviços, constraints, CNPJ,
  titularidade, atacado.
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
- [x] Suíte local: 413 passed, 6 skipped (5 PostgreSQL + 1 Redis), 230 subtests.
- [x] `ruff check`, `manage.py check`, `makemigrations --check --dry-run`.
- [x] Migration completa em banco SQLite vazio.
- [ ] Trigger/concorrência PostgreSQL validados na CI (workflow inclui o branch).
- [x] Specs em `docs/specs/fase-2b/` e ADRs 003/013/014.
- [x] Cobertura: `stock/services.py` 99,02%, `sales/services.py` 93,88%,
      `customers/services.py` 94,55%, total do escopo 91,22%.
- [x] Bandit: 0 medium/high; pip-audit: 0 vulnerabilidades; `ruff`: limpo.
