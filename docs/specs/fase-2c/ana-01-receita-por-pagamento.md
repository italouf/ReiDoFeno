# ANA-01 — Receita reconhecida por pagamento

## Contexto

O painel reconhecia receita por `Pedido.status_financeiro == pago` e filtrava
por `Pedido.criado_em`. Isso antecipava receita antes do recebimento, ignorava
pedidos pagos que ainda estavam em separação e não representava estornos na
data do evento.

## Decisão

1. A receita é reconhecida pelo evento `Pagamento.aprovado_em` (pagamento com
   status aprovado).
2. A data de competência é a data de `aprovado_em`, não a criação do pedido.
3. Estornos são eventos negativos na data `Pagamento.estornado_em`.
4. `Pedido.status` não participa do cálculo financeiro. `status_financeiro`
   participa apenas como salvaguarda: pedidos cancelados antes de qualquer
   aprovação não geram receita.
5. Pagamento sem `aprovado_em` ou pedido concluído sem pagamento aprovado não
   geram receita.
6. A conciliação do período é:

   ```text
   receita = SUM(pagamentos aprovados no período)
           - SUM(estornos ocorridos no período)
   ```

   Ao longo de toda a série, o resultado é igual à soma dos pagamentos que
   permanecem aprovados, desde que todo estorno seja registrado com
   `estornado_em`.

## Implementação

- `Pagamento.estornado_em` (nullable) registra a data do estorno/chargeback.
- `analytics.services.receita_do_periodo(inicio, fim)` implementa a regra.
- `analytics.services.metricas_do_periodo` aceita `vendedor` e expõe
  `receita`, `num_pedidos`, `cmv_total`, `lucro_bruto` além dos campos legados.
- `sales.services.estornar_pagamento` registra o estorno sob lock e mantém o
  pedido coerente.

## Critérios de aceite

- [ ] Pedido com pagamento aprovado gera receita.
- [ ] Pedido estornado não gera receita líquida.
- [ ] Pedido em separação com financeiro pago gera receita.
- [ ] Pedido concluído sem pagamento não gera receita.
- [ ] Estorno reduz a receita no dia do estorno.
- [ ] Testes passam em SQLite e PostgreSQL.

## Riscos

- Dados legados sem `aprovado_em` precisam de conciliação manual; a migração
  não inventa datas.
- A receita histórica permanece no período original após um estorno, com o
  negativo no período do evento. É o comportamento contábil esperado.
