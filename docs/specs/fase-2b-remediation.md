# Remediação da Fase 2B — invariantes de estoque, migração e evidência

**Branch:** `fase-2b-integridade-estoque`
**Base auditada:** `db3c610`
**Objetivo:** fechar B01–B05 e os riscos P2 relevantes (H02–H06), sem regredir a Fase 2A.

## Matriz achado → invariante → teste → implementação → evidência

| Achado | Invariante | Teste de aceite | Implementação | Evidência |
|---|---|---|---|---|
| B01 fallback sem dono | Cancelar/aprovar/expirar A nunca altera bloqueio de B; sem prova, só saldo livre ou pendência auditada | Estoque 10, B reserva 10, A legado item 3; cancelar/aprovar A mantém bloqueio 10 e registra pendência | `_baixar_estoque_do_pedido` sem fallback de bloqueio; `cancelar_pedido` só libera reservas; `Aviso`/`LogAuditoria` de pendência | Testes `test_b01_*` SQLite/PostgreSQL |
| B02 migração histórica | Base histórica migra com segurança e repetibilidade; nenhuma migration posterior esconde passo anterior | Sequência CI `sales 0001 → stock 0001 → fixtures → migrate → verificar` em PostgreSQL 15 | 0002 só schema + delta default 0; 0004 quarentena; 0005 dados/evidência; 0006 constraints/trigger idempotentes | Comando `validar_migracao_legado --criar/--verificar` em SQLite e PostgreSQL 15.8 local; CI pendente |
| B03 contrato de reserva | Reserva respeita pedido, produto, unidade, quantidade agregada e estado; baixa nunca excede o devido | Reserva cancelada/produto divergente/quantidade maior rejeitadas; reserva consumida não baixa de novo; over-reserva não baixa | `reservar` valida contrato sob lock; `consumir_reserva` valida devido; `_baixar_estoque...` considera consumidas e registra pendência | Testes `test_b03_*` |
| B04 escritores alternativos | Toda alteração de saldo passa por serviço/ledger; seed não zera bloqueio nem altera saldo sem evento | Rodar seed com estoque/ledger/reserva; saldo e ledger reconciliam; seed recusa ambiente não descartável | Comando `semear_estoque_demo` via `registrar_ajuste`; guarda `ALLOW_DEMO_SEED=1` em qualquer banco | Teste do comando + docs |
| B05 evidência histórica | Não inventar 0,01; preservar dados/proveniência; baseline e quarentena explícitas | Fixtures com ajuste sem auditoria, transferência ambígua, zero, reserva parcial e bloqueio sem dono | `ReconciliacaoEstoqueLegado`, `BloqueioLegado`, delta 0 como sentinela, falha diagnosticada para zero | `validar_migracao_legado` + testes de migração |
| H02 deadlock | Ordem global de locks em transferências e múltiplos produtos | Duas transferências A→B/B→A e checkouts inversos terminam sem deadlock | Prelock ordenado por `(produto_id, unidade_id)`; retry só na borda transacional | Teste `@pytest.mark.postgres` |
| H03 defesa do ledger | `_update_permitido` só altera `movimento_par`; par válido, sem auto-vínculo; TRUNCATE bloqueado | SQL direto TRUNCATE/par inválido rejeitado; Python rejeita outros campos | QuerySet restrito; trigger valida tipo/par e `BEFORE TRUNCATE` | Teste PostgreSQL |
| H04 PII | Documentos formatados/minúsculos mascarados | `_mascarar` cobre CPF/CNPJ formatados e alfanumérico minúsculo | Regex ampliada | Teste unitário |
| H05 não finitos | Valores financeiros/quantidades finitos | `NaN`/`Infinity` rejeitados no serviço e no banco | `Decimal.is_finite()` + checks de limite superior | Teste SQLite + PostgreSQL |
| H06 cotação | Carrinho e checkout usam a mesma cotação | Carrinho de atacadista verificado mostra o preço final | `sales/pricing.py` compartilhado; carrinho consulta cliente verificado | Teste de carrinho/checkout |

## Invariantes mínimos

1. `0 <= quantidade_bloqueada <= quantidade` e `quantidade >= 0`.
2. `quantidade == SUM(delta)` por (produto, unidade), com baseline explícita.
3. `quantidade_bloqueada == SUM(reservas ativas) + SUM(bloqueios legados ativos)`.
4. Operações de A não reduzem reserva/bloqueio de B.
5. Baixa acumulada por pedido/produto nunca excede o devido e não repete.
6. Reservas novas exigem pedido/produto/unidade/quantidade coerentes e estado pré-pagamento.
7. Valores são finitos; checks de negativos e total permanecem.
8. Fase 2A (titularidade, financeiro, exportação) não regride.

