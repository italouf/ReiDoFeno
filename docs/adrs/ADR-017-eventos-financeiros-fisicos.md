# ADR-017 — Eventos financeiros, físicos e fiscais separados

## Status

Aceita — correção da auditoria da Fase 2C.

## Contexto

A Fase 2C passou a reconhecer receita por pagamento, mas ainda misturou três
fatos distintos ao calcular painéis e ao cancelar/devolver:

- aprovação e estorno **financeiros**;
- retorno **físico** de mercadoria;
- registro **fiscal** de uma NF-e de entrada.

Isso produzia lucro divergente entre painéis após chargeback, apagava CMV de
competências passadas, bloqueava devolução depois de estorno e creditava
estoque sem prova de baixa.

## Decisão

Cada fato tem uma competência e um efeito próprios:

| Evento | Fonte | Receita de produtos | CMV | Estoque |
|---|---|---|---|---|
| Aprovação | `Pagamento.aprovado_em` | + | + | baixa conforme evidência |
| Estorno/chargeback | `Pagamento.estornado_em` | − | 0 | 0 |
| Retorno físico | `MovimentoEstoque` `entrada_devolucao` com obrigação | 0 | − | + quantidade comprovada |
| Documento de entrada | `NotaFiscal` tipo `entrada` | 0 | 0 | 0 |

- `Pedido.status` não define competência financeira nem autoriza retorno.
- Chargeback não é retorno físico.
- Retorno físico após chargeback não gera segundo estorno.
- O CMV original permanece na competência da aprovação até existir movimento
  de devolução comprovado.
- O documento de entrada é registro documental; não repete estoque/estorno.
- Estoque só é compensado com `ObrigacaoEstoquePedido.quantidade_baixada`
  comprovada e não compensada; sem evidência, cria-se pendência/`Aviso`.

## Consequências

- Mesmo período e mesmo escopo reconciliam painel, vendedor, produto,
  comparativo e relatório fiscal.
- `lucro_bruto` de produtos = `receita_produtos - cmv`; frete é exposto
  separadamente (`receita_frete`) e não é atribuído ao lucro de produto.
- O CMV é revertido somente por movimento físico com obrigação, permitindo
  devolução parcial.
- O fluxo fiscal manual tem fila própria e não exige financeiro atualmente
  pago para documentar uma devolução já ocorrida.
