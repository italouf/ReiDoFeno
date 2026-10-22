# Rastreabilidade da reauditoria R01–R05

| ID | Contrato/invariante | Reprodução inicial | Causa raiz | Mudança | Testes | Evidência | Estado |
|---|---|---|---|---|---|---|---|
| R01 | Primeiro registro fiscal e cancelamento serializados | POST pausa após elegibilidade; cancelamento concorrente; hoje 302 com nota autorizada em pedido cancelado | Pedido carregado no dispatch, não relido/travado dentro da transação | Lock `Pedido → NotaFiscal`, releitura e revalidação sob lock; ausência de nota serializada pelo pedido | `fiscal/tests/test_concurrency_postgres.py`, `test_auditoria_fase2c.py` | PG test marcado; sequencial local | Corrigido; PG pendente de CI |
| R02 | Chave fiscal não vazia é globalmente única | Duas confirmações concorrentes da mesma chave | `exists` de aplicação sem exclusão atômica | Constraint condicional, preflight de legado e tratamento de `IntegrityError` | `test_auditoria_fase2c.py::A02ChaveUnicaTests`, PG `test_r02...` | SQLite constraint; PG pendente | Corrigido; CI pendente |
| R03 | Retorno legado só por vínculo explícito/formato canônico | Motivo com `PF... ou PF...` associava ao primeiro | Regex livre `PF\d+` | Padrões canônicos ancorados e exatamente um PF; ambíguo fica em conciliação | `test_motivo_ambiguo_nao_atribui_retorno_a_ninguem`, `test_movimento_legado...` | CMV não revertido; crédito bloqueado | Corrigido e verificado |
| R04 | Receita financeira, produtos e frete com mesma população | Cancelado sem data: receita 0, produtos 100, frete -100 | Filtro divergente entre pagamentos e itens | Exclusão compartilhada; `receita_em_conciliacao` separada | `test_pagamento_cancelado_sem_data_nao_gera_frete_negativo` | 0/0/0 e 100 em conciliação | Corrigido e verificado |
| R05 | Altura lógica estável em DPR 1/2 | Altura CSS crescia a cada resize em DPR 2 | `canvas.height` realimentava `getAttribute("height")` | `data-logical-height` e dimensões CSS/backing separadas | `static/js/relatorios.test.mjs`, browser DPR 2 | 4 resizes: 240 CSS/480 backing | Corrigido e verificado |

## Níveis de evidência

- R01/R02: teste concorrente PostgreSQL marcado; indisponível no SQLite local.
- R03/R04: testes locais SQLite.
- R05: Node test e browser emulado DPR 2.
- CI remoto: pendente de novo push/PR no SHA final.
- Aceite humano: pendente.
