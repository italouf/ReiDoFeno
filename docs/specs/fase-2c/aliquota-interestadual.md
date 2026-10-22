# Alíquota interestadual e relatório fiscal

## Objetivo

Identificar vendas interestaduais, aplicar a alíquota de ICMS de 12% na
operação BA→MG e destacar essas vendas no relatório fiscal.

## Modelo

`Unidade.uf` (2 letras, default `BA`).

`Pedido`:

- `uf_entrega` (UF do endereço de entrega; espelha `uf` no checkout);
- `interestadual` (calculado no save);
- `aliquota_icms` (`Decimal(5,4)`, default `0.0000`).

## Regra

- Sem UF de entrega ou sem unidade: não interestadual, alíquota zero.
- Origem e destino iguais: não interestadual, alíquota zero.
- BA→MG: interestadual, 12%.
- Demais operações interestaduais: 12% nesta fase, com possibilidade de
  tabela por UF na integração fiscal futura.

## Relatório fiscal

`fiscal.services.relatorio_fiscal(inicio, fim)` retorna:

- `vendas_intrastaduais`;
- `vendas_interestaduais`;
- `aliquota_interestadual` (0.12);
- `linhas` com pedido, unidade, UF de entrega, indicador e alíquota.

Receita usa pagamentos aprovados no período, alinhada à ANA-01. A tela
`/fiscal/relatorios/` destaca as vendas interestaduais e exporta CSV.

## Testes

- venda BA→BA não interestadual;
- venda BA→MG interestadual a 12%;
- checkout calcula os campos;
- relatório separa intrastadual/interestadual;
- valores não negativos e alíquota limitada.

## Critérios de aceite

- [ ] Campos e migração.
- [ ] Cálculo automático.
- [ ] 12% para BA→MG.
- [ ] Relatório destaca interestaduais.
- [ ] Testes SQLite/PostgreSQL.
