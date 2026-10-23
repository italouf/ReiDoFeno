# Reauditoria L02/L03 — avisos e deduplicação durável

Data: 2026-10-23
Branch: `fase-2c-analytics-fiscal`
SHA inicial auditado: `409b9f58e7dfd7ceec09eee7127c71b8f5f65e2e`
Base remota de L01: `39889483085` (success no SHA inicial)

## Matriz L02/L03

| ID | Causa reproduzida | Contrato | Correção | Teste | Resultado |
|---|---|---|---|---|---|
| L02 | Avisos por evento e aviso comum compartilhavam a mesma identidade lógica; `Aviso.registrar()` usava `get_or_create` por tipo/objeto/lido=False e lançava `MultipleObjectsReturned` no retry C | Aviso agregado e avisos por evento têm identidades distintas; erro comum encerra a tentativa e libera o claim mesmo com vários avisos | `Aviso.evento_chave`: vazio para agregado, único para evento. `Aviso.registrar()` filtra agregados. Migração preserva eventos antigos | `test_erro_de_c_apos_avisos_de_b_e_a_nao_quebra_retry`; `test_l02_retry_c_apos_avisos_b_e_a_postgres` | SQLite 1/1; PG marcado |
| L02 legado | Avisos por evento antigos tinham chave vazia | Dados do SHA anterior continuam utilizáveis sem apagar avisos | Backfill `legado:<pk>` na `analytics/0004` | Evidência de migração em banco descartável | `legado:1`, `legado:2`; dois avisos preservados |
| L03 | Deduplicação procurava token/tipo apenas em `resultado_externo["eventos"][-20:]` | Identidade sobrevive à rotação, releitura e nova transação | Chave durável por evento no próprio aviso; verificação antes da projeção | `test_evento_repetido_apos_rotacao_de_20_nao_duplica` | 21 eventos/auditorias, JSON com 20 |
| L03 legado | Evento antigo podia existir só em `LogAuditoria` | Não duplicar replay de evento legado | Fallback por `depois.tentativa`/`depois.tipo`; JSON também é consultado | `test_evento_legado_apenas_em_auditoria_nao_duplica` | Nenhum novo evento/aviso/auditoria |
| L03 concorrente | Dois replays poderiam criar dois eventos | Um evento lógico e um conjunto de efeitos | Lock da Nota + chave única condicional | `test_l03_replay_concorrente_do_mesmo_evento_postgres` | Aprovado na reauditoria independente/CI |
| Conflito de chave | Aviso comum após evento podia quebrar o tratamento de `IntegrityError` | Conflito continua domínio tratado, sem HTTP 500 | Fluxo usa `Aviso.registrar()` agregado e preserva evidência `conflito_chave` | `test_conflito_de_chave_com_avisos_previos_nao_quebra` | status erro, claim liberado, evidência retida |

## RED antes da correção

Execução de `L02L03AvisosEventosTests` contra `409b9f5`:

- L02: `analytics.models.Aviso.MultipleObjectsReturned: get() returned more than one Aviso -- it returned 2!` no retry C; a transação reverteu status/claim.
- L03: após E + 20 eventos + E, `22 != 21` auditorias.
- Resultado: **2 failed**.

## GREEN depois da correção

- L02: retry C não lança; `status=erro`, `tentativa_atual=None`, `processando_desde=None`; B agregado e A por evento preservados.
- L03: 21 eventos lógicos, 21 avisos por evento e 21 auditorias; JSON mantém os 20 mais recentes.
- Avisos antigos com chave vazia/legada não participam do agregado; nenhum aviso é apagado.
- Testes focados: 6 cenários SQLite de L02/L03 (incluindo legado e conflito)
  passaram.

## Estratégia de identidade e compatibilidade

- Identidade de evento:
  `fiscal.resultado_externo:<nota_id>:<uuid_da_tentativa>:<tipo>`.
- O registro é feito sob `select_for_update()` da Nota, na mesma transação da
  evidência e da auditoria.
- A constraint `aviso_evento_chave_unica` impede duplicação concorrente da
  chave.
- `resultado_externo["eventos"]` é projeção, não autoridade de deduplicação.
- Eventos antigos ainda na projeção são reconhecidos; eventos que restaram
  apenas em `LogAuditoria` são reconhecidos pelo JSON de auditoria.
- Nenhum `LogAuditoria` é editado ou apagado.

## Migração

`analytics/0004_aviso_evento_chave.py`:

1. adiciona `evento_chave`, default vazio;
2. converte avisos fiscais por evento antigos para `legado:<pk>`;
3. cria a constraint condicional de unicidade.

O gate histórico `0001 → HEAD` aplicou a migração e o comando
`validar_migracao_legado --verificar` passou em SQLite descartável. A CI
`39953967926` aprovou PostgreSQL 15 + Redis e a migração histórica no SHA
`2a7a300`; a reauditoria independente repetiu o gate em PostgreSQL 16.2.

## Verificação local

| Verificação | Resultado |
|---|---|
| Suíte SQLite | 655 passed, 24 skipped, 240 subtests |
| Cobertura total | 86,39% |
| `fiscal/services.py` | 93,50% |
| `analytics/models.py` | 97,67% |
| Node R05 | 2/2 |
| Ruff/check/makemigrations | limpos |
| `check --deploy` | sem issues |
| Gate histórico | aprovado em SQLite |
| PostgreSQL local | indisponível; 8 testes fiscais marcados |

## Gates

| Gate | Situação |
|---|---|
| T — técnico | **Aprovado com observações não bloqueantes** pela reauditoria independente no SHA `2a7a300` |
| C — remoto | **Aprovado**: CI `39953967926` success, incluindo PostgreSQL 15 + Redis, check de produção e migração histórica |
| H — humano | **Pendente**: roteiro `docs/operacao/fase-2c-aceite.md` e ficha não executados pelo cliente |

## Evidência independente posterior

A reauditoria independente registrou, para `2a7a300`:

- SQLite 655 passed, 24 skipped, 240 subtests; cobertura 86,39%;
- PostgreSQL 16.2 678 passed, 1 skipped (Redis), 240 subtests; cobertura
  86,41%;
- 11 testes adversariais ampliados aprovados, incluindo L02/L03;
- backfill sintético independente com cinco avisos preservados;
- gate histórico PostgreSQL com nove cenários legados aprovado;
- CI `39953967926` aprovada no SHA, com PostgreSQL 15 + Redis.

A execução PostgreSQL 16.2 é evidência da reauditoria externa, não deste
ambiente local. O warning de conexão remanescente no teardown e as
depreciações `URLField` são observações não bloqueantes registradas em
`docs/operacao/fase-2c-backlog.md`.

## Limites

- O cliente fiscal continua simulado; nenhuma SEFAZ/Bling real foi chamada.
- O teste concorrente PostgreSQL foi aprovado na reauditoria independente e a
  CI PostgreSQL 15 + Redis passou; ele não foi executado neste ambiente local
  sem PostgreSQL/Redis.
- A compatibilidade de migração foi exercitada com avisos sintéticos no schema
  0003 e o gate histórico passou em SQLite e PostgreSQL; a base real ainda
  precisa de backup/preflight conforme governança.
- Não foi criada tela nova de conciliação; os eventos permanecem visíveis na
  central de avisos e na auditoria.