## Política de migração

- `stock/0002`: schema apenas; `delta` entra não nulo com default temporário 0, sem
  `ALTER TABLE` após DML.
- `stock/0003`: reservas; não libera bloqueio sem dono.
- `stock/0004`: cria `BloqueioLegado` e `ReconciliacaoEstoqueLegado`; quarentena o
  excedente de bloqueio sem reserva, sem alterar o agregado.
- `stock/0005`: calcula `delta` apenas para o sentinela 0; registra evidência; falha
  com diagnóstico para movimento de quantidade zero; baseline explícita para residual.
- `stock/0006`: constraints e trigger idempotentes (compatível com bancos que já
  aplicaram a 0002 antiga).
- `sales/0008`: limites superiores para rejeitar NaN/Infinity.
- `sales/0011`: reconstrói obrigações a partir de movimentos atribuíveis, sem
  escrever no ledger.
- `sales/0012`: adiciona `tipo_pendencia` e reclassifica falta, ambiguidade e
  excesso; preserva decisões de conciliação já registradas.
- `stock/0010`: troca a FK de atribuição para `PROTECT` e atualiza o trigger
  imutável para incluir `obrigacao_id`; cobre bancos que já aplicaram `stock/0006`.

## Pontos de partida e limite U04

- **Suportados:** banco vazio até HEAD; banco em `817d1e8` (que já tem `sales/0002`
  aplicada) até HEAD; banco já em `sales/0009`/`0011` recebendo `sales/0012` e
  `stock/0010`. O validador cobre 0001 vazio e a base histórica com fixtures.
- **Não suportado como atualização automática:** base **povoada exatamente na
  `sales/0001`** com pedido em separação e `Pagamento` aprovado. A `sales/0002`
  pode falhar com `cannot CREATE INDEX ... pending trigger events`; é uma
  limitação pré-existente, não uma regressão deste commit. Não execute
  `0001 → HEAD` nesse estado. O caminho suportado é atualizar a partir de
  `817d1e8`/`0009`/`0011`; uma base 0001 povoada exige procedimento DBA ou
  exportação/importação específico, que **não** é validado automaticamente por
  este fluxo. Não há promessa de compatibilidade universal para 0001 povoada.
- O fixture T01-B do validador usa financeiro pago derivado do status operacional;
  ele não representa a limitação U04 nem deve ser lido como suporte a 0001
  povoada com pagamento aprovado.

## Decisões de negócio pendentes

- A regra comercial de atacado (50 fardos, base balcão/online, elegibilidade) permanece
  a implementada na Fase 2B; divergências com o Documento de Operação devem ser
  confirmadas pela operação. Não foram adicionadas novas regras comerciais.

## Execução e evidências

- **B01:** `sales/tests/test_b01_bloqueio_sem_dono.py` — cancelamento, expiração,
  aprovação e reserva parcial com terceiro; reserva de B permanece ativa e bloqueio
  intacto; aprovação gera `Aviso` e `pedido.estoque_pendente`.
- **B02:** sequência `migrate sales 0001 → stock 0001 → validar_migracao_legado --criar
  → migrate → --verificar` passou em SQLite e PostgreSQL 15.8 local, incluindo
  quarentena, baseline, reserva parcial, evidências e as fixtures T01-A/T01-B.
  Reaplicação de 0005/0006 em banco já migrado é idempotente.
- **B03:** `stock/tests/test_b03_contrato_reserva.py` — estados, produto, unidade,
  quantidade, over-reserva, reserva consumida e PROTECT de item/pedido.
- **B04:** `stock/tests/test_seed_estoque.py` — seed via ledger, bloqueio preservado,
  idempotência e recusa de banco não SQLite sem `ALLOW_DEMO_SEED=1`.
- **B05:** evidências `ajuste_sem_prova`, `transferencia_ambigua`, `baseline`,
  `reserva_parcial` e `bloqueio_quarentena` verificadas no comando histórico.
- **H02:** `stock/tests/test_concurrency_postgres.py` — transferências A→B/B→A sem
  deadlock.
- **H03:** teste PostgreSQL de UPDATE/DELETE, TRUNCATE e par inválido; `_update_permitido`
  restrito a `movimento_par`.
- **H04:** `core/tests/test_hardening.py` cobre CPF/CNPJ formatados e CNPJ minúsculo.
- **H05:** `clean()` e limites de coluna rejeitam NaN/Infinity; teste SQL direto no
  PostgreSQL.
- **H06:** `sales/tests/test_regra_atacado.py` valida carrinho e checkout com a mesma
  cotação.

## Resultado da validação

