# Reauditoria R01–R05 — contratos de fechamento

## Objetivo

Fechar as lacunas encontradas na reauditoria do SHA `bcaebde`, sem
reescrever o histórico A01–A09 e sem fabricar eventos financeiros, fiscais ou
de estoque.

## R01 — primeiro registro fiscal × cancelamento

**Contrato:** o primeiro registro de saída e o cancelamento do pedido são
serializados pela linha do pedido.

- `RegistrarNotaManualView` relê e trava o `Pedido` dentro da transação,
  antes de procurar a nota.
- A ausência inicial de nota é protegida pelo lock do pedido, não por um
  `select_for_update` sobre uma linha que ainda não existe.
- A ordem é `Pedido → NotaFiscal`, compatível com cancelamento e devolução.
- Nota preexistente pós-estorno pode ser retificada/saneada sem exigir
  financeiro atualmente pago.
- Se o cancelamento vencer, o registro é rejeitado; se o registro vencer, o
  cancelamento enxerga a nota e a cancela.

**Evidência:** teste PostgreSQL concorrente
`fiscal/tests/test_concurrency_postgres.py::test_r01_registro_primeiro_serializa_com_cancelamento`;
teste sequencial de primeiro registro após cancelamento.

## R02 — unicidade global da chave fiscal

**Contrato:** uma chave de acesso não vazia pertence a uma única nota.

- Constraint condicional `nota_fiscal_chave_acesso_unica` para
  `chave_acesso != ''`.
- Migração `fiscal/0004_chave_acesso_unica.py` faz preflight de duplicidades
  legadas e aborta com diagnóstico, sem apagar/inventar documentos.
- Escritores manuais e integração tratam `IntegrityError` como conflito de
  formulário/domínio em savepoint, sem HTTP 500.
- Chaves vazias continuam permitidas para documentos pendentes.
- Conflito não expõe dados de outro pedido além do necessário.

**Evidência:** teste SQLite de constraint; teste PostgreSQL concorrente
`test_r02_duas_notas_nao_confirmam_a_mesma_chave`; testes de duplicidade na
view.

## R03 — associação de retorno legado

**Contrato:** apenas vínculo FK explícito ou formato histórico canônico
inequívoco autoriza atribuição.

- `_obrigacao_por_movimento` aceita:
  - `Cancelamento padrão do pedido PF...` (formato canônico);
  - `Devolução do pedido PF...: ...` (formato canônico).
- Exige exatamente um `PF...` no motivo; texto com dois pedidos, referência
  ausente ou texto livre não é autoridade.
- Movimento sem associação permanece visível, não reduz CMV de nenhum
  pedido e bloqueia novo crédito até conciliação.
- A mesma função é usada por análise e compensação de estoque.

**Evidência:** teste de motivo ambíguo com dois pedidos; teste de movimento
legado canônico; teste de evidência sem atribuição.

## R04 — população elegível e decomposição da receita

**Contrato:** receita financeira, receita de produtos e frete usam a mesma
população de pagamentos elegíveis.

- `pagamentos_aprovados` e `_itens_vendidos` excluem pagamento
  `CANCELADO` sem `estornado_em`.
- Esses valores não são convertidos em frete negativo nem em CMV.
- `receita_em_conciliacao` é exposta separadamente; não há data de estorno
  inventada.
- A identidade `receita = receita_produtos + receita_frete` vale para
  pagamentos elegíveis; valores inconclusivos ficam fora da identidade.

**Evidência:** `test_pagamento_cancelado_sem_data_nao_gera_frete_negativo`;
teste de frete separado; teste de aprovação tardia.

## R05 — canvas estável em DPR 1/2

**Contrato:** a altura lógica é independente do backing store.

- `data-logical-height` preserva a altura de layout entre resizes.
- `canvas.height`/`width` acompanham o DPR apenas na resolução interna.
- O handler redefine dimensões e transformação, sem acumular multiplicação.
- Não há CDN nem script inline; CSP permanece `default-src 'self'`.

**Evidência:** `static/js/relatorios.test.mjs` com Node test (DPR 1 e DPR 2,
quatro resizes); browser emulado com DPR 2 mantendo CSS 240 px e backing 480
px em três resizes.

## Limites

- A validação PostgreSQL R01/R02 não roda no SQLite local; os testes ficam
  marcados `postgres` e dependem da CI.
- A constraint de chave pressupõe saneamento de duplicidades legadas; a
  migração aborta com diagnóstico se houver conflito.
- O registro de entrada continua manual/assistido; não há SEFAZ real.
- Custo legado continua aproximado.
