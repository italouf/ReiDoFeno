# Fase 2A — Remediação verificável de segurança

- **Status:** Aceite local concluído no escopo auditado. Código auditado em
  `05e5a2f`; CI confirmada no
  [run 39470071685](https://github.com/italouf/ReiDoFeno/actions/runs/39470071685).
  Os testes E01/E02 e a consolidação documental são o fechamento local
  posterior; a CI do HEAD final será executada na PR.
- **Data:** 2026-10-20
- **Branch:** `fase-2a-seguranca-critica`
- **SHA do código auditado:** `05e5a2f`
- **SHA da auditoria inicial:** `b510978`
- **Base:** `95cd891`
- **CI confirmada:** [run 39470071685](https://github.com/italouf/ReiDoFeno/actions/runs/39470071685) (SHA `05e5a2f`)
- **Referências:** auditoria independente da Fase 2A, `rfenodocs/docs/technical-audit.md`,
  ADR-001, ADR-002.

## 1. Objetivo e gate

Nenhum fluxo pode:

1. liberar pedido/estoque/fiscal sem cobertura financeira válida e comprovada;
2. aplicar resultado financeiro divergente do contrato local do pagamento;
3. expor ou alterar dados/consentimentos de um cadastro que não foi comprovado;
4. decidir uma transição operacional com estado lido antes de outra mutação
   concorrente;
5. perder ou rebaixar um evento financeiro terminal.

O gate só é atendido quando os cenários negativos preservam pedido, pagamento,
estoque, PII e auditoria, e os fluxos legítimos continuam funcionando.

## 2. Matriz requisito → invariante → implementação → testes → evidência → resultado

| Requisito | Invariante de backend | Implementação (fluxo/arquivo) | Teste positivo | Teste negativo | Evidência | Resultado |
|---|---|---|---|---|---|---|
| R1 contrato financeiro | Aprovar/aplicar resultado exige `Pagamento` local, ID consultado/retornado igual, valor exato, BRL, recebedor e ambiente compatíveis | `sales/services.py`, `sales/payments.py`, `sales/views.py` | Webhook oficial aprovado aplica uma vez | Valor/moeda/recebedor/ID/tentativa divergentes não alteram nada e auditam | `sales/tests/test_pay02.py` | Aprovado local e CI `05e5a2f` |
| R2 andamento após estorno | Estado financeiro `estornado`/`cancelado`/`pendente` bloqueia avanço para separação, pronto, enviado e concluído | `sales/models.py`, `sales/views.py` | Pedido pago avança normalmente | Estornado não conclui; pendente não separa | `sales/tests/test_status_financeiro.py` | Aprovado local e CI `05e5a2f` |
| R3 concorrência operacional | Transição operacional relê o pedido sob `select_for_update`, valida estado atual e grava objeto+log na mesma transação | `sales/services.py`, `sales/views.py` | POST válido avança | Instância antiga não reabre cancelado/estornado | `sales/tests/test_operational_transition.py` | Aprovado local e CI `05e5a2f` |
| R4 identidade/PII | Checkout usa snapshot do contato; não expõe nome canônico, não grava consentimento no cadastro não comprovado e não mistura histórico | `sales/services.py`, `sales/emails.py`, templates, `privacy/services.py` | Cliente comprovado mantém consentimento/histórico | Visitante com CPF alheio não vê nome canônico nem altera consentimento | `sales/tests/test_checkout_privacidade.py` | Aprovado local e CI `05e5a2f` |
| R5 prova de vínculo | Prova é nonce persistente, uso único, vinculada ao e-mail/identidade vigente, consumida por POST/CSRF e revogada em mudança relevante | `customers/services.py`, `customers/models.py`, `accounts/views.py` | Link válido confirma uma vez | Reuso, e-mail alterado, usuário errado e expiração falham | `customers/tests/test_vinculo.py` | Aprovado local e CI `05e5a2f` |
| R6 rate limiting/HTTP | Cache compartilhado com incremento atômico; login/checkout/pagamento/webhook com 429/Retry-After; início de pagamento por POST e reuso idempotente | `config/settings/*`, `core/rate_limit.py`, `sales/views.py` | Limites sequenciais e reuso funcionam | 11º POST de pagamento retorna 429; GET não cria preferência | `accounts/tests/test_rate_limiting.py` | Aprovado local e CI `05e5a2f` |
| R7 webhook/estados terminais | Timestamp em s/ms normalizado só na checagem; HMAC usa `ts` original; query/body/ID consistentes; evento ignorado preserva todos os modelos | `sales/payments.py`, `sales/services.py`, `sales/views.py` | Assinatura oficial em s e ms aceita | Adulterada/expirada/divergente rejeitada; `refunded→pending` não rebaixa | `sales/tests/test_pay01.py`, `sales/tests/test_status_financeiro.py` | Aprovado local e CI `05e5a2f` |
| R8 auditoria/legado | Criação de pedido+reserva e efeitos de liberação têm evento transacional; legado inferido é inventariado sem prova fictícia | `sales/services.py`, `core/auditoria.py`, management command | Checkout grava `pedido.criado` | Falha no log reverte pedido, itens e reserva | `sales/tests/test_sec03.py` | Aprovado local e CI `05e5a2f` |
| D01–D03/E01–E02 | Revogação prevalece sobre formulário em andamento; save parcial não invalida prova; correção de metadados é atômica/auditada e reaplicação idempotente | `customers/views.py`, `customers/models.py`, `sales/services.py` | D01/D02/D03 e E01 | Revogação durante edição; falha de auditoria reverte metadados | `customers/tests/test_vinculo.py`, `sales/tests/test_pagamento_metadados.py` | Aprovado local; CI do HEAD final na PR |

## 3. Máquina de estados

### Pedido.status (operacional)

`rascunho → aguardando_pagamento → em_separacao → pronto_para_entrega →
enviado → concluido`

- `cancelado` encerra o andamento.
- `pago`, `pagamento_pendente` e `falhou` são estados legados somente leitura.
- Avanço para `em_separacao`, `pronto_para_entrega`, `enviado` ou
  `concluido` exige `status_financeiro == pago`.
- `estornado`, `cancelado` e `pendente` nunca liberam avanço normal.
- Não haverá exceção administrativa de avanço na 2A; qualquer exceção futura
  exigirá permissão específica, justificativa e auditoria.

### Pedido.status_financeiro

`pendente → pago → estornado`

- `cancelado` encerra o financeiro sem pagamento.
- Aprovação (`approved`) só ocorre com contrato válido.
- `pending`/`in_process` não alteram andamento.
- `refused`/`rejected`/`cancelled` cancelam financeiro e andamento, liberando
  reserva somente se ainda pendente.
- `refunded`/`charged_back` marcam `estornado`, bloqueiam avanço e exigem
  reconciliação operacional.
- Evento ignorado preserva `Pedido`, `Pagamento`, estoque e auditoria.

### Pagamento

`pendente → aprovado`

`pendente → recusado/cancelado`

- Estados terminais (`aprovado`, `recusado`, `cancelado`) não regridem para
  `pendente`.
- Apenas uma tentativa local (`Pagamento` OneToOne) pode ser aplicada; uma
  futura evolução para múltiplas tentativas exigirá ADR própria.
- `init_point` é persistido para reuso idempotente enquanto a tentativa
  estiver pendente.

## 4. Fronteiras de confiança

| Ator | Pode | Não pode |
|---|---|---|
| Visitante | criar pedido com snapshot do contato; pagar pelo token | ver nome canônico, histórico, consentimentos ou exportar dados do titular |
| Cliente comprovado (`Cliente.vinculo_verificado=True`) | ver próprios pedidos verificados, consentimentos e exportação | ver pedidos de terceiros |
| Vendedor | criar pedido interno com `usuario_criador`; consultar clientes | ocupar `Cliente.usuario`, forçar estado financeiro, avançar pedido sem cobertura |
| Gestor/Administrador | operar pedidos, revisar vínculo com justificativa auditada | reescrever histórico financeiro sem evidência |
| Webhook | aplicar somente resultado validado do provedor | aprovar/cancelar sem contrato local válido |
| Jobs | cancelar/expirar somente pedido ainda pendente e não pago | cancelar pedido pago concorrentemente |

## 5. Política para legado

- `status_financeiro` inferido de `pago`/andamento é preservado, mas não é
  tratado como prova do provedor.
- Um comando de inventário lista pedidos financeiros pagos sem `Pagamento`
  aprovado; não reescreve dados nem inventa evidência.
- Vínculos `Cliente.usuario` existentes antes da comprovação ficam com
  `vinculo_verificado=False` e têm acesso a histórico/exportação restrito até
  revisão administrativa ou novo fluxo de comprovação.
- Migrations já aplicadas em ambiente compartilhado não serão reescritas;
  correções futuras usam migration aditiva e procedimento de reconciliação.

## 6. Condições objetivas de aceite

1. Nenhum caminho aprova pagamento sem contrato local válido.
2. Nenhum pedido estornado/cancelado/pendente avança operacionalmente.
3. Transição operacional, pagamento, cancelamento e expiração usam lock e
   releitura; teste determinístico de instância antiga não reabre pedido.
4. Checkout não expõe nome canônico, não grava consentimento alheio e não
   mistura pedido não comprovado com histórico privado.
5. Prova de vínculo é de uso único, expira, exige POST/CSRF e é invalidada por
   mudança de e-mail.
6. Rate limiting usa cache atômico compartilhado; início de pagamento é POST,
   limitado e idempotente.
7. Webhook aceita segundos/milissegundos conforme contrato, mantém HMAC no
   `ts` original e valida query/body/ID.
8. Criação de pedido/reserva é auditada atomicamente; falha de log reverte
   todos os efeitos.
9. Suíte, Ruff, Bandit, pip-audit, checks, migrations e cobertura passam; CI
   executa PostgreSQL e cache real, com limitações externas registradas.

## 7. Estratégia de migração/reversão

- Campos novos são aditivos e nullable/default seguro:
  `Pedido.nome_contato`, `Pedido.identidade_verificada`,
  `Pedido.consentimento_*`, `Pedido.financeiro_conciliado`,
  `Cliente.vinculo_verificado`, `Cliente.identidade_versao`,
  `Pagamento.init_point`, `Pagamento.idempotency_key`,
  `Pagamento.criacao_expira_em`, `VinculoClienteToken`.
- `financeiro_conciliado` e `vinculo_verificado` usam default `False` para
  legado; `identidade_versao` usa default `0`; nenhum deles inventa prova.
- Data migration preenche snapshots legados sem marcar verificação;
  `sales.0002` infere o status financeiro histórico, mas não a prova do
  provedor. As migrations envolvidas são `sales.0002`–`0006` e
  `customers.0004`–`0005`.
- Reversão: desfazer migrations aditivas após backup; nenhum dado financeiro
  é apagado por rollback.
- Nenhuma migration aplicada em ambiente compartilhado será editada; novas
  correções serão migrations aditivas.

## 8. Evidências atuais

- Suíte local (SQLite/cache local): **346 passed, 4 skipped, 230 subtests**.
- Skips: 3 testes de concorrência nativa PostgreSQL e 1 de Redis real sem
  `REDIS_URL`.
- Cobertura global: **89,67%**; `sales/services.py`: **95,20%**;
  `customers/services.py`: **94,55%**.
- Ruff: passou.
- `manage.py check`: passou com 2 checks de backend local silenciados apenas
  em desenvolvimento; produção usa Redis e não os silencia.
- `manage.py check --deploy` com settings de produção + PostgreSQL/Redis
  sintéticos: passou; é validação de configuração, não conectividade real.
- `makemigrations --check --dry-run`: sem alterações.
- Migração histórica 0001 → HEAD validada localmente em SQLite via
  `validar_migracao_legado --criar/--verificar` (7 cenários).
- Bandit: 0 medium/high; B310 0. pip-audit: nenhuma vulnerabilidade conhecida.
- CI do código auditado (`05e5a2f`):
  [run 39470071685](https://github.com/italouf/ReiDoFeno/actions/runs/39470071685)
  concluída com sucesso, incluindo PostgreSQL/Redis, check de produção e
  migração histórica.
- E01/E02 e a consolidação documental são posteriores ao código auditado;
  a CI do HEAD final deve ser executada na PR.
- Não houve deploy, cobrança real ou alteração em dados de produção.

## 9. Limitações externas ainda não validadas localmente

- Row locks e migração histórica em PostgreSQL real: evidência de CI no SHA
  auditado (`05e5a2f`); não executados na máquina local.
- Redis real: teste local é skip sem `REDIS_URL`; a CI executou o cenário.
- Proxy/IP real, SMTP real, Mercado Pago/Bling reais e restore de backup:
  exigem ambiente externo e não foram executados.
- Idempotência externa de `POST /checkout/preferences` ainda depende de
  confirmação/teste no provedor; o fake local não prova o contrato externo.

## 10. Remediação residual da reauditoria (N01–N07)

- **N01:** `ClienteUpdateView` exige `vinculo_verificado` para acesso
  próprio; vínculo pendente recebe 403 em leitura/escrita. Titular
  comprovado que troca e-mail perde a verificação, mas recupera por nova
  prova enviada ao novo e-mail (o destinatário não pode ser escolhido por
  vínculo pendente).
- **N02:** novo `Pedido.financeiro_conciliado`; avanço operacional e
  elegibilidade fiscal exigem prova conciliada, não apenas
  `status_financeiro`. Migração deixa legado como pendente;
  `reconciliar_pedido_financeiro` exige justificativa, audita e não cria
  `Pagamento` fictício. `inventariar_legado` lista pendentes e emite JSON
  puro.
- **N03/N04:** admin trata usuário, e-mail, documento e booleano como
  mudança de identidade; exige justificativa, captura o estado anterior
  antes do save, revoga provas, desmarca histórico e audita antes/depois
  corretos. Troca de titular não herda verificação.
- **N05:** `Cliente.identidade_versao` incrementa em mudanças de
  e-mail/documento/usuário/verificação; a prova guarda a versão. Restaurar
  o e-mail não ressuscita link antigo. Rejeição por hash/versão não grava
  revogação dentro de transação que será revertida.
- **N06:** `Pagamento.idempotency_key` é persistida antes do efeito externo;
  `criacao_expira_em` define janela de recuperação; requisição concorrente
  reutiliza a tentativa e o provedor real recebe `X-Idempotency-Key`.
  Falha/timeout permite retry com a mesma chave.
- **N07:** workflow inclui a branch e `workflow_dispatch`; testes
  `PostgresConcurrencyTests` cobrem cancelamento vs aprovação, avanço vs
  estorno e duas criações de pagamento com conexões/threads independentes,
  executados somente em PostgreSQL.

### Evidência local adicional (histórico N01–N07)

- A baseline histórica imediatamente após N01–N07 foi **343 passed,
  4 skipped, 230 subtests**, cobertura 89,58%.
- A evidência consolidada do fechamento está na seção 8.

## 11. Correções da auditoria de remediação (R01–R04)

- **R01:** criação administrativa com `vinculo_verificado=True` exige
  justificativa e passa por `revisar_vinculo_cliente`; o evento de domínio
  é gravado na transação do admin. Falha de auditoria reverte a criação.
- **R02:** `Cliente.save()` usa `transaction.atomic` +
  `select_for_update`, incrementa a versão em mudança de identidade e faz
  `max(versão_em_memória, versão_no_banco)` em saves de campos não
  sensíveis. Instância antiga não reduz a versão, com ou sem
  `update_fields`.
- **R03:** documento/CPF-CNPJ faz parte do contexto comprovado. A edição
  própria e o admin derrubam `vinculo_verificado` quando e-mail ou
  documento mudam; a recuperação é feita por nova prova no e-mail
  cadastrado.
- **R04:** aprovação válida de pedido legado sincroniza o `Pagamento`
  existente para `aprovado`/`id_externo`/`aprovado_em`, marca
  `financeiro_conciliado` e audita, sem baixa duplicada de estoque. Falha
  de auditoria reverte ambos; repetição é idempotente.

## 12. Correções D01–D03 da reauditoria detalhada

- **D01:** `ClienteUpdateView.form_valid` reabre transação, relê o Cliente
  com `select_for_update` e reautoriza o acesso próprio pelo estado atual.
  Campos de identidade (`usuario`, `vinculo_verificado`,
  `identidade_versao`) são substituídos pelo estado vigente antes do save;
  uma revogação concluída não é restaurada por formulário em andamento.
  Conflito retorna 403 e a edição legítima continua funcionando.
- **D02:** `Cliente.save` calcula mudança de identidade apenas nos campos
  efetivamente persistidos (`update_fields`), trata lista vazia como no-op e
  aplica `max` monotônico na versão. Save parcial de nome não invalida prova
  atual; save de e-mail/documento/usuário/verificação continua
  incrementando a versão.
- **D03:** `_atualizar_pagamento_aprovado` só grava campos que mudaram;
  `aprovado_em` é preenchido apenas quando ausente. Repetição de aprovação
  preserva a primeira data; correções de metadados em pagamento já aprovado
  são auditadas separadamente. Não há escrita nem baixa de estoque na
  repetição.

### Evidência adicional

- Testes locais focados: D01 (revogação antes do save), D02 (save parcial e
  `update_fields=[]`) e D03 (data de aprovação preservada) passaram.
- Suíte completa e gates finais: ver seção 8.

## 13. Testes de fechamento E01/E02

Arquivo rastreado: `sales/tests/test_pagamento_metadados.py`.

- **E01 — correção de metadados auditada e idempotente:** Pedido com
  financeiro pago/prova conciliada e `Pagamento` aprovado sem `id_externo` e
  `aprovado_em`; o resultado aprovado válido preenche ambos, preserva o
  status aprovado e grava
  `pedido.pagamento_aprovado_metadados_corrigidos` com antes/depois
  corretos. Reaplicação preserva a primeira data e não duplica o evento.
- **E02 — falha da auditoria reverte metadados:** falha específica na
  gravação do evento de correção levanta a exceção esperada; ID/data
  continuam ausentes, o status aprovado e o financeiro pago permanecem, e
  não sobra evento parcial.
- Resultado local: 3 testes E01/E02 aprovados (E01 tem dois cenários:
  correção e reaplicação).

## 14. Backlog de continuidade (fora do aceite local)

Estes itens não bloqueiam o aceite local da Fase 2A e não foram implementados
nesta entrega; devem ser tratados nos gates indicados, sem duplicar o backlog
do ADR-002.

| Item | Objetivo | Critério de aceite | Gate |
|---|---|---|---|
| Idempotência externa da preferência | Confirmar o contrato real de `POST /checkout/preferences` para retry/chave repetida | Teste documentado no provedor/sandbox sem preferência duplicada e com o mesmo resultado | Antes de pagamentos reais |
| Outbox de efeitos externos | Retirar e-mail/webhook/fiscal da transação crítica com retry e idempotência | Falha externa não perde nem duplica efeito; estado reconciliável | Fase 2B/operação |
| Imutabilidade de logs | Impedir alteração/exclusão de eventos de auditoria no banco | Update/delete bloqueados e tentativa registrada em ambiente de teste | Antes de produção |
| Proxy/IP e rate limiting | Resolver IP real com proxy confiável sem confiar em cabeçalho arbitrário | Testes de conexão direta e proxy; limites por IP correto | Implantação |
| Backup/restore | Definir RPO/RTO e comprovar restauração | Evidência de restore com data, tamanho e contagens | Go-live |

> **Fase 2B:** o item "Reserva de estoque por pedido" foi implementado em
> `stock.ReservaEstoque` (ADR-003), com consumo/liberação idempotentes e teste de
> concorrência PostgreSQL na CI.
