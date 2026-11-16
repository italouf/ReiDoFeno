# ADR-006 — NF-e assistida (IOB)

**Fase:** 4
**Status:** Aceita (adaptação aprovada).
**Relaciona-se a:** ADR-012 (retenção), ADR-013 (ledger), ADR-017 (eventos
separados).

## Contexto

O cliente emite NF-e no IOB, fora do sistema. Não haverá integração de API no
MVP. O sistema já possui `fiscal.NotaFiscal` como registro fiscal único,
usado por relatório, fila, cancelamento e devolução. Criar um segundo modelo
(`NotaFiscalManual`) duplicaria a fonte de verdade.

## Decisão

- `NotaFiscal` recebe campos de snapshot (`cliente_nome`, `cliente_documento`,
  `cliente_tipo_pessoa`, `cliente_endereco`, `valor_total`, `itens_json`),
  `data_emissao`, `serie` e `pdf`.
- `status=anexada` representa documento com PDF/prova anexada, ainda sem
  confirmação final; `autorizada` representa confirmação no IOB.
- A exportação para IOB é um serviço puro (`exportar_para_iob`) e um endpoint
  de download JSON/CSV. Não grava estado.
- O snapshot é preenchido uma única vez, no primeiro registro/anexo, e nunca
  é sobrescrito por edição cadastral.
- Anexo e autorização respeitam o lease de emissão automática e invalidam a
  tentativa antiga; a fila automática não reivindica nota `anexada` ou de
  origem manual.
- A emissão automática também preenche snapshot, `data_emissao` e
  `retido_ate`; uma migration de dados faz o backfill das notas existentes.

## Consequências

- Uma única tabela fiscal preserva relatórios, fila e retenção.
- O fluxo manual fica rastreável: pendente → anexada → autorizada/cancelada.
- A exportação é reproduzível a partir do pedido, mas o snapshot é a prova
  histórica do que foi emitido.
