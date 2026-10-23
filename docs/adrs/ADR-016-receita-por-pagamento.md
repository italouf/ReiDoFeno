# ADR-016 — Receita reconhecida por pagamento aprovado

## Status

Aceita — Fase 2C.

## Contexto

`analytics/services.py` calculava receita por `Pedido.status_financeiro` e
`Pedido.criado_em`. O resultado divergia do financeiro em quatro situações:

- pedido pago ainda em separação;
- pedido cancelado após pagamento sem estorno registrado;
- pedido concluído sem prova de pagamento;
- estorno não abatido na data do evento.

O modelo já separa andamento (`Pedido.status`) de condição financeira
(`status_financeiro`, ADR-002), mas não registrava a data do estorno.

## Decisão

A receita é um evento financeiro, não um atributo do andamento:

- competência em `Pagamento.aprovado_em`;
- estorno em `Pagamento.estornado_em`, como evento negativo;
- `Pedido.status` não é consultado para reconhecer receita;
- `Pedido.status_financeiro` é usado apenas para excluir pedidos que nunca
  tiveram aprovação válida;
- `Pedido.criado_em` deixa de ser a data de competência.

Foi adicionado `Pagamento.estornado_em`. A transição para `CANCELADO` a partir
de `APROVADO` grava esse campo, seja por chargeback/refund do provedor, seja
por estorno operacional.

O CMV segue a aprovação, mas a reversão é um evento **físico** separado:
apenas `MovimentoEstoque` de `entrada_devolucao` com obrigação comprovada a
reduz. Chargeback reduz receita na data do estorno, mas mantém o CMV até o
retorno físico. A semântica completa está no ADR-017.

## Alternativas consideradas

1. **Manter receita por `Pedido.status`.** Rejeitada: não distingue pagamento
   de andamento e antecipa receita.
2. **Usar `Pedido.atualizado_em` para estorno.** Rejeitada: qualquer alteração
   de cadastro mudaria a competência.
3. **Criar tabela de eventos financeiros.** Mais robusta a longo prazo, mas
   aumenta o escopo da Fase 2C; `Pagamento` mais `estornado_em` cobre o caso e
   pode evoluir para um ledger financeiro na Fase 3.

## Consequências

- Relatórios por período passam a bater com o extrato de pagamentos.
- Dados legados sem `aprovado_em` não geram receita até conciliação.
- Estornos não apagam receita histórica; o total da série fecha em zero.
- Consultas de receita usam `Pagamento`, que é uma tabela menor que
  `Pedido` para agregação.
