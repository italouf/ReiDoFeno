# ADR-003 — Reservas vinculadas a pedido (spec)

**Fase:** 2B
**Prioridade:** P0
**ADR:** `docs/adrs/ADR-003-reservas-vinculadas.md`

## Problema

`Estoque.quantidade_bloqueada` é um inteiro agregado. Não há identidade da reserva:
um pedido cancelado pode liberar a reserva de outro; aprovação e cancelamento
concorrentes podem liberar/baixar duas vezes.

## Modelo

`stock.ReservaEstoque`:

| Campo | Tipo | Regra |
|---|---|---|
| `pedido` | FK `sales.Pedido` (CASCADE) | obrigatório |
| `item_pedido` | FK `sales.ItemPedido` (CASCADE) | opcional |
| `produto` | FK `catalog.Produto` (PROTECT) | obrigatório |
| `unidade` | FK `core.Unidade` (PROTECT) | obrigatório |
| `quantidade` | Decimal(12,2) | `> 0` |
| `status` | escolha | `ativa`, `consumida`, `liberada`, `expirada` |
| `criado_em` | datetime | automático |
| `consumida_em` / `liberada_em` | datetime | nulo até a transição |

Constraints:

- única reserva ativa por `(pedido, produto, unidade)`;
- quantidade positiva;
- índice `(produto, unidade, status)` para reconciliação.

## Serviços

- `reservar(produto, unidade, quantidade, pedido, item_pedido=None) -> ReservaEstoque`
  - trava estoque (`select_for_update`), valida disponível, cria reserva ativa e
    incrementa `quantidade_bloqueada` com `F()`.
- `consumir_reserva(reserva) -> ReservaEstoque`
  - idempotente; só consome se `ativa`; decrementa bloqueio; grava movimento
    `baixa_definitiva` com delta negativo; marca `consumida`.
- `liberar_reserva(reserva) -> ReservaEstoque`
  - idempotente; só libera se `ativa`; decrementa bloqueio; marca `liberada`;
    não grava movimento.

## Integrações

- `sales.services.criar_pedido_do_carrinho`: cria `ItemPedido` e reserva vinculada.
- `sales.services.marcar_pagamento_aprovado`: consome reservas ativas e baixa a
  diferença de reserva parcial; fallback agregado para produto sem reservas.
- `sales.services.cancelar_pedido`: libera reservas ativas; fallback agregado apenas
  para pedidos pendentes legados.
- `expirar_pedidos` herda o cancelamento.

## Invariantes

- `SUM(ReservaEstoque.quantidade WHERE status='ativa') ==
  Estoque.quantidade_bloqueada` para reservas criadas pela aplicação.
- Consumir/liberar duas vezes não altera saldo nem cria movimento duplicado.
- Reserva não é criada sem pedido identificado (sem "reserva órfã").

## Critérios de aceite

- [x] Modelo e migration aditiva criados.
- [x] `reservar` exige pedido e cria vínculo.
- [x] `consumir_reserva` idempotente e gera movimento de baixa.
- [x] `liberar_reserva` idempotente e não gera movimento.
- [x] Checkout/pagamento/cancelamento integrados.
- [x] Reconciliação validada por teste.
- [x] Concorrência validada em PostgreSQL (CI).
- [x] Reserva parcial de legado baixa a diferença na aprovação.