- SQLite local: **496 passed, 14 skipped, 241 subtests**.
- PostgreSQL 15.8 local: **509 passed, 1 skipped (cache Redis), 241 subtests**,
  incluindo B01/B03/R01/T01-T03/U01-U03, concorrência e constraints. Migração
  histórica 0001→HEAD com 9 cenários e T01-A/T01-B também passou. A CI integral do
  novo SHA continua sendo o gate remoto; o Neon permaneceu indisponível para a rodada.
- O PostgreSQL local emitiu o aviso de teardown por conexões remanescentes de testes
  concorrentes; o pytest terminou com exit 0. Os testes U01 novos fecham suas
  conexões explicitamente. O aviso não é ocultado nem tratado como falha de negócio.
- `ruff`, `manage.py check`, `manage.py check --deploy`, `makemigrations --check`,
  Bandit (0 medium/high) e pip-audit (0) aprovados.
- Cobertura desta rodada não foi usada como gate; os números de cobertura anteriores
  não foram reaproveitados como prova das novas invariantes.
- Invariantes verificados no banco local: nenhum ledger divergente, nenhum bloqueio
  divergente e nenhum `delta` nulo/zero.

## Rodada de revisão fresca (pós-remediação)

- **I1:** migrações 0003/0004/0005 validam `is_finite()` de quantidades, bloqueios e
  residual antes de escrever; a migration 0007 adiciona limites superiores em
  `Estoque` e `MovimentoEstoque`, rejeitando NaN/Infinity no PostgreSQL.
- **I2:** cancelamento libera reservas ativas do próprio pedido sempre que o financeiro
  é pendente, inclusive em `RASCUNHO` e em reparo de pedido já `CANCELADO`; pedido pago
  com reserva ativa registra pendência e não libera bloqueio alheio.
- **I3:** documentado que o GUC de `TRUNCATE` é contornável por qualquer role com
  privilégio de truncate; o trigger é proteção contra acidente, não fronteira de
  privilégio. Separação de roles de migration/runtime é requisito operacional.
- **I4:** a 0005 detecta `0,01` sem evidência de baseline e aborta com IDs; cria
  evidência para baselines antigas e documenta a limitação de bases que já aplicaram a
  versão antiga da 0002/0003.

## Limitações e riscos residuais

- O trigger de `TRUNCATE` é proteção contra acidente, **não** fronteira de privilégio:
  qualquer role com privilégio de `TRUNCATE` pode executar
  `SET stock.permitir_truncate='on'` e truncar; o dono das tabelas também pode remover
  o trigger. Produção exige separar o papel de migrations/owner do papel de runtime e
  revogar `TRUNCATE`/DDL do runtime. Superusuário/DBA continua fora do modelo de
  ameaça.
- Bancos que já aplicaram a 0003 antiga tiveram bloqueios sem dono liberados antes desta
  correção; a 0004 só consegue quarentenar o excedente ainda presente. Bases novas
  preservam a evidência desde o início.
- A aprovação financeira pode ficar paga com baixa pendente quando não há saldo livre;
  isso é intencional e observável em `Aviso.Tipo.ESTOQUE_PENDENTE` e na auditoria.
- A regra comercial de atacado continua pendente de confirmação formal da operação.

## Correções residuais da reauditoria (817d1e8)

| ID | Correção | Evidência |
|---|---|---|
| R01 | `ObrigacaoEstoquePedido` persistente por pedido/produto/unidade; transições operacionais bloqueadas com pendência; resolução autorizada/idempotente por saldo livre; baixa complementar vinculada | `sales/tests/test_r01_obrigacao_estoque.py` (SQLite e PostgreSQL); migração `sales/0009`; ADR-015 |
| R02 | `select_for_update(of=("self",))` nas reservas, sem travar produto/pedido via join; locks ordenados por produto/unidade; teste pagamento × transferência | `sales/tests/test_concurrency_postgres.py::test_pagamento_e_transferencia_nao_geram_deadlock` |
| R03 | Testes positivos de seed autorizam `ALLOW_DEMO_SEED=1` com `patch.dict`; teste negativo restaura ambiente; guarda exige confirmação explícita mesmo em SQLite | `stock/tests/test_seed_estoque.py` |
| R04 | `reservar` desconta reservas já consumidas e exige a obrigação restante; não recria compromisso total | `stock/tests/test_b03_contrato_reserva.py` |
| R05 | `resolver_bloqueio_legado` exige justificativa, valida cobertura de reservas/outros bloqueios e audita | teste de cobertura insuficiente + serviço |
| R06 | `seed_demo` classifica pedidos inteiros e exclui pagamento/item/pedido em transação por pedido; falha PROTECT reverte tudo; exige `ALLOW_DEMO_SEED=1` | código + Ruff; execução depende de ambiente demo |
| R07 | Limites superiores de finitude em `ReservaEstoque`, `BloqueioLegado`, `ReconciliacaoEstoqueLegado` (migration `stock/0008`); testes SQL PostgreSQL | `stock/tests/test_b03_contrato_reserva.py` |

