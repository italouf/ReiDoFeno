# ADR-015 — Obrigação persistente de baixa de estoque

**Status:** Aceito
**Data:** 2026-10-21 — atualizado em 2026-10-22
**Fase:** 2B — remediação R01, T01-T03, U01-U04 e C01
**Relaciona-se:** ADR-003 (reservas), ADR-013 (ledger)
**Encerramento:** [`docs/audit/fase-2b-conclusao.md`](../audit/fase-2b-conclusao.md)

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
- o status é `pendente`, `resolvida` ou `cancelada`; `tipo_pendencia` distingue
  `falta`, `ambigua` e `excesso` sem criar uma máquina genérica de workflow;
- `Pedido.transicionar()` bloqueia `EM_SEPARACAO`, `PRONTO_PARA_ENTREGA`, `ENVIADO` e
  `CONCLUIDO` enquanto existir obrigação pendente;
- o financeiro permanece fiel ao provedor: a pendência não reverte `status_financeiro`;
- `resolver_pendencia_estoque()` recebe uma obrigação existente (não cria
  obrigação), exige usuário ativo com perfil Administrador/Gestor, justificativa,
  pedido pago/conciliado, não cancelado/estornado, produto na lista de itens e
  unidade do pedido; recusa `ambigua`/`excesso`; consome reservas ativas do mesmo
  produto/unidade e usa saldo livre para o restante, com auditoria e rollback; a
  aprovação repetida libera reservas órfãs de obrigação já resolvida;
- `conciliar_obrigacao_historica()` é a operação explícita para atribuir/descartar
  uma saída ambígua ou aceitar um excesso; exige ator, justificativa, lock e
  auditoria, e **não cria movimento**;
- `stock.AlocacaoEvidenciaEstoque` é a autoridade global: no máximo uma alocação
  por movimento (`OneToOne`), com FK `PROTECT` para a obrigação. A conciliação grava
  a alocação sob lock do movimento; o JSON da obrigação é apenas trilha. Assim, uma
  saída de 3 não pode ser creditada integralmente a dois pedidos;
- cancelamento antes do pagamento marca as obrigações como `cancelada`; pedido pago com
  reserva/obrigação ativa registra pendência para revisão.

## Backfill e evidência

A migration 0009 não pode usar apenas status pago/avançado nem soma de reservas
consumidas. A migration 0011 reconstrói `quantidade_baixada` por evidência atribuível:

- FK `MovimentoEstoque.obrigacao` para lançamentos novos; a FK é imutável por
  trigger e a remoção da obrigação é `PROTECT`;
- para o legado, movimento `baixa_definitiva`/`saida` cujo motivo contenha exatamente
  um número de pedido igual ao da obrigação;
- motivo com o pedido atual e outro pedido vira `ambigua`; motivo só com pedidos
  alheios não bloqueia o pedido atual;
- sem evidência, a obrigação permanece pendente (`falta`) e bloqueia avanço; não se
  inventa baixa;
- evidência maior que a obrigação vira `excesso`, é limitada a `quantidade_devida`
  e só encerra por aceite explícito;
- o comando `reconstruir_obrigacoes_estoque --aplicar` relê e trava cada obrigação,
  registra antes/depois e repete a reconstrução de forma idempotente em bases que já
  aplicaram a 0009. O dry-run é o padrão.

`evidencia_baixada` e `evidencia_detalhe` preservam os IDs, deltas, origem e decisões
de conciliação da prova. `tipo_pendencia` separa falta, ambiguidade e excesso. A
reconstrução consulta `AlocacaoEvidenciaEstoque` quando disponível; o JSON não é
autoridade suficiente para atribuir a mesma saída a outro pedido.

A migration `stock/0011` cria a alocação e converte decisões JSON anteriores: uma
reivindicação consistente vira alocação única; reivindicações concorrentes para o
mesmo movimento são mantidas pendentes com `conflitos_alocacao` e IDs para revisão,
sem escolher silenciosamente um dono. A alocação é imutável pela API e por trigger
PostgreSQL contra UPDATE/DELETE; o movimento original continua imutável e nenhuma FK
de movimento é reatribuída.

## Procedimento de atualização e conciliação

1. Aplicar as migrations. A `sales/0011` corrige automaticamente bases que já
   aplicaram a `0009` e bases que ainda vão aplicá-la; `sales/0012` classifica a
   pendência, `stock/0010` protege a atribuição e `stock/0011` cria a alocação
   global e converte decisões JSON. Não há escrita no ledger.
2. Executar `python manage.py reconstruir_obrigacoes_estoque` (dry-run) e revisar o
   relatório; usar `--aplicar` somente após conferir os candidatos. O comando trava
   cada obrigação e relê a evidência antes de salvar.
3. Se `tipo_pendencia` for `ambigua` ou `excesso`, o resolvedor de faltante recusa.
   Usar `conciliar_obrigacao_historica` com decisão `atribuir`, `descartar` ou
   `aceitar_excesso`, ator Administrador/Gestor e justificativa. A conciliação não
   cria movimento compensatório e mantém a trilha no JSON e na auditoria.
4. Se `tipo_pendencia` for `falta`, a obrigação pode ser resolvida com saldo
   conferido e pedido pago; não registrar baixa sem prova física.
5. Pedido cancelado/estornado tem a obrigação cancelada; reservas ativas órfãs de
   obrigação já resolvida são liberadas na aprovação, sem consumo duplicado.

## Limite U04: base povoada na 0001

A atualização automática de uma base **povoada exatamente na `sales/0001`** com
pedido em separação e pagamento aprovado não é suportada. A `sales/0002` é uma
limitação pré-existente (`cannot CREATE INDEX ... pending trigger events`) e não uma
regressão deste ADR. Os pontos suportados são banco vazio, `817d1e8` (com `sales/0002`
já aplicada) e bases já em `0009`/`0011`, incluindo `stock/0011`. Para uma base nesse
estado, usar backup e
importação para um ponto suportado ou intervenção DBA autorizada; esse caminho não é
validado automaticamente e não se deve executar `0001 → HEAD` diretamente.

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
