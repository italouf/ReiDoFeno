# ADR-007 — Cancelamento com dois caminhos

## Contexto

O cliente separa dois fatos operacionais que o sistema tratava como um só:

1. **Cancelamento padrão (até 24h)**: a mercadoria não saiu da loja; a NF-e
   de saída, se existir, deve ser cancelada e o pagamento estornado.
2. **Devolução (após 24h ou após entrega)**: a mercadoria volta fisicamente;
   exige NF-e de entrada com CFOP inverso e referência à NF-e de saída.

O cancelamento antigo liberava reservas, mas não distinguia os caminhos, não
registrava justificativa/ator e não tratava nota fiscal.

## Decisão

`Pedido` passa a registrar `tipo_cancelamento` (`padrao`/`devolucao`),
`justificativa_cancelamento`, `cancelado_em` e `cancelado_por`.

### Cancelamento padrão

`cancelar_pedido_padrao`:

- exige justificativa e ator;
- exige pagamento aprovado há no máximo 24h;
- recusa pedido `enviado` ou `concluido`;
- cancela a NF-e de saída autorizada, quando existir;
- estorna o pagamento e marca o financeiro como cancelado;
- devolve ao estoque apenas a quantidade efetivamente baixada;
- libera reservas ativas;
- audita antes/depois com o ator.

### Devolução

`registrar_devolucao`:

- exige pedido com financeiro pago e NF-e de saída com chave;
- cria/retorna NF-e de entrada com `chave_referenciada` e CFOP inverso;
- devolve ao estoque a quantidade baixada (ou a quantidade do item em dados
  legados sem obrigação);
- estorna o pagamento;
- registra o caminho como `devolucao` e audita.

## Invariantes

- O estoque só é devolvido por movimento de ledger (`ENTRADA_DEVOLUCAO`),
  nunca por update direto de saldo.
- O caminho é idempotente pelo par pedido/tipo.
- Nenhum cancelamento apaga movimentos; compensações são movimentos novos.
- A NF-e de entrada é uma linha própria; o pedido pode ter uma saída e uma
  entrada, portanto `NotaFiscal.pedido` passa de `OneToOne` para `ForeignKey`.

## Consequências

- O pedido ganha trilha explícita de cancelamento.
- `Pedido.nota_fiscal` continua existindo como propriedade de compatibilidade
  para a nota de saída.
- A emissão real da NF-e de entrada continua manual/assistida nesta fase;
  o sistema registra e audita o documento e o CFOP.
- A reversão da migração `NotaFiscal` de `OneToOne` para `ForeignKey` não é
  possível depois que um pedido tiver saída e entrada; o rollback deve ser
  tratado como operação de recuperação manual.
- O prazo de 24h é aplicado ao cancelamento padrão. A devolução é permitida
  após pagamento; a política temporal posterior (janela de arrependimento,
  frete de retorno) depende de decisão operacional e não é inventada aqui.
- Após devolução, o status operacional não é convertido em `cancelado` quando
  o pedido já estava `concluido`; o fato fica em `tipo_cancelamento` e na
  NF-e de entrada. Um estado operacional dedicado pode ser avaliado na Fase 3.
