# DAT-01 — Check constraints em Pedido, ItemPedido e Pagamento

**Fase:** 2B
**Prioridade:** P1
**Depende de:** STO-01, ADR-003
**Implementa:** `docs/specs/fase-2b-spec.md` §DAT-01

## Contexto observado

`Pedido.subtotal`, `Pedido.frete`, `Pedido.total`, `ItemPedido.quantidade`,
`ItemPedido.preco_unitario` e `Pagamento.valor` aceitam valores negativos ou
incoerentes via `objects.create()`, `save()` sem `full_clean()` e SQL direto. Os
serviços calculam os totais, mas não há defesa no banco.

## Regras

| Modelo | Campo | Constraint |
|---|---|---|
| `Pedido` | `subtotal` | `>= 0` |
| `Pedido` | `frete` | `>= 0` |
| `Pedido` | `total` | `>= 0` |
| `Pedido` | `total` | `= subtotal + frete` |
| `ItemPedido` | `quantidade` | `> 0` |
| `ItemPedido` | `preco_unitario` | `>= 0` |
| `Pagamento` | `valor` | `>= 0` |
| Todos os valores | limite superior | `< 10.000.000.000,00` (rejeita NaN/Infinity no PostgreSQL) |

`ItemPedido.subtotal` é uma `@property` (`quantidade × preco_unitario`) e não pode ser
uma constraint de banco; a coerência é garantida pela aritmética da propriedade e pelos
limites dos fatores. `clean()` rejeita valores não finitos antes de qualquer comparação.

## Compatibilidade SQLite/PostgreSQL

As constraints usam apenas comparações e aritmética simples entre colunas, suportadas
por ambos os backends. A igualdade `total = subtotal + frete` é comparada com
`ROUND(..., 2)` para evitar divergência de ponto flutuante no SQLite (por exemplo,
`33.33 + 0.01`); no PostgreSQL o arredondamento de `numeric` também é exato. Não há
`RunSQL` específico de backend.

## Migração

1. Validar os dados existentes antes de aplicar as constraints; se houver violação, a
   migration falha com contagem e exemplos, em vez de deixar o banco em estado parcial.
2. Adicionar as constraints via `AddConstraint`.
3. Manter `recalcular_totais()` como caminho de escrita e adicionar `clean()` aos modelos
   para defesa em profundidade em formulários/admin.

## Critérios de aceite

- [ ] Constraints presentes na migration e no modelo.
- [ ] Testes de violação passam em SQLite e PostgreSQL.
- [ ] Dados legados validados antes da migration.
- [ ] `recalcular_totais()` continua produzindo `total = subtotal + frete`.
- [ ] NaN/Infinity rejeitados pelo serviço e pelo banco.
