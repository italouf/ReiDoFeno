# ADR-008 — CMV por item e snapshot de custo

## Escopo

Implementar custo histórico por item, CMV do pedido e lucro bruto, sem
recalcular vendas passadas quando `Produto.custo` muda.

## Modelo

`ItemPedido.custo_unitario`:

- `DecimalField(max_digits=12, decimal_places=2)`;
- não negativo;
- capturado no checkout a partir de `Produto.custo`;
- imutável após a criação.

Propriedades:

- `ItemPedido.lucro_bruto = (preco_unitario - custo_unitario) * quantidade`;
- `Pedido.cmv = SUM(item.custo_unitario * item.quantidade)`;
- `Pedido.lucro_bruto = subtotal - cmv`.

## Migração

1. Adiciona a coluna nullable.
2. Preenche cada item com o custo corrente do produto.
3. Torna a coluna obrigatória.

## Testes

- snapshot no checkout;
- mudança de `Produto.custo` não altera item existente;
- CMV e lucro bruto do pedido;
- lucro bruto do item;
- mutação por `save()` e por `QuerySet.update()` bloqueada;
- custo negativo rejeitado.

## Critérios de aceite

- [ ] Campo e constraints no banco.
- [ ] Snapshot capturado no checkout.
- [ ] Propriedades de CMV/lucro funcionais.
- [ ] Mutação direta bloqueada.
- [ ] Migração preenche legados.
- [ ] ADR-008 publicada.
