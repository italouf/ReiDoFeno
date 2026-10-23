# PR preparada — L02/L03

Não publicar sem autorização.

## Título

`fix(fiscal): separa avisos e torna durável a deduplicação de eventos (L02/L03)`

## Corpo

### Contexto

A auditoria independente de `409b9f5` confirmou L01, mas reproduziu dois
bloqueadores:

- L02: múltiplos avisos por evento faziam `Aviso.registrar()` lançar
  `MultipleObjectsReturned`, revertendo o encerramento da tentativa e podendo
  interromper a fila;
- L03: a deduplicação de eventos vivia apenas nos últimos 20 eventos do JSON,
  permitindo replay após rotação.

### Correção

- `Aviso.evento_chave` identifica eventos; avisos agregados usam chave vazia.
- `Aviso.registrar()` procura somente agregados e é resistente a avisos
  antigos/duplicados.
- Migração aditiva `analytics/0004` preserva avisos existentes e cria a
  identidade condicional única.
- A deduplicação usa a chave durável por
  `(nota, tentativa, tipo)`, com lock da Nota e fallback para JSON/auditoria
  legados.
- L01 permanece preservado: token, terminalidade, manual, evidência e
  ausência de efeitos de estoque/estorno.

### Testes

- 6 cenários SQLite L02/L03 (retry A/B/C, avisos antigos, conflito de chave,
  idempotência após 20 eventos e evento legado em auditoria).
- 2 testes PostgreSQL marcados: retry A/B/C e replay concorrente.
- Regressões L01 e suíte anterior preservadas.
- Validação local: 655 passed, 24 skipped, 240 subtests; cobertura 86,39%;
  Node 2/2; Ruff/check/migrações/Bandit/pip-audit limpos.
- Reauditoria independente no SHA `2a7a300`: SQLite 655/24 e PostgreSQL 16.2
  678/1; CI `39953967926` success com PostgreSQL 15 + Redis e migração
  histórica.

### Gates

- T: **aprovado com observações não bloqueantes** pela reauditoria
  independente.
- C: **aprovado** no SHA `2a7a300`, CI `39953967926`.
- H: **pendente**; aceite do cliente ainda não executado.

### Fora de escopo

Sem merge, deploy, Neon, dados/SEFAZ/Bling reais ou reembolso. A branch já
foi publicada no SHA `2a7a300`; a PR remota ainda depende de autorização e
governança.
