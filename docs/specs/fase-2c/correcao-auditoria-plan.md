# Plano de correção da auditoria — Fase 2C

## Ordem

1. **A01/A02 — eventos e reconciliação**
   - Reproduzir chargeback via `aplicar_resultado_pagamento`.
   - Separar receita de produto, receita de frete, CMV e retorno físico.
   - Testar períodos diferentes e mesmo período.
2. **A03/A04 — retorno físico e evidência**
   - Permitir devolução após estorno confirmado sem novo estorno.
   - Remover fallback de quantidade pedida como baixa.
   - Compensar somente obrigação baixada e não compensada.
   - Registrar pendência quando não houver prova.
3. **A05/A07 — fiscal manual e CFOP**
   - Fila e formulário de entrada para Emissor Fiscal.
   - Validar referência à saída autorizada.
   - Bloquear edição comum de CFOP confirmado; permitir saneamento com
     motivo/evidência.
4. **A06 — CSV fiscal**
   - Alinhar `evento_em`/`evento`; sanitizar texto contra fórmulas.
   - Testar CSV preenchido e vazio.
5. **A08 — CSP**
   - Remover CDN e script inline.
   - Servir `static/js/relatorios.js` local.
   - Validar em navegador com CSP efetiva.
6. **A09 — CI**
   - Incluir a branch no gatilho de push e manter PostgreSQL 15/Redis.

## Dependências

- A05 depende de o modelo distinguir entrada de saída (já existente).
- A03 depende de A04 para não criar crédito sem evidência.
- A08 depende de A01 para os dados exibidos estarem reconciliados.
