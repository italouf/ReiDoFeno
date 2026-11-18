# ADR-012 — Retenção de dados fiscais por 5 anos

**Fase:** 4
**Status:** Aprovada com adaptação: snapshot fica em `NotaFiscal`, não em um
modelo paralelo.

## Contexto

A legislação exige guarda de documentos fiscais por cinco anos. A LGPD dá ao
titular direito de exclusão, mas a obrigação legal de retenção prevalece para
o documento fiscal. O sistema já anonimiza clientes com pedidos, mas precisa
garantir que o snapshot fiscal sobreviva à exclusão/anonimização e que a
limpeza só ocorra após o prazo.

## Decisão

1. `NotaFiscal` guarda o snapshot do cliente e dos itens no momento da
   emissão (ADR-006). O snapshot nunca é recalculado.
2. `NotaFiscal.retido_ate` é recalculado em `save()` a partir de
   `data_emissao` + 5 anos de calendário (tratando 29/02 e usando a data
   local). A data de emissão é validada contra futuro e retroatividade
   excessiva nos formulários.
3. `anonimizar_cliente` pseudonimiza o cadastro e preserva os pedidos e as
   notas. O documento pseudonimizado é numérico e único; a cadeia `"***"`
   não é usada porque violaria validadores e unicidade.
4. A anonimização grava auditoria `cliente_anonimizado_com_notas` quando há
   nota fiscal e `cliente_anonimizado_com_pedidos` quando há apenas pedidos.
5. O comando `limpar_notas_expiradas` remove somente notas
   `autorizada`/`cancelada` com `retido_ate < hoje`, em transação, com
   auditoria por nota. `--dry-run` apenas informa a quantidade.
6. Notas sem `data_emissao` não recebem `retido_ate` e não são removidas pelo
   comando até que a data seja corrigida.

## Consequências

- O direito de exclusão não apaga prova fiscal dentro do prazo legal.
- A retenção é auditável e reproduzível.
- Notas antigas fora do prazo podem ser limpas sem tocar em pedidos.
