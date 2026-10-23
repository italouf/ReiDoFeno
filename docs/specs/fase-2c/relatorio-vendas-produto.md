# Relatório de vendas por produto/dia/unidade

## Objetivo

Responder ao objetivo do cliente: "saber exatamente quanto vende por produto,
por dia, por unidade". O relatório usa a receita de itens de pedidos com
pagamento aprovado no período (ANA-01) e o custo snapshot (ADR-008).

## Regras

- Endpoint: `/gestao/relatorios/vendas-por-produto/`.
- Acesso: Administrador ou Gestor.
- Filtros: `inicio`, `fim`, `unidade`.
- Agrupamento: produto + dia de aprovação + unidade.
- Métricas por linha: quantidade, receita dos itens, CMV e lucro bruto.
- Receita de item = `preco_unitario * quantidade` (frete não é receita de
  produto).
- Aprovação do pagamento define o dia; `Pedido.criado_em` não é usado.
- Exportação: `?formato=csv` (também aceita `format=csv`).
- A tela inclui gráfico de barras por produto.

## Testes

- agrupamento de dois pedidos do mesmo produto no mesmo dia/unidade;
- filtro por unidade;
- CMV e lucro por linha;
- CSV com `Content-Type: text/csv` e conteúdo;
- vendedor recebe 403.

## Critérios de aceite

- [ ] Agrupamento correto.
- [ ] Filtros de período e unidade.
- [ ] CSV funcional.
- [ ] Gráfico renderizado.
- [ ] Acesso restrito à gestão.
