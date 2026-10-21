# ADR-015 — Obrigação persistente de baixa de estoque

**Status:** Aceito
**Data:** 2026-10-21
**Fase:** 2B — remediação R01 e T01-T03
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
- `resolver_pendencia_estoque()` recebe uma obrigação existente (não cria
  obrigação), exige usuário ativo com perfil Administrador/Gestor, justificativa,
  pedido pago/conciliado, não cancelado/estornado, produto na lista de itens e
  unidade do pedido; consome reservas ativas do mesmo produto/unidade e usa saldo
  livre para o restante, com auditoria e rollback; a aprovação repetida libera
  reservas órfãs de obrigação já resolvida;
- cancelamento antes do pagamento marca as obrigações como `cancelada`; pedido pago com
  reserva/obrigação ativa registra pendência para revisão.

## Backfill e evidência

A migration 0009 não pode usar apenas status pago/avançado nem soma de reservas
consumidas. A migration 0011 reconstrói `quantidade_baixada` por evidência atribuível:

- FK `MovimentoEstoque.obrigacao` para lançamentos novos;
- para o legado, movimento `baixa_definitiva`/`saida` cujo motivo contenha exatamente
  um número de pedido igual ao da obrigação;
- motivo com múltiplos pedidos é ambíguo e não é contado;
- sem evidência, a obrigação permanece pendente e bloqueia avanço; não se inventa baixa;
- evidência maior que a obrigação é limitada e sinalizada para revisão;
- o comando `reconstruir_obrigacoes_estoque --aplicar` repete a reconstrução de forma
  idempotente em bases que já aplicaram a 0009. O dry-run é o padrão.

`evidencia_baixada` e `evidencia_detalhe` preservam os IDs, deltas e origem da prova.

## Procedimento de atualização e conciliação

1. Aplicar as migrations. A `sales/0011` corrige automaticamente bases que já
   aplicaram a `0009` e bases que ainda vão aplicá-la; não há escrita no ledger.
2. Executar `python manage.py reconstruir_obrigacoes_estoque` (dry-run) e revisar o
   relatório; usar `--aplicar` somente após conferir os candidatos. A operação é
   idempotente e pode ser repetida.
3. Se `evidencia_baixada < quantidade_devida`, a obrigação fica pendente e bloqueia
   o avanço. Não registrar baixa sem prova física. Quando houver saldo/estoque
   conferido e pedido pago, resolver a obrigação existente com ator
   Administrador/Gestor e justificativa; o serviço consome reservas do próprio
   pedido e/ou saldo livre, com movimento e auditoria.
4. Pedido cancelado/estornado tem a obrigação cancelada; reservas ativas órfãs de
   obrigação já resolvida são liberadas na aprovação, sem consumo duplicado.

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
  legados sem evidência atribuível permanecem pendentes até conciliação explícita.
- Limite: o serviço de resolução consome reservas ativas do próprio pedido e exige
  saldo livre para o restante; repor estoque é decisão operacional.
