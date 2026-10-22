# Perfil Emissor Fiscal

## Objetivo

Permitir que o operador fiscal (Caio) registre/edite notas e exporte o
relatório fiscal sem ganhar acesso à edição de pedidos, clientes, produtos
ou estoque.

## Grupo

`Emissor Fiscal` é criado por data migration e também declarado em
`accounts.permissions` para o comando idempotente `seed_groups`.

Permissões:

- `fiscal.view_notafiscal`
- `fiscal.add_notafiscal`
- `fiscal.change_notafiscal`
- `sales.view_pedido`

Sem permissões de alteração em `sales`, `catalog`, `customers`, `stock` ou
`core`. A autorização das views continua por grupo, como no restante do
sistema.

## Rotas

- `/fiscal/pedidos/<pk>/nota-manual/` — Administrador, Gestor e Emissor
  Fiscal.
- `/fiscal/relatorios/` — Administrador, Gestor e Emissor Fiscal, com link
  para a nota manual de cada pedido.
- `/gestao/pedidos/<pk>/status/` — apenas grupos internos; Emissor recebe
  403.
- `/painel/painel/` — apenas Administrador/Gestor.
- O pós-login redireciona cada papel para uma rota permitida: gestão → painel,
  Emissor → relatório fiscal, Vendedor → minhas métricas.

## Data migration

Cria o grupo e, se existir um usuário `Caio` (case-insensitive), adiciona-o
ao grupo. A atribuição de permissões é feita por `seed_groups`, que é a fonte
única da matriz.

## Testes

- emissor acessa o formulário de nota manual;
- emissor não acessa a alteração de status de pedido/painel;
- emissor exporta o relatório fiscal;
- grupo tem as permissões declaradas e nenhuma permissão de alteração em
  pedidos/produtos/clientes/estoque.

## Critérios de aceite

- [ ] Grupo criado e idempotente.
- [ ] Permissões corretas.
- [ ] Data migration atribui Caio quando existir.
- [ ] Fluxos fiscais funcionam.
- [ ] Acessos indevidos retornam 403.
