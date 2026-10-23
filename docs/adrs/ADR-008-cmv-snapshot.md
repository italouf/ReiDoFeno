# ADR-008 — CMV por item com snapshot de custo

## Contexto

`Produto.custo` é um valor corrente. Recalcular o custo de uma venda passada
com o valor atual distorce o CMV e o lucro bruto sempre que o fornecedor
reajusta o preço. O documento de operação exige saber o lucro por produto e
por venda.

## Decisão

1. `ItemPedido.custo_unitario` é um snapshot imutável de `Produto.custo` no
   momento em que o item é criado no checkout.
2. `ItemPedido.lucro_bruto = (preco_unitario - custo_unitario) * quantidade`.
3. `Pedido.cmv = SUM(custo_unitario * quantidade)` dos itens.
4. `Pedido.lucro_bruto = subtotal - cmv` (frete não entra no lucro bruto de
   mercadoria).
5. Alterações diretas de `custo_unitario` por `save()` ou `QuerySet.update()`
   levantam `ImutabilidadeViolation`. Correções exigem um procedimento
   auditado fora do fluxo normal.
6. Itens legados recebem, na migração, o custo corrente do produto como
   melhor evidência disponível. O ADR registra que esse valor é aproximado.

## Consequências

- Reajustes de custo não reescrevem vendas passadas.
- O checkout precisa capturar o custo dentro da mesma transação do item.
- Relatórios por produto/dia/unidade podem somar CMV sem consultar o catálogo
  atual.
- Itens criados fora do checkout (importações, comandos) devem informar o
  snapshot explicitamente.
- A reversão de CMV é um evento físico: `MovimentoEstoque` do tipo
  `entrada_devolucao`, vinculado à obrigação, na data do movimento. A
  quantidade é a baixa comprovada ainda não compensada; devolução parcial é
  suportada. Estorno financeiro/chargeback não reverte CMV por si só
  (ADR-017).
- Sem obrigação/evidência de baixa, nenhum saldo é creditado e uma pendência
  auditável é registrada para conciliação.
- A proteção de imutabilidade cobre `save`, `QuerySet.update` e `bulk_update`
  da aplicação. SQL bruto, `_base_manager` e leitura concorrente seguida de
  escrita ainda podem contornar a checagem; um trigger PostgreSQL dedicado
  fica como endurecimento da Fase 3, pois o dado é tratado como confiável
  dentro do processo Django.
