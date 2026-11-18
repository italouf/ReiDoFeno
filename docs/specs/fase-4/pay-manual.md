# PAY-MANUAL — Registro manual de pagamento

**Fase:** 4
**Status:** Aprovado (adaptação do prompt original)
**Depende de:** ADR-002 (status financeiro separado), ADR-015 (obrigação de
estoque), ADR-016 (receita por pagamento), ADR-017 (eventos separados),
ADR-018 (pagamento manual).

## Objetivo

Permitir que o vendedor registre pagamento manual (PIX, dinheiro, cartão de
crédito ou débito), com comprovante e trilha de auditoria, para pedidos em
`status_financeiro=pendente`, sem gateway online.

## Modelo `ComprovantePagamento`

| Campo | Regra |
|---|---|
| `pedido` | FK `sales.Pedido`, `CASCADE`, `related_name="comprovantes"` |
| `metodo` | `pix`, `dinheiro`, `cartao_credito`, `cartao_debito` |
| `valor` | `Decimal(12,2)`, `> 0` e `< 10.000.000.000,00` |
| `data_pagamento` | `DateTimeField` |
| `referencia` | até 100 caracteres; obrigatória para PIX |
| `observacao` | texto livre |
| `arquivo` | JPG/PNG/PDF, até 5 MB, opcional |
| `status` | `pendente`, `conciliado`, `rejeitado` |
| `registrado_por` | FK `accounts.Usuario`, `PROTECT` |
| `registrado_em` | `auto_now_add` |

Constraint de banco: `valor > 0` e `valor < 10000000000.00`.

## Regras de negócio

1. Só é permitido registrar em pedido com `status_financeiro=pendente` e
   `status != cancelado`.
2. O valor não pode exceder o saldo devedor (`total - comprovantes ativos`).
3. Pagamento parcial mantém `status_financeiro=pendente`.
4. Quando a soma dos comprovantes ativos cobre o total:
   - `status_financeiro` passa a `pago` via `Pedido.definir_status_financeiro`;
   - `financeiro_conciliado` permanece `False`;
   - `Pagamento` do pedido é criado/atualizado como `provedor="manual"`,
     `status=aprovado`, `valor=total`, `aprovado_em` = data do último
     comprovante que fechou o saldo;
   - estoque é baixado pelo fluxo existente (`_baixar_estoque_do_pedido`),
     que consome reservas e trata obrigações/pendências.
5. O andamento operacional (`status`) não avança automaticamente: a transição
   para separação continua exigindo `financeiro_conciliado=True` (ADR-002).
6. Toda operação grava `LogAuditoria` com ação
   `pagamento_manual_registrado`, incluindo método, valor, saldo e status.
7. Comprovantes rejeitados na conciliação não contam para o saldo devedor.
8. A data do pagamento não pode estar no futuro nem ser anterior a um ano.
9. Referência PIX é obrigatória e única entre comprovantes PIX.
10. Upload exige extensão, MIME e assinatura binária compatíveis
    (JPEG/PNG/PDF), além do limite de 5 MB.
11. Enquanto houver comprovante ativo, o checkout online do pedido fica
    bloqueado para evitar pagamento duplicado. Aprovação do provedor em
    pedido com prova manual não auto-concilia: exige revisão financeira.
12. Em rejeição, a receita provisória é removida (`aprovado_em=None`) sem
    criar estorno sem contrapartida; o evento fica na auditoria.

## CSV de comprovantes? Não.

O comprovante é evidência operacional; exportações fiscais usam a nota e os
dados do pedido (Task 3). Não há exportação própria de comprovantes neste MVP.

## Fora de escopo

- Gateway online, conciliação bancária automática, estorno automático de
  estoque por rejeição financeira.
