# Plano de execução — Fase 2C

Branch: `fase-2c-analytics-fiscal`
Base: `a314a74` (merge da Fase 2B)

## Tarefas

1. ANA-01 — receita reconhecida por pagamento aprovado; estorno por evento.
2. ADR-008 — CMV por item e snapshot imutável de custo.
3. ADR-010 — recorte de métricas, clientes e despesas por vendedor.
4. Relatório de vendas por produto/dia/unidade com CSV e gráfico.
5. Comparativo FS/Iaçu com receita, CMV, lucro, pedidos e ticket médio.
6. ADR-007 — cancelamento padrão em 24h e devolução fiscal.
7. Modelo fiscal expandido: NF-e entrada/saída, CFOP inverso e chave
   referenciada.
8. Alíquota interestadual BA→MG 12% e relatório fiscal.
9. Perfil Emissor Fiscal com permissões restritas.

## Restrições globais

- Não quebrar o ledger imutável, reservas vinculadas, status financeiro
  separado, CNPJ alfanumérico e titularidade LGPD das fases anteriores.
- Migrações aditivas e compatíveis com SQLite/PostgreSQL.
- Testes primeiro; suíte completa antes de cada commit.
- Commits atômicos por tarefa.
- Documentar specs em `docs/specs/fase-2c/` e ADRs em `docs/adrs/`.

## Referências

- `rfenodocs/docs/data-model.md`
- `rfenodocs/docs/technical-audit.md` (ANA-01, FIS-01/02, ADR-007, ADR-008,
  ADR-010)
- `docs/specs/fase-2b-spec.md`
- `docs/adrs/ADR-002-status-financeiro.md`
- `docs/adrs/ADR-013-ledger-imutavel.md`
- `docs/adrs/ADR-015-obrigacao-estoque.md`
