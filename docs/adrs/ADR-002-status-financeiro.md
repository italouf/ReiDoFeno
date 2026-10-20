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
   - `refused`/`rejected`/`cancelled` → financeiro `cancelado` e andamento
     `cancelado`, liberando a reserva;
   - `charged_back`/`refunded` → financeiro `estornado`; se o andamento já
     estiver em separação/expedição, o cancelamento operacional é registrado
     como pendente (`pedido.estorno_com_andamento`) para revisão manual.
6. Serviços de pagamento/cancelamento re-leem o pedido com
   `select_for_update()` antes de decidir; a expiração usa
   `permitir_pago=False` para nunca cancelar um pedido pago concorrentemente.
7. Eventos financeiros fora de ordem não rebaixam um pedido já pago nem o
   `Pagamento` aprovado. Uma aprovação tardia de pedido cancelado é
   registrada em `LogAuditoria` (`pedido.pagamento_apos_cancelamento`) e
   exige conciliação manual; o pedido não é reaberto. Eventos `pending`,
   `refused`, `rejected` ou `cancelled` posteriores a um pagamento aprovado
   são ignorados e auditados (`pedido.pagamento_evento_ignorado`).
8. Status oficiais `rejected` e `refunded` são mapeados; `refunded` e
   `charged_back` marcam `estornado`; status desconhecidos são auditados
   (`pedido.pagamento_status_desconhecido`) e `in_mediation` gera
   `pedido.pagamento_em_mediacao`.
9. A aprovação de um pedido em `rascunho`, com financeiro
   `cancelado`/`estornado` ou já em andamento pós-pagamento sem financeiro
   `pago` não altera o pedido; gera
   `pedido.pagamento_inconsistente` para conciliação.
10. A migration `0002_pedido_status_financeiro` popula o novo campo usando
   `Pedido.status` e `Pagamento.status`:
   - estados operacionais de pedido pago → `pago`;
   - pagamento aprovado → `pago`;
   - `cancelado`/`falhou` ou pagamento recusado/cancelado → `cancelado`;
   - demais → `pendente`.

## Remediação da auditoria independente (2026-10-20)

- **R1/PAY-02:** `aplicar_resultado_pagamento` valida `Pagamento` local,
  ID consultado/retornado, `external_reference`, valor exato, BRL, recebedor
  e `live_mode` antes de qualquer mutação. Divergência gera
  `pedido.pagamento_contrato_invalido` e não altera pedido/pagamento/estoque.
- **R2:** qualquer avanço para separação, pronto, enviado ou concluído exige
  `status_financeiro=pago`; estornado/cancelado/pendente não avançam.
- **R3:** `alterar_status_operacional()` relê o pedido com
  `select_for_update` e aplica o recorte de autorização antes de decidir.
- **R4:** `Pedido.nome_contato` é snapshot do checkout; público/e-mails usam
  esse nome, não o nome canônico. `identidade_verificada` só é verdadeiro
  para cliente comprovado; pedidos não verificados não entram em
  `meus-pedidos`/exportação e não gravam consentimento no cadastro canônico.
- **R5/R10:** prova de vínculo é nonce hasheado, uso único, expira, é
  vinculada ao e-mail do cadastro e consumida por POST/CSRF. Vínculos legados
  ficam `vinculo_verificado=False` até revisão administrativa; admin exige
  justificativa e audita.
- **R6:** rate limiting usa Redis com incremento atômico; início de pagamento
  é POST, limitado e idempotente por `Pagamento.init_point`.
- **R7:** timestamp aceita segundos/milissegundos (HMAC preserva o valor
  original); query/body/ID precisam concordar; evento ignorado preserva
  Pedido, Pagamento e estoque.
- **R8:** criação de pedido/reserva é auditada atomicamente; liberação de
  reserva também; `inventariar_legado` lista dados sem prova sem reescrever
  histórico.
- **N02:** `Pedido.financeiro_conciliado` distingue status histórico de prova;
  legado pago sem evidência fica bloqueado até `reconciliar_pedido_financeiro`
  com justificativa/auditoria.
- **N05:** `Cliente.identidade_versao` invalida provas antigas de forma
  durável mesmo se o e-mail for restaurado.
- **N06:** `Pagamento.idempotency_key` e `criacao_expira_em` são persistidos
  antes do efeito externo; a preferência usa `X-Idempotency-Key`.
- **R04:** aprovação válida de pedido legado sincroniza o `Pagamento`
  existente e `financeiro_conciliado`, sem repetir baixa de estoque.
- **R02/R03:** `identidade_versao` é monotônica sob lock e documento/CPF-CNPJ
  faz parte do contexto comprovado; alteração exige nova comprovação.

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
