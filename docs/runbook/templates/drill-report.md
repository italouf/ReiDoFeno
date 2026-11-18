# Relatório de DRILL — Data: ____/____/________

## Identificação
- **Executor:** __________________________
- **Data/hora início:** ____/____/____ ____:____
- **Data/hora fim:** ____/____/____ ____:____
- **SHA-256 do dump usado:** __________________________
- **Origem do dump:** ☐ Backup local ☐ Backup offsite (R2/B2)

## Ambiente de restore
- **Tipo:** ☐ VPS nova ☐ Container descartável ☐ Outro: ______
- **Local:** __________________________

## Etapas executadas
- [ ] Dump baixado e validado (checksum SHA-256 OK + `pg_restore --list`)
- [ ] Mídia baixada e restaurada
- [ ] Config descriptografada com chave privada `age`
- [ ] PostgreSQL restaurado sem erros (`infra/backup/restore.sh`)
- [ ] `docker compose up` executou sem erro
- [ ] `/healthz/` retornou 200 (`status=ok`, `database=ok`, `cache=ok`)
- [ ] `python manage.py validar_restore` retornou `RESTORE_VALIDADO_OK`

## Validação de consistência
- Pedidos: ______ registros (esperado: ~______)
- Clientes: ______ registros (esperado: ~______)
- Movimentos (`MovimentoEstoque`): ______ registros (esperado: ~______)
- Notas fiscais (`NotaFiscal`): ______ registros (esperado: ~______)
- Ledger reconciliado (`SUM(delta) == saldo`): ☐ Sim ☐ Não (detalhar: ______)
- Reservas reconciliadas (`SUM(ativas) == bloqueada`): ☐ Sim ☐ Não
- Snapshot CMV (`custo_unitario` não nulo): ☐ Sim ☐ Não

## Métricas
- **RTO alcançado:** ______ minutos (meta: ≤ 60 min)
- **RPO alcançado:** ______ horas (meta: ≤ 24 h)

## Incidentes encontrados
(Listar qualquer problema e resolução)

## Conclusão
- [ ] DRILL bem-sucedido
- [ ] DRILL parcial (detalhar pendências)
- [ ] DRILL falhou (motivo: ______)

## Assinatura
__________________________________
Executor
