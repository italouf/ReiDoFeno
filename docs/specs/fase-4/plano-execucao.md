# Fase 4 — Pagamento Manual + Fiscal Assistido: Plano de Execução

**Goal:** Permitir pagamento manual auditável (PIX/dinheiro/cartão), conciliação
financeira e emissão fiscal assistida via IOB, preservando as garantias das
Fases 2A–3.

**Branch:** `fase-4-pagamento-fiscal-manual`

**Base:** `main` @ merge da Fase 3.

**Decisões aprovadas pelo cliente:**
- Sem gateway online no MVP.
- PIX direto, dinheiro e cartão presencial.
- IOB como ERP fiscal; emissão manual assistida.
- Responsáveis financeiros: Nilton, Neto e Caio.

**Adaptações aprovadas sobre o prompt original:**
1. `fiscal.NotaFiscal` é a única fonte de verdade fiscal; recebe snapshot,
   PDF e retenção. Não será criado `NotaFiscalManual` paralelo.
2. Pagamento manual cria/atualiza `sales.Pagamento` (`provedor="manual"`)
   para preservar a receita por pagamento (ADR-016).
3. Pedido não avança para separação no registro do pagamento; a transição
   exige `financeiro_conciliado=True` (ADR-002/015).
4. LGPD mantém pseudonimização numérica única; não usa `"***"`, que violaria
   unicidade e validadores.
5. Retenção usa data de calendário (+5 anos), não `5 * 365` dias.
6. `ComprovantePagamento` ganha `status` (pendente/conciliado/rejeitado) para
   que comprovantes rejeitados não voltem a quitar o pedido.

## Constantes e contratos globais

- Valores monetários: `Decimal`, duas casas, nunca negativos.
- Toda operação financeira/fiscal usa `transaction.atomic()` e `select_for_update()`.
- Toda mudança de estado crítica grava `LogAuditoria` na mesma transação.
- Migrations aditivas, compatíveis com SQLite e PostgreSQL.
- Gates: `ruff check .`, `manage.py check`, `pytest` (suíte completa).
- Cobertura mínima alvo: 85% em `sales/views.py` e `fiscal/views.py`.

---

## Task 1 — PAY-MANUAL

**Files:**
- Modify: `sales/models.py`
- Modify: `sales/services.py`
- Modify: `sales/forms.py`
- Modify: `sales/views.py`
- Modify: `sales/urls.py`
- Modify: `sales/admin.py`
- Modify: `sales/templates/sales/pedido_interno_detail.html`
- Create: `sales/templates/sales/registrar_pagamento_manual.html`
- Create: `sales/migrations/0018_comprovante_pagamento.py`
- Create: `docs/specs/fase-4/pay-manual.md`
- Create: `docs/adrs/ADR-018-pagamento-manual.md`
- Test: `sales/tests/test_pagamento_manual.py`

**Interfaces (Produces):**
- `ComprovantePagamento` (`pedido`, `metodo`, `valor`, `data_pagamento`,
  `referencia`, `observacao`, `arquivo`, `status`, `registrado_por`,
  `registrado_em`).
- `ComprovantePagamento.Metodo`: `pix`, `dinheiro`, `cartao_credito`,
  `cartao_debito`.
- `ComprovantePagamento.Status`: `pendente`, `conciliado`, `rejeitado`.
- `sales.services.registrar_pagamento_manual(pedido, *, metodo, valor,
  data_pagamento, referencia="", observacao="", arquivo=None, usuario,
  request=None) -> ComprovantePagamento`.
- `Pedido.saldo_devedor` e `Pedido.total_comprovantes_ativos`.

**Tests (RED):**
- registra PIX com valor total → `status_financeiro=pago`,
  `financeiro_conciliado=False`, comprovante criado;
- pagamento parcial → status continua `pendente`, comprovante criado;
- valor acima do saldo devedor → erro, nenhum comprovante;
- pedido já pago/estornado/cancelado → 400, nenhum comprovante;
- PIX sem referência → erro de formulário;
- arquivo > 5MB ou tipo inválido → erro;
- upload JPG/PDF válido → arquivo salvo;
- reserva consumida após cobertura total;
- auditoria `pagamento_manual_registrado` com usuário e antes/depois;
- `Pagamento` manual criado com `provedor="manual"`, `status=aprovado`,
  `aprovado_em` = data do pagamento e `valor` = total.

**Steps:**
1. Escrever spec e ADR-018.
2. Escrever testes e rodar: devem falhar por ausência do modelo/serviço.
3. Adicionar modelo + migration.
4. Implementar serviço, form, view, URL e template.
5. Rodar testes da tarefa; suíte fiscal/sales; `ruff`.
6. Commit `PAY-MANUAL: ...`.

---

## Task 2 — CONCILIACAO

**Files:**
- Modify: `accounts/permissions.py`
- Modify: `sales/services.py`
- Modify: `sales/views.py`
- Modify: `sales/urls.py`
- Create: `sales/templates/sales/conciliacao_list.html`
- Create: `docs/specs/fase-4/conciliacao.md`
- Test: `sales/tests/test_conciliacao.py`

**Interfaces (Produces):**
- Grupo `Financeiro` em `accounts.permissions.GRUPOS`.
- `sales.services.conciliar_pagamento_manual(pedido, *, usuario, request=None)`.
- `sales.services.rejeitar_conciliacao_pagamento(pedido, *, justificativa,
  usuario, request=None)`.
- URLs: `gestao/conciliacao/`, `.../<pk>/conciliar/`, `.../<pk>/rejeitar/`.

**Tests (RED):**
- Financeiro concilia pedido pendente → `financeiro_conciliado=True`,
  comprovantes `conciliados`, auditoria `pedido_conciliado`;
