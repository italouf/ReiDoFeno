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

## Fechamento da reauditoria (R01–R05)

- Primeiro registro fiscal e cancelamento serializam pelo lock do Pedido,
  na ordem `Pedido → NotaFiscal`; a ausência inicial de nota não é protegida
  por lock de linha inexistente.
- Chave de acesso não vazia é globalmente única por constraint condicional;
  legado duplicado aborta a migração para conciliação, sem escolher vencedor.
- Retorno legado só é associado por FK explícita ou formato canônico
  inequívoco; motivo com mais de um pedido permanece em conciliação.
- Receita financeira, receita de produtos e frete usam a mesma população
  elegível. Pagamento cancelado sem data de estorno fica em
  `receita_em_conciliacao`, fora da identidade e sem frete negativo.
- A altura lógica do canvas é independente do backing store; DPR 2 não
  acumula escala em resizes.

## Fechamento da reauditoria N01–N03

- Receita financeira e receita de produtos podem ficar em conciliação,
  separadas; o CMV histórico comprovado não é apagado por incerteza sobre o
  estorno. CMV só reverte por retorno físico.
- A integração fiscal usa duas fases: claim/lease curto, chamada externa
  fora do lock, aplicação com releitura. Retry concorrente não duplica a
  chamada externa.
- Autorização externa tardia após cancelamento é preservada com `Aviso` e
  auditoria; não reabre o pedido, não move estoque e não repete estorno.
- Nota cancelada é terminal para o retry ordinário e para a fila.
- O teste concorrente R01 usa `TransactionTestCase` com `setUp`, threads
  iniciadas uma única vez e eventos liberados em falha.

## Consequências

- Mesmo período e mesmo escopo reconciliam painel, vendedor, produto,
  comparativo e relatório fiscal.
- `lucro_bruto` de produtos = `receita_produtos - cmv`; frete é exposto
  separadamente (`receita_frete`) e não é atribuído ao lucro de produto.
- O CMV é revertido somente por movimento físico com obrigação, permitindo
  devolução parcial.
- O fluxo fiscal manual tem fila própria e não exige financeiro atualmente
  pago para documentar uma devolução já ocorrida.
