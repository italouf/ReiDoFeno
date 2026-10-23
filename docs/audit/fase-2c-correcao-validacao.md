# Validação da correção da auditoria — Fase 2C

Data: 2026-10-23
Branch: `fase-2c-analytics-fiscal`
Ambiente local: Windows, Python 3.14.3, Django 5.2.17, SQLite.
PostgreSQL 15/Redis: **não disponíveis neste ambiente**; CI remoto pendente.
A CI `39889483085` passou em `409b9f5`, mas não cobre L02/L03.

## Suíte e cobertura

| Verificação | Resultado |
|---|---|
| Suíte SQLite | **655 passed, 24 skipped, 240 subtests** |
| Cobertura total dos módulos medidos | **86,39%** |
| `analytics/services.py` | **95,24%** |
| `analytics/models.py` | **97,67%** |
| `sales/services.py` | **84,91%** |
| `fiscal/services.py` | **93,50%** |
| `fiscal/views.py` | **89,84%** |
| `ruff check .` | limpo |
| `manage.py check` | sem issues |
| `manage.py makemigrations --check --dry-run` | no changes |
| `manage.py check --deploy` com segredos sintéticos | sem issues |
| Bandit `-ll` | 0 medium/high |
| `pip-audit -r requirements.txt` | 0 vulnerabilidades conhecidas |
| Gate histórico `0001 → HEAD` | aprovado em SQLite descartável, incluindo `fiscal/0006` e `analytics/0004` |

Os 24 skips são os testes marcados `postgres`/Redis já conhecidos e os testes
que exigem backend real. Não foram apresentados como aprovados.

## Fechamento N01–N03

- N01: teste R01 passou a usar `setUp` de `TransactionTestCase`, threads
  iniciadas uma única vez, login/erros no `try` e eventos liberados em falha.
- N02: população financeira separada da população de CMV; teste com checkout
  público, baixa física e pagamento inconclusivo preserva CMV 160, receita 0 e
  frete 0, com valor em conciliação.
- N03: integração fiscal em duas fases com claim/lease; autorização tardia
  gera aviso/auditoria; nota cancelada não é reautorizada; retry concorrente
  não chama o provedor.

## Correção L01 — autoridade da tentativa

- `NotaFiscal.tentativa_atual` recebe UUID na fase curta; sucesso/erro relê e
  compara o token sob lock antes de alterar documento, número, chave, origem
  ou lease.
- Manual durante lease ativo retorna erro tratável; após expiração, assume o
  claim, limpa o token antigo e registra `fiscal.tentativa_manual_assumida`.
- Erro/sucesso de tentativa antiga não rebaixa autorizada, não desfaz
  cancelada e não limpa resultado/claim de tentativa mais nova.
- Respostas tardias/conflitantes ficam em
  `NotaFiscal.resultado_externo["eventos"]`, com `Aviso` e auditoria
  `fiscal.resultado_externo_obsoleto`; repetição do mesmo token/tipo é
  idempotente.
- `fiscal/0006_tentativa_emissao.py` adiciona os campos de forma aditiva.
- Testes SQLite: 13 cenários em `L01AutoridadeTentativaTests`; PostgreSQL:
  quatro interleavings marcados em `FiscalConcurrencyTests`.
- Contrato e matriz: `docs/specs/fase-2c/l01-autoridade-tentativa.md` e
  `docs/audit/fase-2c-reauditoria-l01.md`.

## Correção L02/L03 — avisos e identidade de eventos

- **L02:** `Aviso.evento_chave` separa aviso agregado (`""`) de aviso por
  evento (chave única). `Aviso.registrar()` busca somente agregados e não
  lança `MultipleObjectsReturned` quando há vários avisos da nota.
- **L02:** migração `analytics/0004_aviso_evento_chave.py` preserva avisos
  antigos, atribuindo `legado:<pk>` aos avisos por evento do SHA anterior, e
  cria constraint condicional de unicidade.
- **L03:** a chave estável
  `fiscal.resultado_externo:<nota>:<tentativa>:<tipo>` é verificada antes de
  criar evento; a projeção JSON continua limitada a 20, mas a memória de
  deduplicação é durável.
- **L03:** eventos legados ainda no JSON ou apenas em `LogAuditoria` são
  reconhecidos para não duplicar efeitos; o histórico completo não é
  reescrito nem apagado.
- Testes: 6 cenários SQLite em `L02L03AvisosEventosTests`; 2 testes
  PostgreSQL marcados (retry A/B/C e replay concorrente).
- Contrato: `docs/specs/fase-2c/l02-l03-avisos-eventos.md`;
  rastreabilidade: `docs/audit/fase-2c-reauditoria-l02-l03.md`.

## Reauditoria R01-R05

- R01: lock `Pedido → NotaFiscal`, releitura e revalidação; teste PG
  concorrente marcado, teste sequencial SQLite.