- Financeiro rejeita com justificativa → `status_financeiro=pendente`,
  comprovantes `rejeitados`, `Pagamento.status=cancelado` e
  `estornado_em` preenchido, auditoria;
- rejeição sem justificativa → 400;
- vendedor recebe 403;
- vendedor não concilia pedido criado por ele mesmo;
- listagem mostra somente pagos e não conciliados;
- comprovante rejeitado não conta para novo pagamento;
- conciliação sem comprovantes suficientes → 400.

---

## Task 3 — ADR-006 / FISCAL-EXPORT

**Files:**
- Modify: `fiscal/models.py`
- Modify: `fiscal/services.py`
- Modify: `fiscal/forms.py`
- Modify: `fiscal/views.py`
- Modify: `fiscal/urls.py`
- Modify: `fiscal/templates/fiscal/nota_manual_form.html`
- Create: `fiscal/migrations/0007_snapshot_iob_pdf.py`
- Create: `docs/specs/fase-4/adr006-nfe-assistida.md`
- Create: `docs/adrs/ADR-006-nfe-assistida-iob.md`
- Test: `fiscal/tests/test_nota_assistida.py`

**Interfaces (Produces):**
- Campos em `NotaFiscal`: `cliente_nome`, `cliente_documento`,
  `cliente_tipo_pessoa`, `cliente_endereco`, `valor_total`, `itens_json`,
  `pdf`, `data_emissao`.
- `NotaFiscal.Status.ANEXADA`.
- `fiscal.services.exportar_para_iob(pedido) -> dict`.
- `fiscal.services.exportar_para_iob_csv(pedido) -> str`.
- `fiscal.services.snapshot_fiscal(nota, pedido) -> NotaFiscal`.
- URL `fiscal:exportar_iob` (`GET`, `?formato=json|csv`).
- URL `fiscal:nota_anexar` (`POST` multipart; cria/atualiza nota como
  `anexada`).

**Tests (RED):**
- `exportar_para_iob` produz cliente, endereço, itens com NCM e total;
- exportação JSON e CSV com escape de fórmula;
- operador anexa PDF e dados fiscais → nota `anexada`, snapshot preenchido;
- operador registra nota completa → `autorizada` e snapshot preservado;
- PDF inválido/grande → erro;
- auditoria `fiscal.nota_anexada` / `fiscal.nota_manual_registrada`;
- snapshot não muda se cliente for editado depois.

---

## Task 4 — FISCAL-WORKFLOW

**Files:**
- Modify: `fiscal/views.py`
- Modify: `fiscal/urls.py`
- Modify: `fiscal/forms.py`
- Create: `fiscal/templates/fiscal/nota_list.html`
- Create: `docs/specs/fase-4/fiscal-workflow.md`
- Test: `fiscal/tests/test_workflow_fiscal.py`

**Interfaces (Produces):**
- `NotaFiscalListView` com filtro `?status=`.
- `ConfirmarNotaAutorizadaView` (POST).
- `CancelarNotaView` (POST com `justificativa`).
- URLs: `fiscal:nota_lista`, `fiscal:nota_autorizar`, `fiscal:nota_cancelar`.

**Tests (RED):**
- listagem e filtros por status;
- confirmar nota anexada com número/chave → `autorizada` + auditoria;
- confirmar sem número/chave → 400;
- cancelar com justificativa → `cancelada` + auditoria;
- cancelar sem justificativa → 400;
- vendedor recebe 403.

---

## Task 5 — ADR-012 / RETENÇÃO FISCAL

**Files:**
- Modify: `fiscal/models.py`
- Modify: `privacy/services.py`
- Create: `fiscal/management/commands/limpar_notas_expiradas.py`
- Create: `docs/specs/fase-4/adr012-retencao-fiscal.md`
- Create: `docs/adrs/ADR-012-retencao-dados-fiscais.md`
- Test: `privacy/tests/test_retencao_fiscal.py`
- Test: `fiscal/tests/test_retencao.py`

**Interfaces (Produces):**
- `NotaFiscal.retido_ate` calculado em `save()` a partir de `data_emissao`
  com data de calendário +5 anos.
- `anonimizar_cliente` preserva snapshot e audita.
- Comando `limpar_notas_expiradas` (`--dry-run`).

**Tests (RED):**
- nota emitida em 2026-11-10 → `retido_ate=2031-11-10`;
- cliente anonimizado não altera snapshot da nota;
- comando remove somente notas com `retido_ate < hoje`;
- comando audita cada remoção;
- `--dry-run` não remove.

---

## Task 6 — E2E

**Files:**
- Create: `tests_e2e/test_fluxo_pagamento_manual.py`
- Create: `docs/specs/fase-4/e2e-staging.md`
- Modify: `CHANGELOG.md`
- Modify: `docs/runbook.md`

**Fluxo:**
1. Vendedor cria pedido pelo checkout.
2. Vendedor registra PIX manual com comprovante.
3. Financeiro concilia.
4. Emissor Fiscal registra/anexa NF-e.
5. Pedido permanece rastreável com comprovantes e nota.

**Validação operacional:** Nilton/Neto/Caio e staging ficam registrados como
pendência humana no relatório final; não serão declarados como concluídos sem
evidência.

---

## Review Focus

- Pagamento parcial seguido de novo pagamento que cobre o total.
- Rejeição de conciliação seguida de novo pagamento.
- Upload com nome de arquivo malicioso ou conteúdo divergente do tipo.
- Pedido cancelado/estornado durante o registro.
- Corrida entre registrar pagamento e conciliar/rejeitar.
- Snapshot fiscal sobrevivendo à edição/anonimização do cliente.
- Nota expirada vs. nota com data nula.
