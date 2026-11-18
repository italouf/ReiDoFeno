# DRILL — Restauração validada e evidência de RTO/RPO

**Fase:** 5
**Status:** Em implementação
**Depende de:** `docs/specs/fase-5/backup-offsite.md`, ADR-019.

## Objetivo

Garantir procedimento reproduzível e automatizado de restauração completa em
ambiente limpo (`infra/backup/restore.sh`), validação automática de
consistência pós-restore (`validar_restore`) e template de evidência de DRILL
(`docs/runbook/templates/drill-report.md`), visando **RTO ≤ 60 min** e
**RPO ≤ 24 h**.

## Garantias validadas no restore

1. **STO-01:** `SUM(MovimentoEstoque.delta) == Estoque.quantidade` em todas as
   combinações `(produto, unidade)`.
2. **ADR-003:** `SUM(ReservaEstoque.quantidade WHERE status='ativa') ==
   Estoque.quantidade_bloqueada`.
3. **ADR-008:** nenhum `ItemPedido` possui `custo_unitario` nulo.
4. **CUS-01 / ADR-006 / ADR-012:** documentos alfanuméricos, `NotaFiscal` e
   mídias/PDFs permanecem íntegros e contáveis.

## Especificação

1. **`infra/backup/restore.sh`:**
   - Recebe `--dump <file> --media <file> --target <dir>` e opcionalmente
     `--config <file.age> --config-key <key>`.
   - Valida existência dos arquivos de entrada e integridade do dump com
     `pg_restore --list`.
   - Restaura mídia para `<target>` e, quando fornecidos, descriptografa
     `config.tar.gz.age` com `age --decrypt` removendo o tarball temporário.
   - Sobe container temporário `postgres:15-alpine`, aplica `pg_restore
     --no-owner --no-acl`, executa contagens de `sales_pedido`,
     `customers_cliente`, `stock_movimentoestoque` e `fiscal_notafiscal` e
     encerra o container temporário via `trap`.
2. **`python manage.py validar_restore`:**
   - Executa as verificações de ledger, reservas ativas, snapshot de custo e
     contagens de tabelas críticas; retorna erro (`CommandError`) se houver
     inconsistência.
3. **`docs/runbook/templates/drill-report.md`:**
   - Formulário padrão para registrar data/hora, SHA do dump, origem,
     contagens, reconciliação, RTO/RPO e assinatura do executor.

## Limite de ambiente local

Neste ambiente Windows não há Docker Engine nem PostgreSQL instalado; o script
`restore.sh` é validado por sintaxe (`bash -n`) e execução em sandbox com
binários simulados, e a consistência ORM é validada por suíte Django. A
execução real do DRILL em VPS/container descartável permanece registrada como
pendência operacional antes do go-live.
