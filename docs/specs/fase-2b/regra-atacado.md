# Regra de preço atacado (> 50 fardos)

**Fase:** 2B
**Prioridade:** P1
**Depende de:** catálogo e checkout existentes
**Origem:** Documento de Operação §3.2 + decisão de reunião (limiar de 50 fardos)

## Regra

Um item usa `Produto.preco_atacado` quando **todas** as condições são verdadeiras:

1. `Cliente.categoria == ATACADO`;
2. o pedido é do titular com vínculo comprovado (`identidade_verificada=True`) **ou**
   foi criado por vendedor interno (`criado_por_interno=True`);
3. `Produto.unidade_medida == FARDO` (a regra não se aplica a kg, saca ou unidade);
4. `quantidade > 50` (limiar estrito; 50 usa o preço-base);
5. `Produto.preco_atacado` está preenchido.

Um visitante que informa um CNPJ alheio (sem prova de vínculo) não recebe a tabela de
atacado: usa o preço-base online do canal.

Caso contrário, usa o preço-base do canal:

- checkout da loja para cliente ATACADO: `preco_balcao`;
- checkout da loja para cliente VAREJO: `preco_online` (comportamento da Fase 1);
- chamadas diretas ao serviço sem `preco_base`: `preco_balcao`.

O preço é capturado em `ItemPedido.preco_unitario` no checkout; alterações posteriores
no produto não reescrevem pedidos existentes.

## Modelo

`catalog.Produto.preco_atacado`: `DecimalField(10,2)`, nulo, `>= 0`, editável no
formulário de produto.

## Serviços

- `sales.services.calcular_preco_unitario(produto, cliente, quantidade, preco_base=None)`.
- `sales.services.calcular_item_pedido(...)` devolve um `ItemPedido` não salvo com o
  preço calculado (usado no checkout e em testes).
- `criar_pedido_do_carrinho` passa o preço-base do canal.

## Limitação conhecida

O carrinho (pré-checkout) continua exibindo `preco_online`; o valor final é recalculado
no servidor no checkout. O pedido e o pagamento usam o preço correto. A exibição do
preço promocional no carrinho pode ser tratada em fase posterior.

## Critérios de aceite

- [ ] Campo `preco_atacado` e migration aditiva.
- [ ] 51 fardos para cliente ATACADO usa atacado.
- [ ] 50 fardos usa preço-base.
- [ ] Cliente VAREJO nunca usa atacado.
- [ ] Visitante sem vínculo usando CNPJ de atacadista paga preço online.
- [ ] Vendedor interno pode aplicar a tabela para cliente cadastrado.
- [ ] Produto sem `preco_atacado` usa preço-base.
- [ ] Produto que não é fardo não aplica a regra.
- [ ] Checkout grava o preço calculado no `ItemPedido`.
- [ ] `help_text`, formulário e README atualizados.
