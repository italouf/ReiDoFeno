# Changelog

## [Fase 2C — Analytics Core + Fiscal Manual] — 2026-10-22

- **ANA-01/ADR-016:** receita reconhecida por `Pagamento.aprovado_em`, não por
  `Pedido.status`; `Pagamento.estornado_em` registra o evento negativo. Pedido
  pago em separação conta; concluído sem pagamento não conta; estorno abate na
  data do evento.
- **ADR-008:** `ItemPedido.custo_unitario` é snapshot imutável do custo no
  checkout; `Pedido.cmv`, `Pedido.lucro_bruto` e `ItemPedido.lucro_bruto`
  passam a refletir custo histórico. Migração preenche legados com o custo
  corrente e registra a limitação.
- **ADR-010:** métricas de `/gestao/minhas-metricas/` recortadas por
  `usuario_criador`; painel global restrito a Administrador/Gestor; despesas
  ganham `usuario_responsavel`; recompra filtra clientes do vendedor.
- **Painéis:** relatório de vendas por produto/dia/unidade com CMV, lucro e
  CSV; comparativo FS/Iaçu com receita, CMV, lucro, pedidos e ticket médio.
- **ADR-007:** cancelamento padrão em até 24h e devolução após entrega, com
  justificativa, ator, auditoria, estorno e compensação de estoque por
  `MovimentoEstoque` do tipo `entrada_devolucao`.
- **Fiscal:** NF-e de entrada/devolução com CFOP inverso e chave referenciada
  de 44 dígitos; `NotaFiscal.pedido` passa a `ForeignKey` para permitir saída +
  entrada; cancelamento de NF-e autorizada auditado.
- **Interestadual:** `Unidade.uf`; `Pedido.uf_entrega`, `interestadual` e
  `aliquota_icms` calculados no save; BA→MG a 12%; relatório fiscal destaca
  operações interestaduais e exporta CSV.
- **Emissor Fiscal:** grupo com permissões de NF-e e leitura de pedido, sem
  edição de pedido/cliente/produto/estoque; data migration atribui ao usuário
  `Caio`, se existente.
- **Revisão final:** corrigidos o gate histórico de migração (`validar_migracao_legado`),
  a coerência receita/CMV em devoluções, o CFOP da saída emitida/manual, a
  validação de NF-e de entrada, o redirect do Emissor, o bloqueio do
  cancelamento pago pelo endpoint genérico, a nova rota de cancelamento, o
  backfill de UF/interestadual, a atribuição de despesa e a ordem de locks
  pedido→pagamento.
- **Validação local:** SQLite 598 passed/16 skipped/240 subtests; cobertura
  `analytics/services.py` 98,70% e `sales/services.py` 85,22%; Ruff, check,
  `makemigrations --check`, Bandit (0 medium/high) e pip-audit (0) limpos.
  Gate histórico `0001 → HEAD` validado em SQLite descartável com
  `validar_migracao_legado --criar/--verificar`. A suíte PostgreSQL/Redis de
  CI não foi executada neste ambiente local; os testes marcados como
  PostgreSQL continuam pulados fora da CI.
- **Documentação:** specs em `docs/specs/fase-2c/`; ADRs 007, 008, 010 e 016;
  relatório em `docs/audit/fase-2c-conclusao.md`.

## [Fase 2B — remediação da auditoria independente] — 2026-10-20, encerrada em 2026-10-22

- **B01:** removido o fallback que reduzia `quantidade_bloqueada` sem identidade;
  cancelamento/expiração só liberam reservas do próprio pedido e a aprovação baixa
  somente reservas identificadas + saldo livre, registrando `Aviso`/auditoria quando
  falta saldo. Operações de A não afetam reservas de B.
- **B02:** migração histórica dividida em schema (0002), reservas (0003), quarentena/
  evidência (0004), dados (0005) e constraints/trigger (0006); validada em PostgreSQL 15
  com `validar_migracao_legado --criar/--verificar`.
- **B03:** contrato de reserva valida pedido, estado, produto, unidade e quantidade
  agregada; reserva consumida não baixa de novo; item/pedido com reserva usam PROTECT.
- **B04:** `semear_estoque_demo` grava via ledger, preserva bloqueios e exige
  `ALLOW_DEMO_SEED=1` fora do SQLite; `seed_demo` também tem guarda de ambiente.
