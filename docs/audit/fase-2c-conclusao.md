# Conclusão da Fase 2C — Analytics Core + Fiscal Manual

Data: 2026-10-22
Branch: `fase-2c-analytics-fiscal`
Base: `a314a74` (merge da Fase 2B)

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

- Suíte local completa (SQLite): **575 passed, 15 skipped, 240 subtests**.
- Cobertura:
  - `analytics/services.py`: **97,87%**;
  - `sales/services.py`: **85,02%**.
- `ruff check .`: limpo.
- `python manage.py check`: sem issues.
- `python manage.py makemigrations --check --dry-run`: sem mudanças.
- `bandit -r . -ll`: 0 medium/high; apenas achados low pré-existentes.
- `pip-audit -r requirements.txt`: nenhuma vulnerabilidade conhecida.
- **Pendente de CI:** a suíte PostgreSQL 15 + Redis não foi executada neste
  ambiente local. Os testes marcados `postgres` permanecem pulados no SQLite,
  como nas fases anteriores; o workflow de CI já contém o serviço PostgreSQL.

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
