# STO-01 — Ledger de estoque imutável com delta assinado

**Fase:** 2B
**Prioridade:** P0
**Depende de:** Fase 2A (merge `f3e3353`)
**Implementa:** `docs/specs/fase-2b-spec.md` §STO-01

## Contexto observado

`stock.MovimentoEstoque` grava `quantidade` como valor absoluto. O serviço atual
(`stock/services.py::registrar_movimento`) calcula o sinal em memória, atualiza
`Estoque.quantidade` e grava `abs(delta)`. Um ajuste de `-2` fica indistinguível de
`+2` no ledger. `MovimentoEstoque.save()` já bloqueia edição de instância existente,
mas `QuerySet.update()`/`delete()` e SQL direto contornam a proteção.

## Decisão

1. Adicionar `delta` (`DecimalField(12,2)`, não nulo) como fonte de verdade do sinal.
2. Manter `quantidade` como campo derivado (`abs(delta)`), somente leitura na prática:
   `save()` sobrescreve o valor antes de persistir.
3. Estender `MovimentoEstoque.Tipo` com tipos inequívocos:
   - positivos: `entrada`, `transferencia_entrada`, `ajuste_positivo`, `entrada_inicial`;
   - negativos: `saida`, `transferencia_saida`, `ajuste_negativo`, `baixa_definitiva`.
   - `ajuste` e `transferencia` permanecem como tipos legados ambíguos, aceitos apenas
     para leitura/migração.
4. Rejeitar `delta == 0` por `CheckConstraint` e por validação de serviço.
5. Rejeitar incoerência tipo × sinal por validação de serviço e por `CheckConstraint`.
6. `movimento_par` é obrigatório para os tipos `transferencia_entrada` e
   `transferencia_saida` criados pelo serviço público. O vínculo recíproco é feito por
   uma operação interna restrita, que não permite alterar nenhum outro campo.
7. Imutabilidade em camadas:
   - instância: `save()`/`delete()` levantam `ImutabilidadeViolation`;
   - QuerySet: `update()`/`delete()` levantam `ImutabilidadeViolation` (exceto o vínculo
     interno de `movimento_par`);
   - PostgreSQL: trigger `BEFORE UPDATE OR DELETE` na migration; permite apenas o
     vínculo de `movimento_par` e a anonimização de `usuario_id` (SET NULL da LGPD);
   - SQLite: proteção de serviço/QuerySet + testes; trigger não é criada.
8. Migração de dados:
   - movimentos de tipos inequívocos recebem sinal direto;
   - `ajuste` legado tenta recuperar o sinal via `core.LogAuditoria`
     (`estoque.ajuste_manual`, `saldo_novo - saldo_anterior`); sem auditoria, assume
     saída (`-quantidade`) e registra a limitação;
   - ao final, um movimento de reconciliação (`entrada_inicial` ou
     `ajuste_positivo`/`ajuste_negativo`) garante `SUM(delta) == Estoque.quantidade`
     para cada par (produto, unidade). O saldo operacional não é alterado.

## Invariantes

- `Estoque.quantidade == SUM(MovimentoEstoque.delta)` para todo par (produto, unidade),
  após a migration.
- `delta != 0`.
- `delta > 0` para tipos positivos; `delta < 0` para tipos negativos.
- Nenhum movimento existente pode ser alterado ou excluído pela aplicação.

## Alternativas rejeitadas

- **Quantidade absoluta + flag de sinal:** duplica estado e permite combinações
  incoerentes.
- **Event sourcing completo:** muda o modelo de leitura e o escopo da fase.
- **Append-only apenas na aplicação:** não protege contra SQL direto no PostgreSQL.

## Critérios de aceite

- [x] Campo `delta` existe e é não nulo após a migration.
- [x] Ajuste de `-2` grava `delta=-2` e `quantidade=2`.
- [x] `SUM(delta)` reconcilia com `Estoque.quantidade` em todos os estoques migrados.
- [x] `save()`/`delete()` de instância existente e `QuerySet.update()`/`delete()`
      levantam `ImutabilidadeViolation`.
- [x] Trigger PostgreSQL bloqueia UPDATE/DELETE direto (CI).
- [x] Tipos positivos/negativos rejeitam sinal contrário.
- [x] Testes passam em SQLite e PostgreSQL.
- [x] Cobertura de `stock/services.py` ≥ 90% no escopo da fase.