- **B05:** `ReconciliacaoEstoqueLegado` registra ajuste sem prova, transferência ambígua,
  baseline e reserva parcial; `BloqueioLegado` mantém bloqueio sem dono em quarentena;
  movimento de quantidade zero falha com diagnóstico em vez de virar 0,01.
- **H02:** locks ordenados em transferências e checkouts de múltiplos produtos; teste
  PostgreSQL de transferências inversas sem deadlock.
- **H03:** `_update_permitido` só aceita `movimento_par`; trigger valida tipo/par e
  bloqueia `TRUNCATE` fora do GUC de teste.
- **H04/H05:** PII formatada/minúscula mascarada; NaN/Infinity rejeitados no serviço e
  por limites no banco.
- **H06:** cotação do carrinho movida para `sales/pricing.py`, compartilhada com o
  checkout e exibindo o preço final para atacadista verificado.
- **R01:** `ObrigacaoEstoquePedido` persistente por pedido/produto/unidade; transições
  para separação/entrega/conclusão bloqueadas enquanto houver baixa pendente; resolução
  autorizada, auditada e idempotente por saldo livre (ADR-015, migration `sales/0009`).
- **R02:** `select_for_update(of=("self",))` nas reservas e locks ordenados; teste
  PostgreSQL de pagamento × transferência sem deadlock.
- **R03:** testes de seed autorizam `ALLOW_DEMO_SEED=1` localmente; teste negativo
  restaura o ambiente; a guarda exige confirmação explícita em qualquer banco.
- **R04:** nova reserva desconta o que já foi consumido e respeita a obrigação restante.
- **R05:** resolução de quarentena exige justificativa e recusa estado sem cobertura de
  reservas/bloqueios.
- **R06:** limpeza do `seed_demo` é atômica por pedido/produto e não apaga pagamento antes
  de falhar em PROTECT.
- **R07:** limites de finitude em reserva, quarentena e evidências (migration
  `stock/0008`), com testes SQL no PostgreSQL.
- **T01:** reconstrução de obrigações por evidência (FK ou motivo com exatamente um
  pedido), com `sales/0011`, `evidencia_baixada`/`evidencia_detalhe` e comando
  `reconstruir_obrigacoes_estoque`; status pago não presume baixa e motivo ambíguo fica
  pendente.
- **T02:** resolvedor recebe obrigação existente, valida pedido/unidade/financeiro,
  consome reservas ativas do mesmo produto/unidade ou recusa, e não cria obrigação.
- **T03:** resolvedor exige usuário ativo Administrador/Gestor, persiste `resolvido_por`,
  justificativa e auditoria transacional com rollback.
- **U01:** reparo de obrigações roda em transação por unidade, com lock e releitura
  após o lock; não sobrescreve baixa concorrente e registra antes/depois.
- **U02:** `stock/0010` torna a atribuição `MovimentoEstoque.obrigacao` imutável
  (`PROTECT` + trigger PostgreSQL com `obrigacao_id`); SQL direto não reatribui/remove
  a prova. Bancos que já aplicaram `stock/0006` recebem a atualização.
- **U03:** `tipo_pendencia` separa falta, ambiguidade e excesso; o resolvedor não
  decide ambiguidade/excesso incidentalmente. `conciliar_obrigacao_historica` registra
  atribuição, descarte ou aceite de excesso com ator/justificativa/auditoria, sem criar
  movimento. Ambiguidades alheias ao pedido não bloqueiam.
- **U04:** base povoada exatamente na `sales/0001` com pagamento aprovado não é
  suportada para atualização automática (limitação pré-existente da `sales/0002`);
  caminhos suportados e restrição documentados. Não é regressão deste commit.
- **C01:** cada saída passa a ter uma única alocação global de evidência
  (`AlocacaoEvidenciaEstoque`, `OneToOne`), gravada sob lock na conciliação. A
  reconstrução consulta essa autoridade, decisões JSON legadas são convertidas e
  conflitos são diagnosticados com IDs, sem escolher dono silenciosamente.