- R02: constraint condicional de chave, preflight de legado e tratamento de
  `IntegrityError`; teste PG concorrente marcado.
- R03: formatos canônicos ancorados; motivo ambíguo não atribui pedido.
- R04: exclusão compartilhada de pagamento cancelado sem estorno;
  `receita_em_conciliacao` separada.
- R05: Node test `static/js/relatorios.test.mjs` 2/2 e browser emulado DPR 2
  com quatro resizes, CSS 240 px/backing 480 px estáveis.

## Cenários adicionais A01–A07

Executados em `sales/tests/test_auditoria_fase2c.py` e
`fiscal/tests/test_auditoria_fase2c.py`:

- `test_chargeback_deve_manter_lucro_coerente_entre_paineis` — 0/60/-60 nos
  dois painéis.
- `test_chargeback_nao_deve_apagar_cmv_de_janeiro` — janeiro mantém 100/60/40.
- `test_devolucao_manual_apos_chargeback_deve_ser_possivel` — uma entrada,
  um movimento e um estorno.
- `test_cancelamento_legado_sem_evidencia_nao_deve_inflar_estoque` — saldo
  10→10 e aviso.
- `test_evidencia_parcial_devolve_somente_quantidade_comprovada` — 10→11.
- `test_emissor_deve_conseguir_registrar_documento_de_entrada` — entrada
  autorizada sem novo efeito.
- `test_csv_fiscal_com_dados_deve_funcionar` — HTTP 200 com linha real.
- `test_cfop_de_nota_autorizada_nao_deve_ser_reescrito_silenciosamente`.
- `test_saneamento_autorizado_de_cfop_legado_e_auditado`.
- `test_movimento_legado_sem_obrigacao_e_reconhecido` — movimento antigo
  sem FK é mapeado pelo número do pedido; não duplica crédito.
- `test_evidencia_zero_nao_credita` e
  `test_devolucao_reconcilia_evidencia_parcial_em_segunda_chamada`.
- `test_oracle_janeiro_fevereiro_marco_por_fluxos_publicos` — 100/60/40,
  -100/0/-100, 0/-60/60.
- `test_entrada_nao_pode_reutilizar_chave_da_saida`,
  `test_entrada_nao_pode_duplicar_chave_de_outra_nota`,
  `test_entrada_cancelada_nao_e_reautorizada`,
  `test_saida_cancelada_nao_e_reautorizada`,
  `test_cfop_sem_mapeamento_e_rejeitado`.
- `test_csv_fiscal_sanitiza_formula_e_exporta_estorno`.
- `test_graficos_nao_dependem_de_cdn_nem_script_inline`.
- `test_push_da_fase_2c_dispara_ci`.

## Evidência de navegador

Playwright, servidor local com CSP padrão e `DEBUG=True` do settings de
desenvolvimento:

- `/gestao/relatorios/comparativo-unidades/`: canvas pintado, tabela
  FS `100/60/40` e Iaçu `100/40/60`; colunas separadas de receita financeira,
  receita de produtos e frete; `canvas.style.width` acompanha o container
  (1008 px em viewport de 1024 px), scripts apenas
  `static/js/relatorios.js` e `static/js/app.js`; zero erros de console/CSP.
  Screenshot: `docs/audit/fase-2c-comparativo-csp.png`.
- DPI: browser emulado com `devicePixelRatio=2` e quatro resizes manteve
  CSS 240 px, backing 480 px e `data-logical-height=240`; o teste Node repete
  a estabilidade sem acumular escala. Não houve dispositivo físico.
- Login como Emissor Fiscal: `/fiscal/notas-entrada/` listou a pendência;
  o formulário registrou número 77001/chave/ link, e a lista passou a
  “Autorizada”; nenhuma ação de estoque/pagamento foi repetida.
  Screenshot: `docs/audit/fase-2c-nota-entrada.png`.

O único erro de console no login foi `favicon.ico` 404, sem relação com CSP.

## Pendências e limites

- CI remoto (PostgreSQL 15 + Redis) não executado: o prompt não autoriza push
  e não há PostgreSQL/Redis locais. `workflow_dispatch`/PR devem ser usados
  após autorização.
- Aceite do cliente não realizado; roteiro em
  `docs/operacao/fase-2c-aceite.md`.
- Emissão/cancelamento fiscal real, reembolso real e SEFAZ não executados.
- Custo legado continua aproximado pelo custo corrente.
- `NotaFiscal` de entrada é registro manual; não é autorização externa
  inventada pelo sistema.
- A validação visual usou dados sintéticos, não base real.
- Movimentos legados de devolução sem número de pedido no motivo não são
  inventados: ficam para conciliação e bloqueiam novo crédito até atribuição.
- A proteção de chave única de NF-e é de aplicação/validação, não uma
  constraint SQL adicional sobre dados históricos; uma constraint exigiria
  saneamento prévio de duplicidades legadas.
