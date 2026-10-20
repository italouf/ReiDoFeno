# ADR-002 — Status financeiro separado do andamento operacional

- **Status:** Aceito
- **Data:** 2026-10-19
- **Fase:** 2A — Contenção de Segurança Crítica
- **Referências:** `rfenodocs/docs/technical-audit.md` (ADR-002, PAY-03)

## Contexto

`Pedido.status` misturava dois conceitos distintos:

- **financeiro**: pendente, pago, recusado, estornado;
- **operacional**: aguardando pagamento, em separação, pronto, enviado,
  concluído, cancelado.

Isso permitia que a área interna marcasse um pedido como `pago` por POST
(SEC-01) e fazia a confirmação do provedor alterar o andamento da operação.
Também impedia distinguir um pedido pago que ainda não entrou em separação de
um pedido efetivamente separado.

## Decisão

1. `Pedido.status_financeiro` passa a existir com os valores:
   `pendente`, `pago`, `estornado`, `cancelado`.
2. `Pedido.status` permanece como andamento operacional:
   `rascunho`, `aguardando_pagamento`, `em_separacao`,
   `pronto_para_entrega`, `enviado`, `concluido`, `cancelado`.
   Os valores legados `pago`, `pagamento_pendente` e `falhou` continuam
   legíveis para dados antigos, mas **não podem ser gravados por
   `transicionar()`**.
3. `marcar_pagamento_aprovado()` altera somente `status_financeiro` para
   `pago`, baixa o estoque e atualiza `Pagamento`. O andamento operacional
   permanece em `aguardando_pagamento`.
4. A transição `aguardando_pagamento → em_separacao` exige
   `status_financeiro == "pago"`. Pedido não pago não pode ser separado.
5. Resultados do provedor:
   - `approved` → financeiro `pago`;
   - `pending`/`in_process` → financeiro `pendente`, sem mudar o andamento;
   - `refused`/`cancelled` → financeiro `cancelado` e andamento `cancelado`,
     liberando a reserva;
   - `charged_back` → financeiro `estornado` e andamento `cancelado`.
6. Eventos financeiros fora de ordem não rebaixam um pedido já pago. Uma
   aprovação tardia de pedido cancelado é registrada em
   `LogAuditoria` (`pedido.pagamento_apos_cancelamento`) e exige
   conciliação manual; o pedido não é reaberto.
7. A migration `0002_pedido_status_financeiro` popula o novo campo usando
   `Pedido.status` e `Pagamento.status`:
   - estados operacionais de pedido pago → `pago`;
   - pagamento aprovado → `pago`;
   - `cancelado`/`falhou` ou pagamento recusado/cancelado → `cancelado`;
   - demais → `pendente`.

## Consequências

- Consultas de receita, recompra, NF-e, expiração e avisos passam a usar
  `status_financeiro` (e excluem pedidos operacionalmente cancelados).
- O botão/ação de separação só aparece quando o financeiro está pago.
- O frontend exibe os dois estados separadamente.
- `expiar_pedidos` ignora pedidos com financeiro pago, mesmo que o andamento
  ainda esteja em `aguardando_pagamento`.
- Cancelar um pedido pago **não** presume estorno: o financeiro continua
  `pago` e o caso é auditado para conciliação/estorno manual. O estorno só é
  registrado quando o provedor informa `charged_back`.
- A base está pronta para a Fase 2B tratar tentativas, reembolsos parciais,
  conciliação por valor/moeda/recebedor e reservas por pedido.

## Riscos residuais e trabalho futuro (Fase 2B)

- Não há entidade de tentativa de pagamento; `Pagamento` continua OneToOne.
- Reembolso/estorno manual não altera automaticamente o financeiro para
  `estornado`; isso deve ser um fluxo auditado na 2B.
- Aprovação tardia após cancelamento exige operação manual.
- Os estados legados `pago`, `pagamento_pendente` e `falhou` só devem ser
  removidos depois de uma janela de compatibilidade e nova migration.
- A decisão de receita reconhecida em pedido pago mas ainda não separado deve
  ser validada com a operação (ADR-008).

## Validação

Testes em `sales/tests/test_status_financeiro.py` e
`sales/tests/test_migracao_status_financeiro.py` cobrem:

- aprovação não altera o andamento;
- separação exige financeiro pago;
- transição financeira via `transicionar()` é bloqueada;
- recusa/cancelamento/estorno;
- idempotência da aprovação;
- cancelamento de pedido pago preserva o financeiro;
- migração de dados legados.

Testes de consumidores em `core`, `fiscal`, `analytics`, `customers` e `sales`
verificam que receita, NF-e, avisos, expiração e métricas usam o novo campo.
