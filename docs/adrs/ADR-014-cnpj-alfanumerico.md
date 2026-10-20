# ADR-014 — CNPJ alfanumérico

**Status:** Aceito
**Data:** 2026-10-20
**Fase:** 2B
**Referência:** Nota Técnica COCAD/SUARA/RFB nº 49/2024

## Contexto

A Receita Federal passou a emitir CNPJ com 12 posições alfanuméricas e 2 dígitos
verificadores numéricos. O sistema normalizava documentos removendo letras, o que
transformava `00.000.000/E08G-12` em `000000000812` e invalidava o cadastro.

## Decisão

Preservar letras maiúsculas na normalização e validar CNPJ alfanumérico com o algoritmo
oficial: valor de cada caractere = código ASCII - 48; pesos e módulo 11 idênticos ao
CNPJ numérico. O DV continua estritamente numérico. CPF permanece numérico.

O armazenamento continua sem pontuação e em maiúsculas (`00000000E08G12`), preservando
a chave única e a compatibilidade com os 18 caracteres do campo.

## Alternativas rejeitadas

1. **Aceitar apenas o formato mascarado:** o banco e os integradores já trabalham com
   documentos normalizados; exigir máscara quebraria o fluxo atual.
2. **Converter letras para dígitos:** destrói a identidade fiscal e permite colisões.
3. **Validar somente o formato, sem DV:** aceitaria documentos inválidos e transferiria
   o erro para a emissão fiscal.

## Consequências

- Positivas: novos CNPJs aceitos sem regressão dos numéricos; validação fiscal correta;
  PII alfanumérica mascarada em logs.
- Negativas: integrações externas que assumam 14 dígitos precisam ser auditadas; a
  documentação oficial deve ser acompanhada caso a RFB publique ajustes.
