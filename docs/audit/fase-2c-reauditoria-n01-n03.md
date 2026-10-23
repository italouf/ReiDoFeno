# Rastreabilidade N01–N03

| ID | Invariante | Reprodução | Causa | Correção | Testes | Evidência | Estado |
|---|---|---|---|---|---|---|---|
| N01 | R01 executa os dois interleavings sem fixture/thread inválida | Teste falhava em `entrou.wait` por `AttributeError: gestor`; threads reiniciavam | `setUpTestData` em `TransactionTestCase`, login fora do `try`, start duplo | `setUp` por teste, login dentro do `try`, start/join separados, eventos liberados em falha | `fiscal/tests/test_concurrency_postgres.py` | suíte PG pendente local; código corrigido | Corrigido; PG pendente |
| N02 | CMV comprovado não é apagado por receita inconclusiva | Pagamento aprovado, baixa física e depois status cancelado sem estorno: CMV 160→0 | Mesmo filtro financeiro alimentava receita e CMV | População financeira separada da população histórica de CMV; conciliação explícita | `test_cmv_fisico_permanece_quando_receita_entra_em_conciliacao`, R04 | CMV 160 preservado; receita 0; frete 0 | Corrigido e verificado |
| N03 | Integração respeita cancelamento e terminalidade | Autorização tardia após cancelamento sem pendência; retry reautorizava nota cancelada | Serviço sem claim/lock consistente e sem terminalidade cancelada | Duas fases com lease, releitura final, aviso/auditoria de autorização tardia, bloqueio de nota cancelada na fila/serviço | `N03IntegracaoFiscalTests`, testes PG de concorrência | 3 testes locais; concorrência PG pendente | Corrigido; PG pendente |

## Evidência

- N02: teste local SQLite.
- N03: testes locais com cliente fake; sem chamada fiscal real.
- N01/N03 concorrentes: PostgreSQL real necessário; testes marcados.
- CI remota: pendente no novo SHA.
- Aceite humano: pendente.

## L01 — autoridade da tentativa

A correção L01 foi acrescentada sem alterar os contratos N01–N03. O token
`NotaFiscal.tentativa_atual` é comparado sob lock na conclusão de sucesso e
erro; a confirmação manual coordena com o lease; cancelamento invalida o
claim; resultados antigos/conflitantes ficam em `resultado_externo` com
`Aviso` e auditoria. A matriz e a política completas estão em
`docs/audit/fase-2c-reauditoria-l01.md` e
`docs/specs/fase-2c/l01-autoridade-tentativa.md`.
