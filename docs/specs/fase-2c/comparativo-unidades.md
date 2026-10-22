# Painel comparativo FS vs Iaçu

## Objetivo

Comparar, no mesmo período, o desempenho das duas unidades operacionais:
receita, CMV, lucro bruto, número de pedidos e ticket médio.

## Regras

- Endpoint: `/gestao/relatorios/comparativo-unidades/`.
- Acesso: Administrador ou Gestor.
- Filtro: `inicio` e `fim`.
- Receita: pagamentos aprovados no período, agrupados pela unidade do pedido.
- CMV: snapshot de custo dos itens dos pedidos pagos.
- `num_pedidos`: pedidos distintos com pagamento aprovado.
- `ticket_medio = receita / num_pedidos`.
- Unidades ativas sem venda aparecem com zero, para comparação honesta.
- Gráfico de barras agrupadas com receita, CMV e lucro por unidade.

## Testes

- métricas corretas por unidade;
- unidade sem venda aparece com zero;
- ticket médio;
- filtro de período;
- vendedor recebe 403.

## Critérios de aceite

- [ ] Comparativo lado a lado.
- [ ] Métricas corretas.
- [ ] Visualização em barras agrupadas.
- [ ] Acesso restrito.
