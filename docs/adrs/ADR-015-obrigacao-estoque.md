# ADR-015 — Obrigação persistente de baixa de estoque

**Status:** Aceito
**Data:** 2026-10-21
**Fase:** 2B — remediação R01
**Relaciona-se:** ADR-003 (reservas), ADR-013 (ledger)

## Contexto

A aprovação de pagamento pode ser reconhecida pelo provedor mesmo quando não há saldo
livre para baixar o pedido. A versão anterior registrava apenas um `Aviso` e uma ação de
auditoria; a máquina de estados operacional continuava exigindo somente financeiro
pago/conciliado. Isso permitia avançar um pedido pago até `CONCLUIDO` sem que a baixa de
estoque tivesse ocorrido.

## Decisão

Criar `sales.ObrigacaoEstoquePedido`, uma obrigação persistente por
(pedido, produto, unidade):

- `quantidade_devida` é criada no checkout e no backfill de migração;
- `quantidade_baixada` só avança na mesma transação do movimento de baixa;
- o status é `pendente`, `resolvida` ou `cancelada`;
- `Pedido.transicionar()` bloqueia `EM_SEPARACAO`, `PRONTO_PARA_ENTREGA`, `ENVIADO` e
  `CONCLUIDO` enquanto existir obrigação pendente;
- o financeiro permanece fiel ao provedor: a pendência não reverte `status_financeiro`;
- `resolver_pendencia_estoque()` exige justificativa/usuário, usa somente saldo livre,
  cria movimento e auditoria, e é idempotente;
- cancelamento antes do pagamento marca as obrigações como `cancelada`; pedido pago com
  reserva/obrigação ativa registra pendência para revisão.

## Alternativas rejeitadas

1. **Booleano `estoque_pendente` no Pedido:** não identifica produto/unidade/quantidade
   nem permite retomada idempotente por item.
2. **Confiar no `Aviso`:** avisos podem ser lidos/ignorados e não são estado de domínio.
3. **Reverter o financeiro quando a baixa falha:** o provedor já confirmou o pagamento;
   o financeiro deve permanecer rastreável e a pendência deve ser operacional.
4. **Baixar reduzindo bloqueio de terceiros:** viola o invariante B01.

## Consequências

- Positivas: transições operacionais refletem a baixa real; retomada auditável e
  idempotente; baixa complementar vinculada ao pedido/produto.
- Negativas: mais uma tabela e um passo operacional para resolver pendências; pedidos
  legados pagos são tratados como resolvidos no backfill.
- Limite: o serviço de resolução exige saldo livre; repor estoque é decisão operacional.
