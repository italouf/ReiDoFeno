# CUS-01 — CNPJ alfanumérico (Receita Federal 2026)

**Fase:** 2B
**Prioridade:** P1
**Implementa:** `docs/specs/fase-2b-spec.md` §CUS-01
**Referência oficial:** Nota Técnica COCAD/SUARA/RFB nº 49/2024 e primeiro CNPJ
`00.000.000/E08G-12` (31/07/2026).

## Contexto observado

`customers.normalizar_documento()` remove tudo que não é dígito e
`DocumentoValidator` só aceita 11 ou 14 dígitos. Um CNPJ alfanumérico é mutilado na
normalização e rejeitado. `fiscal.services` também usa `_apenas_digitos`, e o filtro de
PII só mascara sequências numéricas.

## Algoritmo oficial

- 14 posições: 12 alfanuméricas (`A-Z`, `0-9`) + 2 dígitos verificadores numéricos.
- Cada caractere vale `ord(caractere) - 48` (ASCII). Assim `0-9` valem `0-9`,
  `A=17`, `B=18`, ..., `Z=42`.
- Pesos do DV1: `(5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)`.
- Pesos do DV2: `(6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)` incluindo o DV1.
- Módulo 11: resto `< 2` → DV `0`; caso contrário `11 - resto`.
- CNPJ numérico usa exatamente o mesmo cálculo (os dígitos mantêm o valor).

## Normalização

`normalizar_documento()` remove pontuação e converte letras para maiúsculas,
preservando `A-Z` e `0-9`. CPF continua exigindo 11 dígitos; qualquer letra em CPF é
rejeitada.

## Integrações

- `fiscal.services.pedido_elegivel`: usa o normalizador preservando letras.
- `core.logging_filters`: mascara CNPJ alfanumérico sem pontuação (14 caracteres com ao
  menos uma letra e um dígito), além de CPF/CNPJ numéricos.
- Formulários (`accounts`, `sales`, `customers`) herdam o validador; `max_length=18`
  comporta o formato mascarado.

## Critérios de aceite

- [ ] `00.000.000/E08G-12` é normalizado para `00000000E08G12` e aceito.
- [ ] Minúsculas são convertidas para maiúsculas.
- [ ] DV inválido é rejeitado.
- [ ] CNPJ numérico e CPF continuam válidos.
- [ ] `DocumentoValidator` e `validar_documento()` aceitam alfanumérico.
- [ ] Fiscal e mascaramento de PII preservam/protegem letras.
