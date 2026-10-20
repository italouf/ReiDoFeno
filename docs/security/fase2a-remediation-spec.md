# Fase 2A — Remediação verificável de segurança

- **Status:** Remediação residual N01–N07 implementada; validação local concluída;
  CI PostgreSQL/Redis configurada, aguardando execução no SHA final.
- **Data:** 2026-10-19
- **Branch:** `fase-2a-seguranca-critica`
- **Commit auditado:** `b510978cd5b82638a0b26114fa9506de6478a778`
- **Base:** `95cd891`
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

## 2. Matriz requisito → invariante → fluxo → testes → evidência

| Requisito | Invariante de backend | Fluxo/arquivo | Teste positivo | Teste negativo | Evidência |
|---|---|---|---|---|---|
| R1 contrato financeiro | Aprovar/aplicar resultado exige `Pagamento` local, ID consultado/retornado igual, valor exato, BRL, recebedor e ambiente compatíveis | `sales/services.py`, `sales/payments.py`, `sales/views.py` | Webhook oficial aprovado aplica uma vez | Valor/moeda/recebedor/ID/tentativa divergentes não alteram nada e auditam | `sales/tests/test_pay02.py` |
| R2 andamento após estorno | Estado financeiro `estornado`/`cancelado`/`pendente` bloqueia avanço para separação, pronto, enviado e concluído | `sales/models.py`, `sales/views.py` | Pedido pago avança normalmente | Estornado não conclui; pendente não separa | `sales/tests/test_status_financeiro.py` |
| R3 concorrência operacional | Transição operacional relê o pedido sob `select_for_update`, valida estado atual e grava objeto+log na mesma transação | `sales/services.py`, `sales/views.py` | POST válido avança | Instância antiga não reabre cancelado/estornado | `sales/tests/test_operational_transition.py` |
| R4 identidade/PII | Checkout usa snapshot do contato; não expõe nome canônico, não grava consentimento no cadastro não comprovado e não mistura histórico | `sales/services.py`, `sales/emails.py`, templates, `privacy/services.py` | Cliente comprovado mantém consentimento/histórico | Visitante com CPF alheio não vê nome canônico nem altera consentimento | `sales/tests/test_checkout_privacidade.py` |
| R5 prova de vínculo | Prova é nãoce persistente, uso único, vinculada ao e-mail/identidade vigente, consumida por POST/CSRF e revogada em mudança relevante | `customers/services.py`, `customers/models.py`, `accounts/views.py` | Link válido confirma uma vez | Reuso, e-mail alterado, usuário errado e expiração falham | `customers/tests/test_vinculo.py` |
| R6 rate limiting/HTTP | Cache compartilhado com incremento atômico; login/checkout/pagamento/webhook com 429/Retry-After; início de pagamento por POST e reuso idempotente | `config/settings/*`, `core/rate_limit.py`, `sales/views.py` | Limites sequenciais e reuso funcionam | 11º POST de pagamento retorna 429; GET não cria preferência | `accounts/tests/test_rate_limiting.py` |
| R7 webhook/estados terminais | Timestamp em s/ms normalizado só na checagem; HMAC usa `ts` original; query/body/ID consistentes; evento ignorado preserva todos os modelos | `sales/payments.py`, `sales/services.py`, `sales/views.py` | Assinatura oficial em s e ms aceita | Adulterada/expirada/divergente rejeitada; `refunded→pending` não rebaixa | `sales/tests/test_pay01.py`, `sales/tests/test_status_financeiro.py` |
| R8 auditoria/legado | Criação de pedido+reserva e efeitos de liberação têm evento transacional; legado inferido é inventariado sem prova fictícia | `sales/services.py`, `core/auditoria.py`, management command | Checkout grava `pedido.criado` | Falha no log reverte pedido, itens e reserva | `sales/tests/test_sec03.py` |

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
  `Pedido.consentimento_*`, `Cliente.vinculo_verificado`,
  `Pagamento.init_point`, `VinculoClienteToken`.
- Data migration preenche snapshots legados sem marcar verificação.
- Reversão: desfazer migrations aditivas após backup; nenhum dado financeiro
  é apagado por rollback.
- Nenhuma migration aplicada em ambiente compartilhado será editada; novas
  correções serão migrations aditivas.

## 8. Evidências executadas

- Suíte local (SQLite): 318 passed, 1 skipped (teste de Redis real sem
  `REDIS_URL`), 230 subtests.
- Cobertura local: global ≥80%; `sales/services.py` e
  `customers/services.py` ≥90% (ver relatório final).
- Ruff: passou.
- `manage.py check`: passou com 2 checks de backend local silenciados apenas
  em desenvolvimento; produção usa Redis e não os silencia.
- `manage.py check --deploy` com settings de produção + PostgreSQL/Redis
  sintéticos: passou.
- `makemigrations --check --dry-run`: sem alterações.
- Migração histórica 0001 → HEAD validada localmente em SQLite via
  `validar_migracao_legado --criar/--verificar` (7 cenários).
- CI configurado com serviços PostgreSQL 15 e Redis 7, teste de incremento
  atômico e etapa de migração histórica real em PostgreSQL. Não executado
  neste ambiente local.
- Não houve deploy, push remoto, cobrança real ou alteração em dados de
  produção.

## 9. Limitações externas ainda não validadas

- Row locks e migração histórica em PostgreSQL real: cobertos pela CI
  configurada, não executados localmente.
- Redis real: teste local é skip sem `REDIS_URL`; CI executa.
- Proxy/IP real, SMTP real, Mercado Pago/Bling reais e restore de backup:
  exigem ambiente externo e não foram executados.

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

### Evidência local adicional

- Suíte: **329 passed, 4 skipped, 230 subtests**.
- Skips: 3 testes de concorrência nativa PostgreSQL e 1 de Redis real sem
  `REDIS_URL`.
- Cobertura e ferramentas: ver relatório final.
- A CI não foi executada neste ambiente porque não houve push remoto.
