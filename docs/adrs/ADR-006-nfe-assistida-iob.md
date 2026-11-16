# ADR-006 — NF-e assistida via IOB (dados prontos para exportação)

**Fase:** 4
**Status:** Aprovado com adaptação: o registro fiscal único continua em
`fiscal.NotaFiscal`; não há modelo `NotaFiscalManual` paralelo.

## Contexto

O cliente usa o IOB como ERP fiscal, sem integração por API no MVP. A NF-e é
emitida fora do sistema e precisa ser registrada com prova documental, sem
duplicar o registro fiscal usado por relatórios e pela fila de emissão.

## Decisão

1. `fiscal.NotaFiscal` acumula os dados de snapshot do pedido no momento da
   emissão: cliente, documento, tipo de pessoa, endereço, total e itens.
2. `exportar_para_iob(pedido)` gera JSON; `exportar_para_iob_csv(pedido)`
   gera CSV. Ambos são somente leitura e não alteram a nota.
3. O operador pode:
   - baixar os dados para importar no IOB;
   - anexar o PDF da NF-e em rascunho (`status=anexada`);
   - registrar a nota completa (número, série, chave, data e PDF), passando
     para `status=autorizada`.
4. O snapshot não é recalculado depois de preenchido: mudanças posteriores
   no cliente não alteram o documento fiscal.
5. A exportação usa escape contra fórmulas em CSV.

## Consequências

- Relatórios, fila e retenção continuam lendo uma única tabela.
- O PDF é evidência anexa; a autorização continua explícita.
- A emissão permanece manual e fora do sistema, conforme decisão do cliente.