- **Validação:** SQLite 501 passed/15 skipped/241 subtests; PostgreSQL 15.8 local
  515 passed/1 skipped (cache Redis)/241 subtests, incluindo U01-U03/C01,
  concorrência e constraints. A execução independente em PostgreSQL 16.2 +
  Redis 7.4.2 registrou 516 passed/zero skips/241 subtests, SQLite 501/15 e 21
  regressões externas; são números de origem distinta, não da CI. Migração
  histórica 0001→HEAD validada em SQLite e PostgreSQL 15.8 com 9 cenários e
  T01-A/T01-B; upgrades reais 817d1e8→HEAD e b1cc7d2→HEAD passaram. A CI
  `39774481256` do SHA `5ae6bfc0b3ab1fca4789295803aadd07efd0d16b` está verde
  (tests PostgreSQL 15 + Redis, check de produção, migração histórica, lint,
  security e semgrep). Restaram os avisos conhecidos de `URLField` e datetime
  sem timezone; o aviso de teardown de uma execução intermediária não apareceu
  na execução independente final. Ruff, Bandit (0 medium/high), pip-audit (0),
  check, check --deploy e `makemigrations --check` limpos.
- **Documentação de encerramento:** relatório canônico em
  `docs/audit/fase-2b-conclusao.md`; o SHA de código validado é `5ae6bfc` e o
  commit documental posterior tem SHA próprio.

## [Fase 2B — integridade financeira e estoque] — 2026-10-20

- **STO-01:** `MovimentoEstoque.delta` assinado como fonte de verdade;
  `quantidade` derivada; imutabilidade em instância, QuerySet, bulk e trigger
  PostgreSQL; migração reconcilia o saldo legado e tipos de transferência
  passam a ser `transferencia_entrada`/`transferencia_saida`.
- **ADR-003:** `ReservaEstoque` vinculada a pedido/item, com unique parcial,
  consumo/liberação idempotentes, reconciliação com `quantidade_bloqueada` e
  integração no checkout, pagamento aprovado, cancelamento e expiração. A baixa
  cobre reservas parciais de pedidos legados sem deixar saldo remanescente.
- **DAT-01:** check constraints de valores não negativos e
  `total = subtotal + frete`; a igualdade usa arredondamento de 2 casas para ser
  portátil entre SQLite e PostgreSQL; migration valida o legado antes de aplicar.
- **CUS-01:** CPF, CNPJ numérico e CNPJ alfanumérico (ASCII - 48, módulo 11);
  normalização preserva letras maiúsculas; fiscal e filtro de PII atualizados.
- **ADR-005:** `meus-pedidos` exige vínculo comprovado e pedido do titular;
  exportação LGPD sem vínculo retorna 403; tela orienta o usuário pendente.
- **Atacado:** `Produto.preco_atacado` e regra estrita de mais de 50 fardos
  para cliente ATACADO com vínculo comprovado (ou pedido de vendedor interno),
  com preço congelado no `ItemPedido`.
- **Migração histórica:** `validar_migracao_legado` passa a criar estoque,
  movimentos legados e reserva parcial no schema 0001 e valida ledger, reservas
  e alocação após migrar até HEAD.
- **Validação local:** 433 passed, 6 skipped (5 PostgreSQL + 1 Redis), 233
  subtests; cobertura `stock/services.py` 99,02%, `sales/services.py` 93,89%,
  `customers/services.py` 94,55%, total 91,41%; Ruff, Bandit (0 medium/high),
  pip-audit (0 vulnerabilidades), `manage.py check`, `makemigrations --check`
  e migração completa em SQLite aprovados. Trigger e concorrência PostgreSQL
  ficam cobertos pelos testes `@pytest.mark.postgres` na CI.

Todas as mudanças relevantes deste projeto são registradas aqui.

## [Fase 2A — fechamento local E01/E02] — 2026-10-20

- **E01:** teste rastreado confirma que a correção de `id_externo` e
  `aprovado_em` em pagamento legado já aprovado preenche os metadados,
  preserva o status e grava
  `pedido.pagamento_aprovado_metadados_corrigidos` com antes/depois; a
  reaplicação preserva a primeira data e não duplica o evento.
- **E02:** falha controlada na auditoria da correção reverte ID, data e
  evento parcial, preservando o pagamento aprovado e o financeiro conciliado.
- **Documentação:** spec consolidada com SHA auditado `05e5a2f`, CI run
  39470071685, evidências atuais e riscos residuais; sem alteração funcional
  ou migration nesta etapa.
- **Validação local:** 346 passed, 4 skipped, 230 subtests, cobertura
  89,67%; Ruff, Bandit (0 medium/high), pip-audit, check, check de produção
  e migração histórica aprovados. CI do HEAD final pendente de execução na PR.

