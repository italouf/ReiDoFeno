# ADR-010 — Recorte de acesso e métricas por vendedor

## Contexto

O painel global mostrava receita, despesas, avisos e clientes de toda a
operação para qualquer perfil interno. A decisão de negócio é que o vendedor
veja apenas o próprio desempenho; Administrador e Gestor continuam com a visão
global. O mesmo recorte vale para despesas e clientes elegíveis a recompra.

## Decisão

1. `/gestao/minhas-metricas/` usa `vendedor=request.user` e agrega somente
   pedidos em que `Pedido.usuario_criador` é o usuário autenticado.
2. `/painel/painel/` exige Administrador ou Gestor e agrega `vendedor=None`
   (global).
3. Vendedor autenticado recebe 403 no painel global.
4. Despesas ganham `usuario_responsavel`. Métricas de vendedor somam apenas
   despesas com esse responsável; a visão global soma todas.
5. `clientes_para_recompra(dias, vendedor=...)` filtra os pedidos pelo
   vendedor em todas as subconsultas, não apenas no resultado final.
6. Superusuário continua passando nos mixins, como já ocorre no sistema.

## Consequências

- O vendedor não vê mais dados de terceiros no painel de métricas.
- O painel global deixa de ser uma rota de vendedor; a navegação deve apontar
  o vendedor para "Minhas métricas".
- Despesas antigas sem responsável não entram na métrica individual; entram na
  global. Isso é intencional e evita atribuição inventada.
- O recorte é aplicado no servidor, não apenas no template.
