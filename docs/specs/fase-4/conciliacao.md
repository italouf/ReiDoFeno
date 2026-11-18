# CONCILIAÇÃO — Validação financeira manual

**Fase:** 4
**Depende de:** PAY-MANUAL, ADR-002, ADR-016, ADR-017, ADR-018.

## Objetivo

Permitir que os responsáveis financeiros (Nilton, Neto, Caio) validem os
recebimentos manuais antes de o pedido avançar na operação.

## Acesso

- Grupo novo `Financeiro` (criado por `seed_groups`) e `Administrador`.
- Vendedor não acessa a fila nem executa ações (403).
- Ninguém concilia pedido do qual é `usuario_criador` (403), inclusive
  administradores.

## Fila

`/gestao/conciliacao/` lista pedidos com:

- `status_financeiro=pago`;
- `financeiro_conciliado=False`;
- `status != cancelado`.

Cada linha mostra cliente, total, comprovantes (método, valor, data,
referência, arquivo) e as ações.

## Conciliar

`POST /gestao/conciliacao/<pk>/conciliar/`

1. Trava o pedido com `select_for_update`.
2. Exige `status_financeiro=pago` e soma de comprovantes não rejeitados
   maior ou igual ao total.
3. Marca `financeiro_conciliado=True`.
4. Marca comprovantes `pendente` como `conciliado`.
5. Grava `LogAuditoria` `pedido_conciliado` com usuário, antes/depois e IDs
   dos comprovantes.

## Rejeitar

`POST /gestao/conciliacao/<pk>/rejeitar/` com `justificativa`.

1. Exige justificativa não vazia (400 caso contrário).
2. Trava o pedido e exige que ainda não esteja conciliado.
3. Marca comprovantes como `rejeitado` (não os apaga).
4. Reverte `status_financeiro` para `pendente` e mantém
   `financeiro_conciliado=False`.
5. Cancela o `Pagamento` manual limpando `aprovado_em` e `estornado_em`,
   removendo a receita provisória. Não há estorno porque a prova nunca foi
   confirmada; o evento fica na auditoria.
6. Libera reservas ainda ativas; **não** devolve estoque já baixado, pois
   rejeição financeira não é retorno físico (ADR-017).
7. Grava `LogAuditoria` `pedido_rejeitado_conciliacao`.

## Novo pagamento após rejeição

Comprovantes rejeitados permanecem no histórico, mas `Pedido.saldo_devedor`
ignora esses registros. O vendedor pode registrar novas provas até fechar o
saldo novamente.
