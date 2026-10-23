# Reauditoria L01 — autoridade da tentativa fiscal

Data: 2026-10-22/23
Branch: `fase-2c-analytics-fiscal`
Base auditada: `47f75eb7ce6ca87395f777600d75c157cf44306b`

## Parecer

A correção L01 foi implementada e validada localmente. A suíte SQLite,
cobertura, Ruff, `check`, migração histórica, Node, Bandit e `pip-audit`
passaram. O SHA `2a7a300` foi publicado e a CI `39953967926` aprovou
PostgreSQL 15 + Redis, check de produção e migração histórica; a reauditoria
independente aprovou o Gate T com observações não bloqueantes. O aceite
humano (Gate H) permanece pendente.

## Matriz L01

| ID | Reprodução observada | Causa | Correção | Evidência local |
|---|---|---|---|---|
| L01-A | Confirmação manual durante a chamada de A era substituída pelo sucesso de A; origem continuava `manual` | Conclusão não comparava a autoridade da tentativa e o manual não coordenava com o lease | Rota manual bloqueia lease ativo sob o lock; lease expirado pode ser assumido, limpa o token e audita a assunção. Sucesso de A com token divergente vai para `resultado_externo` e gera `Aviso`/auditoria | `test_manual_durante_lease_ativo_e_bloqueado`, `test_sucesso_antigo_nao_substitui_manual`, `test_sucesso_antigo_nao_desfaz_sucesso_de_b` |
| L01-B | Erro de A rebaixava nota confirmada manualmente | Caminho de `ErroFiscal` aplicava `status=erro` e limpava `processando_desde` sem verificar o dono | Erro só altera documento mutável se o token ainda for de A; terminal/confirmado preserva status e recebe evidência de erro | `test_erro_antigo_nao_rebaixa_manual_autorizada`, `test_erro_com_token_atual_em_documento_terminal_nao_rebaixa` |
| L01-C | Erro de A desfazia nota cancelada e permitia novo ciclo | Cancelamento não invalidava o claim e o erro não tratava terminalidade | `cancelar_nota_fiscal` limpa `tentativa_atual`/`processando_desde`; retorno antigo vira evidência; retry ordinário de cancelada continua bloqueado | `test_erro_antigo_nao_desfaz_cancelamento`, `test_sucesso_antigo_apos_cancelamento_fica_como_evidencia`, `test_integracao_nao_reemite_nota_cancelada` |
| L01-D | Tentativa A expirada limpava o resultado de B | Token/lease não tinha identidade comparável na conclusão | Token UUID por tentativa; conclusão relê e compara sob lock. A não altera nem libera claim de B, mesmo quando B já autorizou | `test_resultado_antigo_nao_limpa_claim_novo_ativo`, `test_resultado_antigo_nao_desfaz_sucesso_de_b`, `test_l01_erro_antigo_nao_desfaz_sucesso_de_b_postgres` |
| Controle | Dois retries com lease ativo chamavam o provedor uma vez | — | Lease ativo faz retorno sem chamada; token não cria segunda tentativa | `test_retry_nao_chama_provedor_quando_lease_ativo` |

## Política de claim, expiração e resultado

- `tentativa_atual` é UUID gerado na fase curta, sob `Pedido → NotaFiscal`.
- `processando_desde` é lease de 2 minutos. Lease ativo não é tomado por
  retry automático nem por manual. Lease expirado pode ser assumido por uma
  nova tentativa ou pelo manual; o token anterior perde autoridade.
- Sucesso e erro só aplicam transição quando o token relido é o mesmo.
- Documento autorizado/cancelado é terminal para a tentativa antiga. A
  resposta é retida em `resultado_externo`, com número/chave, motivo, token e
  instante, e gera `Aviso` e `fiscal.resultado_externo_obsoleto`. Cada evento
  distinto tem aviso próprio, identificado por tentativa e tipo, para não
  esconder uma nova evidência atrás de um aviso antigo.
- Repetição do mesmo token/tipo é idempotente: não duplica evento, aviso ou
  auditoria.
- Evidência externa conflitante não reabre pedido, não repete estoque/estorno
  e não inventa cancelamento externo.

## Evidência de preservação

- Manual durante lease: HTTP 200 com erro de domínio; Nota continua no claim
  e o sucesso posterior da integração é o único resultado aplicado.
- Manual após expiração: HTTP 302; número/chave/origem manuais permanecem; a
  resposta API-A fica em `resultado_externo["eventos"]` com número e chave.
- Cancelada: status `cancelada`, número/chave manuais preservados; sucesso ou
  erro antigo ficam apenas como evidência.
- Tentativa B: status/número/chave de B preservados; A não limpa token,
  `processando_desde` nem resultado de B.
- Conflito de chave: `IntegrityError` não vira HTTP 500; evidência
  `conflito_chave`, status de erro e aviso.

## Verificação

A consolidação final desta rodada está registrada em
`docs/audit/fase-2c-correcao-validacao.md`. Resumo:

- SQLite local: **649 passed, 22 skipped, 240 subtests**; cobertura total
  **86,38%** (`fiscal/services.py` 93,94%; `fiscal/views.py` 89,84%).
- PostgreSQL: testes marcados em `fiscal/tests/test_concurrency_postgres.py`;
  não há PostgreSQL/Redis neste ambiente, portanto não foram apresentados
  como aprovados localmente.
- Node: `static/js/relatorios.test.mjs` 2/2.
- Gate histórico: `0001 → HEAD` em SQLite descartável, incluindo
  `fiscal/0006`.
- Ruff, `manage.py check`, `makemigrations --check`, Bandit `-ll` e
  `pip-audit` limpos; `check --deploy` com segredos sintéticos sem issues.
- Sem cliente real, SEFAZ/Bling, Neon, dados reais ou reembolso.

### Reauditoria independente no SHA final

No SHA `2a7a300`, a CI `39953967926` passou PostgreSQL 15 + Redis,
check de produção e migração histórica. A reauditoria independente reportou
Gate T aprovado com observações não bloqueantes e preservou os cenários
L01-A/B/C/D. A contagem SQLite local deste documento é histórica da rodada
L01; a validação consolidada está em
`docs/audit/fase-2c-correcao-validacao.md`.

## Gates

| Gate | Situação |
|---|---|
| T — técnico | **Aprovado com observações não bloqueantes** no SHA `2a7a300` |
| C — CI remoto | **Aprovado**: CI `39953967926` success no SHA `2a7a300` |
| H — aceite do cliente | **Pendente**; ficha em `docs/operacao/fase-2c-aceite.md` |

## Riscos remanescentes

- A prova de concorrência final depende de PostgreSQL real; SQLite não
  reproduz row-locks.
- A chamada externa continua podendo superar o lease; por isso a política é
  de evidência tardia, não de promessa de duração máxima.
- A decisão de bloquear o manual durante o lease ativo é deliberada; se a
  operação precisar de tomada manual imediata, deve aguardar o fim do lease
  ou usar o fluxo explícito de expiração/assunção.
- A evidência de resultado externo não substitui a conciliação fiscal humana
  quando o provedor realmente autorizou outro documento.
