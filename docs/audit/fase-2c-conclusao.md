# Conclusão da Fase 2C — Analytics Core + Fiscal Manual

Data: 2026-10-22
Branch: `fase-2c-analytics-fiscal`
Base: `a314a74` (merge da Fase 2B)

> **Atualização pós-auditoria:** os achados A01–A09 foram corrigidos e
> validados localmente. Ver `docs/audit/fase-2c-correcao-rastreabilidade.md`
> e `docs/audit/fase-2c-correcao-validacao.md`. O Gate C (CI remoto
> PostgreSQL 15/Redis) e o Gate H (aceite humano) permanecem pendentes.

## Entregas

| Tarefa | Implementação | Testes |
|---|---|---|
| ANA-01 | Receita por `Pagamento.aprovado_em`; estorno por `estornado_em` | `analytics/tests/test_ana01_receita_por_pagamento.py` |
| ADR-008 | Snapshot de custo, CMV e lucro bruto | `sales/tests/test_adr008_cmv_snapshot.py` |
| ADR-010 | Recorte por vendedor, painel restrito, despesas por responsável | `analytics/tests/test_adr010_recorte_vendedor.py` |
| Painel produto/dia/unidade | `vendas_por_produto`, CSV e gráfico | `analytics/tests/test_relatorio_vendas_produto.py` |
| Comparativo FS/Iaçu | `comparativo_unidades`, gráfico de barras | `analytics/tests/test_comparativo_unidades.py` |
| ADR-007 | Cancelamento 24h, devolução, estorno e ledger | `sales/tests/test_adr007_cancelamento.py` |
| Fiscal expandido | NF-e entrada/saída, CFOP inverso, chave referenciada | `fiscal/tests/test_modelo_fiscal.py` |
| Interestadual | BA→MG 12%, relatório fiscal e CSV | `sales/tests/test_aliquota_interestadual.py`, `fiscal/tests/test_relatorio_fiscal.py` |
| Emissor Fiscal | Grupo, permissões, data migration e relatório | `fiscal/tests/test_perfil_emissor.py` |

## Validação

- Suíte local completa (SQLite): **628 passed, 16 skipped, 240 subtests**.
- Cobertura:
  - `analytics/services.py`: **94,79%**;
  - `sales/services.py`: **84,82%**;
  - `fiscal/services.py`: **90,20%**.
- Gate histórico `0001 → HEAD` validado em SQLite descartável com
  `validar_migracao_legado --criar/--verificar`.
- `ruff check .`: limpo.
- `python manage.py check`: sem issues.
- `python manage.py makemigrations --check --dry-run`: sem mudanças.
- `bandit -r . -ll`: 0 medium/high; apenas achados low pré-existentes.
- `pip-audit -r requirements.txt`: nenhuma vulnerabilidade conhecida.
- **Pendente de CI:** a suíte PostgreSQL 15 + Redis não foi executada neste
  ambiente local. Os testes marcados `postgres` permanecem pulados no SQLite,
  como nas fases anteriores; o workflow de CI já contém o serviço PostgreSQL.
  Foi adicionado um teste PostgreSQL de concorrência entre cancelamento
  padrão e estorno direto para validar a ordem de locks pedido→pagamento.

## Correções da revisão final

- Gate histórico de migração corrigido: fixture da `sales/0001` não envia
  campo que só existe em `0014`; `--criar/--verificar` passou em banco
  descartável.
- Receita, CMV, top produtos, relatório por produto, comparativo e relatório
  fiscal passaram a compartilhar a mesma semântica de eventos: aprovação
  positiva e estorno/devolução negativa na data do evento.
- Cancelamento pago foi removido do endpoint genérico; nova rota
  `/gestao/pedidos/<pk>/cancelar/` expõe os dois caminhos.
- Saída fiscal recebe CFOP 5.102/6.102 quando emitida pelo sistema ou manual;
  devolução exige saída autorizada, chave de 44 dígitos e nota de entrada
  validada por `full_clean()`.
- Emissor é redirecionado para o relatório fiscal após registrar nota, e o
  pós-login/navegação aponta cada papel para uma rota permitida.
- Pedidos legados recebem backfill de `uf_entrega`/`interestadual`; despesas
  podem ser atribuídas a um responsável no formulário.
- Ordem de locks padronizada em pedido→pagamento, com teste PostgreSQL de
  concorrência entre cancelamento padrão e estorno.

## Decisões e limites registrados

- `Pagamento.estornado_em` foi adicionado porque o modelo não tinha timestamp
  de atualização confiável para a data do estorno (ADR-016).
- Itens legados recebem o custo corrente do produto na migração; o CMV
  histórico desses itens é aproximado (ADR-008).
- `NotaFiscal.pedido` passou a `ForeignKey` para permitir NF-e de saída e de
  entrada no mesmo pedido; `Pedido.nota_fiscal` foi mantido como propriedade
  de compatibilidade para a saída (ADR-007).
- A emissão externa da NF-e de entrada continua manual/assistida nesta fase;
  o sistema registra CFOP, chave referenciada, status e auditoria.
- Outras operações interestaduais usam 12% como padrão desta fase; a tabela
  por UF será refinada na integração fiscal.
- Despesas antigas sem `usuario_responsavel` aparecem só na visão global.

## Próximo passo

1. Abrir PR de `fase-2c-analytics-fiscal` para `main`.
2. Rodar o workflow PostgreSQL/Redis e validar a migração histórica
   `a314a74 → HEAD`.
3. Iniciar a Fase 3 (paridade Docker + staging), preservando os contratos de
   ledger, reservas e status financeiro.
