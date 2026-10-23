# L01 — autoridade da tentativa fiscal

Status: implementado localmente; Gate C pendente no SHA final.

## Contrato

Uma chamada ao provedor fiscal só pode alterar a `NotaFiscal` enquanto a
tentativa que a originou ainda for dona do claim. O documento canônico, o
terminal e o resultado de uma tentativa mais nova não são “última resposta
vence”.

### Identidade e aquisição

- `NotaFiscal.tentativa_atual` é um UUID gerado dentro da transação que
  revalida o Pedido e a Nota, na ordem `Pedido → NotaFiscal`.
- A mesma transação grava `processando_desde = agora`; o lease é
  `LEASE_EMISSAO = 2 minutos`.
- Um retry com lease ativo não chama o provedor.
- Lease expirado pode ser reivindicado por uma nova tentativa automática ou
  pelo registro manual. A nova aquisição substitui o token; a tentativa
  anterior perde a autoridade.
- O token não é inferido de tempo decorrido, thread ou processo. A conclusão
  compara o UUID relido sob lock.

### Matriz de conclusão

| Autoridade atual | Resultado recebido | Comportamento |
|---|---|---|
| Token A ainda é dono; documento mutável | Sucesso de A | Reler Pedido/Nota sob lock, aplicar número/chave/link e liberar A |
| Token A ainda é dono; documento mutável | `ErroFiscal` de A | Registrar erro de A e liberar A |
| Token B passou a ser dono | Sucesso/erro de A | Não alterar status, número, chave, origem, token nem lease de B; guardar evidência de A |
| Documento confirmado/autorizado sem A | Sucesso/erro de A | Não substituir/rebaixar; guardar evidência e pendência |
| Documento cancelado | Sucesso/erro de A | Não desfazer terminalidade; guardar evidência e pendência |
| Retorno externo após cancelamento do Pedido | Autorização real de A | Preservar o fato com aviso/auditoria, sem reabrir pedido, estoque ou estorno |
| Mesmo resultado repetido | Mesmo token e tipo | Não duplicar evento, aviso nem auditoria |

### Registro manual

- Com lease ativo, a rota manual retorna erro de formulário tratável e não
  acessa o documento. O bloqueio é verificado sob o lock `Pedido → Nota`, não
  apenas escondendo botão.
- Com lease expirado ou ausente, a confirmação manual é permitida. Ela limpa
  `tentativa_atual`/`processando_desde`, grava origem `manual` e registra
  `fiscal.tentativa_manual_assumida` quando havia claim expirado.
- Um retorno da tentativa antiga depois disso encontra token divergente e
  vira evidência de conciliação; número, chave, origem e status manuais ficam
  preservados.

### Cancelamento e resultado externo

- `cancelar_nota_fiscal` limpa o claim ao cancelar ou ao repetir um
  cancelamento já idempotente, e audita a tentativa invalidada.
- Respostas tardias/conflitantes são gravadas em
  `NotaFiscal.resultado_externo["eventos"]`, com token, tipo, resultado,
  motivo e instante. O histórico mantém os 20 eventos mais recentes.
- Um `Aviso` fiscal e `LogAuditoria` com ação
  `fiscal.resultado_externo_obsoleto` tornam a conciliação visível.
- Eventos repetidos do mesmo token/tipo são idempotentes. Uma resposta de
  outro documento não é descartada nem convertida em cancelamento externo
  fictício.
- A evidência não reabre o pedido, não movimenta estoque e não repete
  estorno.

## Ordem de locks e atomicidade

1. Aquisição e confirmação manual: `Pedido → NotaFiscal`.
2. Conclusão de sucesso: `Pedido → NotaFiscal`.
3. Conclusão de erro: `NotaFiscal` (não há alteração de Pedido).
4. Cancelamento documental: `NotaFiscal`, com o Pedido já bloqueado pelo
   fluxo de cancelamento quando aplicável.
5. A chamada externa ocorre fora dos locks.

A comparação de token e a escrita final ocorrem na mesma transação. Um erro
de auditoria reverte a evidência e a transição correspondente.

## Persistência e migração

- `fiscal/0006_tentativa_emissao.py` adiciona `tentativa_atual` (UUID nulo) e
  `resultado_externo` (JSON vazio), sem reescrever migrações compartilhadas.
- Notas legadas ficam com token nulo e evidência vazia; a primeira tentativa
  nova cria seu próprio token.

## Testes de aceite

- `fiscal/tests/test_auditoria_fase2c.py::L01AutoridadeTentativaTests` cobre
  bloqueio manual, sucesso/erro antigos, cancelamento, claim novo ativo,
  sucesso de B, terminalidade, conflito de chave, evidência e idempotência.
- `fiscal/tests/test_concurrency_postgres.py::FiscalConcurrencyTests` contém
  os interleavings PostgreSQL marcados: bloqueio manual sob lease, sucesso/
  erro antigos após tomada manual e erro antigo contra sucesso de B.
- O controle de retry ativo continua sem chamar o provedor.

## Limites

- O cliente fiscal é fake; nenhuma SEFAZ/Bling real foi chamada.
- A validação PostgreSQL + Redis é remota; o ambiente local só executa
  SQLite e marca os testes de concorrência como skip.
- A aprovação do cliente (Gate H) não é presumida.