## [Fase 2A — correções D01–D03] — 2026-10-20

- **D01:** edição própria relê e reautoriza o vínculo sob lock; revogação
  administrativa durante formulário em andamento não é desfeita e retorna 403.
- **D02:** `Cliente.save` considera somente os campos efetivamente escritos
  por `update_fields`; save parcial de nome não invalida prova atual, lista
  vazia é no-op e a versão nunca diminui.
- **D03:** aprovação repetida preserva `aprovado_em`; metadados só são
  corrigidos/auditados quando realmente ausentes/divergentes, sem baixa de
  estoque adicional.

## [Fase 2A — correções R01–R04] — 2026-10-20

- **R01:** criação administrativa verificada exige justificativa e evento de
  domínio; falha de auditoria reverte a criação.
- **R02:** `identidade_versao` é monotônica sob lock; save de instância antiga
  não reduz a versão nem revalida prova.
- **R03:** mudança de CPF/CNPJ na edição própria ou admin derruba a
  verificação e exige nova prova.
- **R04:** aprovação válida de pedido legado sincroniza o `Pagamento`
  existente, sem baixa duplicada de estoque, com auditoria e rollback.

## [Fase 2A — remediação residual N01–N07] — 2026-10-20

- **N01:** vínculo pendente não lê/edita cadastro; e-mail só muda após
  comprovação e recuperação por nova prova no novo endereço.
- **N02:** `Pedido.financeiro_conciliado`; legado pago sem prova não avança
  operacionalmente nem entra na fila fiscal até reconciliação auditada.
- **N03/N04:** admin unifica mudança de usuário/e-mail/documento/verificação,
  exige justificativa, captura o “antes” correto e não herda histórico.
- **N05:** `identidade_versao` persistente invalida provas após mudança e
  restauração de e-mail; revogação não é revertida por erro de validação.
- **N06:** tentativa de pagamento persistida antes do efeito externo, com
  `idempotency_key`, janela de recuperação e header `X-Idempotency-Key`.
- **N07:** CI inclui a branch/workflow_dispatch e testes de concorrência
  PostgreSQL para cancelamento/aprovação, avanço/estorno e criação dupla de
  pagamento. `inventariar_legado --json` emite JSON puro.

## [Fase 2A — remediação da auditoria independente] — 2026-10-20

- **R1/PAY-02:** contrato financeiro completo (tentativa local, ID
  consultado/retornado, valor, BRL, recebedor e `live_mode`) antes de
  qualquer mutação; divergência gera auditoria e não altera estoque/pedido.
- **R2:** pedido estornado/cancelado/pendente não avança para separação,
  pronto, enviado ou concluído.
- **R3:** transição operacional centralizada em serviço com
  `select_for_update`, releitura e autorização por objeto.
- **R4:** `Pedido.nome_contato` e `identidade_verificada` separam contato de
  identidade; checkout não expõe nome canônico nem grava consentimento em
  cadastro não comprovado.
- **R5/R10:** prova de vínculo com nonce hasheado, uso único, expiração,
  POST/CSRF e invalidação por e-mail; vínculos legados exigem revisão
  administrativa com justificativa e auditoria.
- **R6:** rate limiting migrado para Redis com incremento atômico; início de
  pagamento virou POST limitado e idempotente; CI com PostgreSQL/Redis.
- **R7:** timestamp de webhook aceita segundos/milissegundos; query/body/ID
  precisam concordar; eventos ignorados preservam todos os modelos.
- **R8:** criação de pedido/reserva auditada atomicamente; liberação de
  reserva auditada; comando `inventariar_legado` para conciliação read-only.

### Migrations

- `sales.0003_pedido_consentimento_compras_and_more`: snapshot de contato,
  identidade verificada e flags de consentimento do pedido.
- `sales.0004_pagamento_init_point`: reuso idempotente de preferência.
- `customers.0004_cliente_vinculo_verificado_vinculoclientetoken`: estado de
  vínculo comprovado e provas de uso único.

### Documentação

- `docs/security/fase2a-remediation-spec.md`
- ADR-001/ADR-002 e runbook atualizados para VPS, Redis e revisão de legado.

## [Fase 2A] — 2026-10-19 — Contenção de segurança crítica

### Segurança

- **SEC-01:** `/gestao/pedidos/<pk>/status/` rejeita `pago`,
  `pagamento_pendente` e `falhou` com HTTP 403; tentativas são registradas em
  `LogAuditoria` com a ação `tentativa_bloqueada_transicao_financeira`.
