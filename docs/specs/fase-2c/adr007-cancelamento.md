# ADR-007 — Workflow de cancelamento com dois caminhos

## Escopo

Implementar cancelamento padrão (24h) e devolução fiscal, com auditoria,
estorno e compensação de estoque.

## Campos

`Pedido`:

- `tipo_cancelamento` (`padrao`/`devolucao`, nulo quando não cancelado);
- `justificativa_cancelamento` (obrigatória nos serviços);
- `cancelado_em`;
- `cancelado_por`.

## Serviços

- `cancelar_pedido_padrao(pedido, justificativa, usuario)`.
- `registrar_devolucao(pedido, justificativa, usuario)`.
- `estornar_pagamento(pagamento, usuario, motivo)`.
- `fiscal.services.cancelar_nota_fiscal(nota, motivo, usuario)`.
- Rota de gestão: `/gestao/pedidos/<pk>/cancelar/` com escolha do caminho e
  justificativa. O endpoint genérico de status recusa cancelar pedido pago.

## Regras de estoque

Devolução e cancelamento padrão criam `MovimentoEstoque` do tipo
`entrada_devolucao` para a quantidade comprovadamente baixada. Reservas
ativas são liberadas. Obrigações pendentes são canceladas; obrigações
resolvidas permanecem como evidência histórica.

## Testes

- padrão dentro de 24h;
- bloqueio após 24h;
- bloqueio para enviado/concluído;
- devolução cria NF-e de entrada, CFOP inverso e chave referenciada;
- devolução devolve estoque por movimento;
- estorno do pagamento e auditoria;
- idempotência do caminho.

## Critérios de aceite

- [ ] Campos e migração.
- [ ] Dois serviços com validações.
- [ ] Estoque compensado via ledger.
- [ ] NF-e de entrada registrada.
- [ ] Auditoria nos dois caminhos.
- [ ] ADR-007 publicada.