## Correções da última reauditoria (00bf5cc)

| ID | Correção | Evidência |
|---|---|---|
| T01 | `sales/obrigacoes.py` reconstrói a baixa por evidência (FK do movimento ou motivo com exatamente um número de pedido). Status pago/avançado não prova baixa; sem evidência fica pendente; excesso é sinalizado; `movimentos`/`ambiguos` ficam no JSON. Migration `sales/0011` corrige a 0009 e bases já migradas; comando `reconstruir_obrigacoes_estoque` reaplica idempotente (dry-run padrão). | `sales/tests/test_t01_reconstrucao_obrigacoes.py`; histórico SQLite/PostgreSQL 15.8 com T01-A/B |
| T02 | `resolver_pendencia_estoque` recebe uma obrigação existente; valida pedido/produto/unidade, financeiro pago/conciliado e pedido não cancelado/estornado; consome reservas ativas do mesmo produto/unidade ou recusa; não cria obrigação; usa saldo livre para o restante. A aprovação repetida libera reserva órfã de obrigação resolvida. | `sales/tests/test_r01_obrigacao_estoque.py` (unidade/produto divergente, não pago, cancelado, reserva ativa/órfã) |
| T03 | Resolver exige usuário ativo, persistido em `resolvido_por`, com perfil Administrador/Gestor; justificativa obrigatória; auditoria na mesma transação e rollback em falha. | testes de usuário/None/inativo/sem grupo e falha de auditoria |

## Correções U01-U03 (b725a2a)

| ID | Invariante | Implementação | Evidência |
|---|---|---|---|
| U01 | Reconstrução não sobrescreve baixa/obrigação confirmada concorrentemente. | `reconstruir_obrigacoes_estoque --aplicar` executa uma transação por obrigação, `select_for_update`, relê a obrigação/movimentos depois do lock, grava somente campos calculados e registra `LogAuditoria` antes/depois. Dry-run não escreve. | `RebuildRaceTests` em `sales/tests/test_evidence_safety.py` (duas conexões PostgreSQL) |
| U02 | Movimento persistido não muda de obrigação; atribuição é evidência protegida. | `stock/0010` faz `AlterField` para `on_delete=PROTECT` e substitui a função/trigger PostgreSQL incluindo `NEW.obrigacao_id IS NOT DISTINCT FROM OLD.obrigacao_id`. INSERT válido continua permitido; UPDATE/NULL/reatribuição e DELETE da obrigação referenciada são recusados. | `ImmutableAssignmentTests` (SQL direto, remoção e `ProtectedError`) |
| U03 | Falta comprovada, ambiguidade pertinente e excesso são distintos; conciliação é explícita e auditável. | `tipo_pendencia` (`falta`/`ambigua`/`excesso`), helper preserva decisões em `evidencia_detalhe`, resolvedor/`_baixar` recusam ambígua/excesso, e `conciliar_obrigacao_historica` registra `atribuir`/`descartar`/`aceitar_excesso` sem criar movimento. Ambiguidades sem o pedido atual não bloqueiam. | `EvidenceSemanticsTests` (ambiguidade, excesso, não pertinente, atribuição, aceite idempotente) |
| U04 | Limite de atualização delimitado. | Base **povoada na 0001** com pagamento aprovado + separação não é suportada devido à fragilidade pré-existente da `sales/0002`; pontos suportados e caminho de backup/importação documentados. Não é regressão de b725a2a. | ADR-015, runbook e seção “Pontos de partida e limite U04” |

### Decisões e limites adicionais

- O trigger de `TRUNCATE` continua sendo proteção contra acidente; o GUC é contornável por
  role com privilégio de truncate. Separação de roles runtime/migrations é requisito
  operacional, não garantia do código.
- O projeto Neon `twilight-silence-34012623` é mantido como QA temporário. Testes que
  dependem de GUC/sessão usam conexão **direta**, não o pooler transacional. A suíte
  integral deve rodar no PostgreSQL local da CI; Neon foi usado para sondagens dirigidas
  por latência/suspensão do compute.
- A execução integral PostgreSQL foi concluída localmente em PostgreSQL 15.8
  (509 passed/1 skipped); o Neon permaneceu indisponível. A CI integral do novo SHA
  ainda é o gate remoto.