- **SEC-02:** o checkout não vincula mais `Cliente.usuario` por CPF/CNPJ.
  Novos clientes também nascem sem vínculo. O vínculo exige link assinado e
  expirável enviado ao e-mail já cadastrado (`/accounts/vincular-cliente/`),
  com auditoria `cliente.vinculo_confirmado`.
- **SEC-03:** novo helper `core.auditoria.auditar_atomicamente()` grava a
  alteração e o `LogAuditoria` na mesma transação. Transições de pedido,
  pagamentos, movimentos de estoque e notas fiscais foram cobertos. O IP é
  capturado de `REMOTE_ADDR`; `X-Forwarded-For` não é aceito diretamente.
- **Rate limiting:** login (`5/m` por IP), checkout (`10/h` por sessão e
  `30/h` por IP), início de pagamento (`10/m` por IP) e webhook (`60/m` por
  IP) retornam HTTP 429 com `Retry-After`.
  `django-ratelimit==4.1.0` adicionado. Em produção o cache é compartilhado
  via `DatabaseCache`.
- **PAY-01:** webhook aceita o formato oficial `ts=...,v1=...` (e o legado
  com `;`), exige `MERCADOPAGO_WEBHOOK_SECRET` no modo real, valida
  `x-request-id`, `data_id` canônico e timestamp dentro de
  `MERCADOPAGO_WEBHOOK_TOLERANCE_SECONDS` (padrão 300s).
- `AXES_FAILURE_LIMIT` ajustado para 6 para que o limite efetivo de 5
  tentativas/minuto seja aplicado pelo rate limiting, mantendo o bloqueio
  temporário do django-axes.
- Produção rejeita `MERCADO_PAGO_FAKE=True` e `BLING_FAKE=True`.
- Serviços de pagamento/cancelamento re-leem o pedido com
  `select_for_update()`; a expiração nunca cancela pedido pago concorrente.
- Eventos oficiais `rejected` e `refunded` são mapeados; eventos fora de
  ordem não rebaixam `Pagamento` aprovado. `in_mediation` e status
  desconhecidos são auditados.
- Migration prioriza estados cumpridos sobre pagamentos recusados antigos.
- Checkout ganhou limite secundário por IP (`30/h`); início de pagamento é
  limitado (`10/m`) e auditado.
- CRUD de `Unidade` passou a ser auditado atomicamente.

### Banco de dados e infraestrutura

- **ADR-001:** produção exige `DATABASE_URL` PostgreSQL, rejeita SQLite e
  força `sslmode=require`. `conn_max_age=600` e health checks ativos.
- **ADR-002:** novo campo `Pedido.status_financeiro`
  (`pendente`, `pago`, `estornado`, `cancelado`).
  - A aprovação do pagamento altera apenas o financeiro e baixa o estoque;
    o andamento permanece em `aguardando_pagamento`.
  - A transição para `em_separacao` exige financeiro `pago`.
  - `transicionar()` não aceita mais estados financeiros legados.
  - Eventos `pending`/`refused`/`cancelled` posteriores a um pagamento
    aprovado são ignorados e auditados, sem rebaixar o financeiro.
  - Migration `sales.0002_pedido_status_financeiro` preserva os dados
    existentes.
- CI passa a falhar com cobertura global abaixo de 80%
  (`pytest --cov-fail-under=80`).
- Deploy passa a exigir `python manage.py createcachetable`.

### Documentação

- `docs/adrs/ADR-001-postgres-local.md`
- `docs/adrs/ADR-002-status-financeiro.md`
- `README.md` atualizado com variáveis de ambiente, produção e segurança.
- `docs/runbook.md` atualizado com cache compartilhado e PostgreSQL/TLS.

### Testes

- Novas suítes: `sales/tests/test_sec01.py`, `sales/tests/test_sec02.py`,
  `customers/tests/test_vinculo.py`, `core/tests/test_sec03.py`,
  `sales/tests/test_sec03.py`, `accounts/tests/test_rate_limiting.py`,
  `core/tests/test_settings_production.py`,
  `sales/tests/test_status_financeiro.py`,
  `sales/tests/test_migracao_status_financeiro.py`.
- Cobertura dos consumidores de status financeiro em `analytics`, `fiscal`,
  `core`, `customers` e `sales`.
