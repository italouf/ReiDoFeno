# Reauditoria N01–N03 — fechamento

## N01 — teste concorrente R01

**Contrato:** o teste oficial deve exercitar os dois interleavings sem
fixture inválida, thread reiniciada ou exceção não tratada.

Correções:
- `FiscalConcurrencyTests` prepara grupo/usuário em `setUp`, compatível com
  `TransactionTestCase`.
- `force_login` e demais etapas da thread ficam dentro do `try`.
- `thread_registro` é iniciada uma única vez; `_juntar` só faz join.
- `entrou`/`liberar` são liberados em falha; erros de thread são reportados.
- Conexões são fechadas em `finally`.

Aceite: PostgreSQL real, dois interleavings, zero exceção de thread e zero
thread abandonada.

## N02 — CMV comprovado × receita em conciliação

**Contrato:** a população financeira e a população de CMV não são a mesma
quando há incerteza de estorno.

- Receita financeira e receita de produtos excluem pagamento cancelado sem
  `estornado_em`; esse valor aparece em `receita_em_conciliacao`.
- CMV histórico usa itens com aprovação e snapshot, incluindo o estado
  financeiro inconclusivo. A baixa física conhecida não é apagada por
  incerteza sobre o estorno.
- A reversão de CMV continua sendo somente o movimento físico de devolução.
- Frete não é derivado de populações incompatíveis; sem frete real, é zero.
- Pedido nunca aprovado não entra; o filtro de `aprovado_em` permanece.

Aceite: CMV 160 permanece 160 no estado legado; receita 0; frete 0; valor
100/160 em conciliação, sem data de estorno inventada.

## N03 — integração fiscal, cancelamento e terminalidade

**Contrato:** integração, views manuais, fila e cancelamento compartilham as
mesmas garantias.

- `enviar_para_emissao` usa duas fases:
  1. lock curto do Pedido/Nota, revalidação, claim `processando_desde`;
  2. chamada externa fora do lock;
  3. lock curto para aplicar a resposta com releitura.
- `processando_desde` é lease; retry concorrente não chama o provedor.
- Autorização externa tardia após cancelamento é preservada, mas marcada com
  `Aviso` fiscal e auditoria de conciliação; não reabre pedido, não move
  estoque e não repete estorno.
- Nota cancelada não é reautorizada pelo retry ordinário nem pela fila.
- Chave duplicada continua tratada como conflito de domínio.

Aceite: integração não transforma cancelamento em sucesso silencioso; nota
cancelada permanece terminal; dois retries produzem no máximo uma chamada
externa.

## Limites

- A concorrência N01/N03 depende de PostgreSQL real e não roda no SQLite.
- O cliente fiscal é fake; nenhuma chamada SEFAZ/Bling real é feita.
- A pendência de autorização tardia é local/auditável; confirmação externa
  de cancelamento continua humana.
