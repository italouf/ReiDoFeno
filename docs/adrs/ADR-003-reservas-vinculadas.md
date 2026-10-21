# ADR-003 — Reservas de estoque vinculadas a pedido

**Fase:** 2B
**Prioridade:** P0
**Depende de:** STO-01 (delta assinado)
**Implementa:** `docs/specs/fase-2b-spec.md` §ADR-003

## Contexto observado

A Fase 1 representa reservas apenas como `Estoque.quantidade_bloqueada`, um agregado
sem identidade. Não é possível saber qual pedido bloqueou qual quantidade, nem garantir
que o cancelamento de um pedido libere exatamente a sua reserva. Duas aprovações ou
aprovação + cancelamento concorrentes podem liberar/baixar a mesma quantidade duas vezes.

## Decisão

Criar `stock.ReservaEstoque`, com vínculo obrigatório a `sales.Pedido`, vínculo opcional
ao `ItemPedido`, produto, unidade, quantidade, status (`ativa`, `consumida`, `liberada`,
`expirada`) e timestamps de consumo/liberação.

Regras:

- `reservar()` exige pedido identificado, trava o estoque, valida o disponível, cria a
  reserva ativa e incrementa `quantidade_bloqueada` via `F()`.
- `consumir_reserva()` é idempotente: só age se a reserva estiver ativa; decrementa o
  bloqueio e grava `MovimentoEstoque` do tipo `baixa_definitiva` com delta negativo.
- `liberar_reserva()` é idempotente: só age se ativa; decrementa o bloqueio e **não**
  grava movimento.
- Uma reserva ativa por (pedido, produto, unidade) — `UniqueConstraint` condicional.
- Quantidade positiva — `CheckConstraint`.
- Reconciliação: `SUM(reservas ativas) == SUM(Estoque.quantidade_bloqueada)` para cada
  par (produto, unidade) criado pela aplicação.

## Integração

- Checkout: cria o `ItemPedido` e em seguida a reserva vinculada.
- Pagamento aprovado: consome as reservas ativas do pedido e baixa a diferença entre o
  item e o total reservado somente se houver saldo **livre**. Se não houver, registra
  pendência auditada e mantém o financeiro pago rastreável. Nunca reduz bloqueio de
  terceiros.
- Cancelamento/expiração: libera somente reservas ativas com identidade do pedido. Não
  existe fallback que reduza `quantidade_bloqueada` sem dono.
- Bloqueios legados sem pedido identificável ficam em `BloqueioLegado` (quarentena),
  reduzem disponibilidade e são resolvidos por operação explícita.
- A baixa efetiva é acompanhada por `ObrigacaoEstoquePedido` (ADR-015); enquanto houver
  obrigação pendente, o pedido não avança para separação/entrega/conclusão.

## Migração de dados

Reservas legadas não têm identidade. A migration 0003 aloca o bloqueio existente aos
pedidos pendentes (`aguardando_pagamento`/`pagamento_pendente`, financeiro pendente),
respeitando a ordem de criação e o saldo bloqueado. O excedente sem dono **não é
liberado**: a migration 0004 o representa em `BloqueioLegado` (quarentena), que continua
reduzindo a disponibilidade até resolução explícita. Quando o bloqueio legado é menor
que o item, a reserva fica parcial; a aprovação consome a reserva e baixa a diferença
apenas com saldo livre, registrando pendência auditada se não houver.

## Alternativas rejeitadas

1. **Reserva por sessão de carrinho:** expira com a sessão, não sobrevive ao checkout e
   não prova qual pedido reservou.
2. **Reserva apenas por produto:** é o estado atual (agregado); não resolve a
   concorrência entre pedidos.
3. **Tabela de reservas sem status:** impede distinguir consumo de liberação e não
   permite idempotência.

## Consequências

- Positivas: rastreabilidade por pedido, idempotência, reconciliação verificável,
  concorrência segura com row-lock e bloqueios sem dono preservados em quarentena.
- Negativas: N reservas por produto (overhead de storage), necessidade de migration para
  o legado e uma fila operacional de bloqueios em quarentena/pendências de baixa.
