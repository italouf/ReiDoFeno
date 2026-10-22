# ADR-010 — Recorte de métricas por vendedor

## Escopo

Aplicar autorização por objeto nas métricas do vendedor, restringir o painel
global a Administrador/Gestor e impedir vazamento de clientes e despesas de
terceiros.

## Regras

- `vendedor=<Usuario>`: filtra pagamentos por `pedido__usuario_criador`.
- `vendedor=None`: visão global (Admin/Gestor).
- Despesas: `usuario_responsavel`.
- Recompra: pedidos do vendedor, inclusive na anotação de última compra.
- `MinhasMetricasView`: contexto expõe `receita`, `num_pedidos`, `cmv_total`,
  `lucro_bruto`, `despesas_total` e os campos legados do template.
- `PainelView`: `grupos_permitidos = ("Administrador", "Gestor")`.

## Testes

- vendedor vê somente a própria receita e contagem;
- admin vê a soma global;
- vendedor recebe 403 no painel;
- recompra não retorna cliente de outro vendedor;
- despesa de outro responsável não entra na métrica individual.

## Critérios de aceite

- [ ] Recorte no servidor em todas as consultas.
- [ ] Painel global restrito.
- [ ] Contexto de minhas métricas com receita/contagem.
- [ ] Clientes e despesas isolados.
- [ ] ADR-010 publicada.
