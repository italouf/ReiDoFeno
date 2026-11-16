# ADR-018 — Pagamento manual sem gateway online

## Status

Aceita — Fase 4.

## Contexto

O MVP não usará gateway de pagamento online. A operação recebe PIX direto,
dinheiro na entrega e cartão presencial. O sistema precisa registrar esses
recebimentos com prova, conciliação humana e auditoria, sem quebrar:

- a separação entre `Pedido.status` e `Pedido.status_financeiro` (ADR-002);
- a receita por pagamento (ADR-016);
- a baixa de estoque por obrigação (ADR-015);
- a separação entre evento financeiro, físico e fiscal (ADR-017).

O `Pagamento` existente é `OneToOne` com o pedido e é a fonte da receita.
Criar um segundo modelo de pagamento paralelo faria painéis e relatórios
ignorarem os recebimentos manuais.

## Decisão

1. `ComprovantePagamento` registra cada prova recebida (método, valor, data,
   referência, arquivo, autor). É evidência, não receita.
2. Ao cobrir o total, o pedido recebe `status_financeiro=pago`, mas
   `financeiro_conciliado=False`. A receita é reconhecida atualizando o
   `Pagamento` único do pedido (`provedor="manual"`, `aprovado_em` = data do
   pagamento que fechou o saldo).
3. A conciliação financeira (`Financeiro`/`Administrador`) apenas valida a
   prova e marca `financeiro_conciliado=True`. Somente depois disso o pedido
   pode avançar para separação/entrega (ADR-002/015).
4. Rejeitar a conciliação reverte `status_financeiro` para `pendente`,
   marca os comprovantes como `rejeitado` e cancela o `Pagamento` limpando
   `aprovado_em` e `estornado_em`. A receita manual era provisória (a prova
   nunca foi confirmada), então ela é removida sem gerar um estorno sem
   contrapartida no período do reconhecimento. O estoque **não** é devolvido
   automaticamente: rejeição financeira não é retorno físico (ADR-017).
5. Comprovantes rejeitados permanecem armazenados como evidência histórica,
   mas não contam para o saldo devedor.
6. PIX exige referência única; a data do pagamento não pode estar no futuro
   nem retroceder mais de um ano; o upload valida extensão, MIME e assinatura
   binária. Enquanto houver prova ativa, o checkout online do pedido fica
   bloqueado. Aprovação do provedor com prova manual não auto-concilia.
7. Cancelamento de pedido pendente com baixa já efetivada devolve ao estoque
   somente quantidades com evidência, via movimento de ledger auditado.

## Consequências

- O pagamento manual aparece em painel, relatório fiscal e métricas do
  vendedor sem código de agregação paralelo.
- A operação não consegue separar mercadoria sem conciliação explícita.
- Rejeição não apaga histórico nem inventa movimento de estoque.
- Um pedido só tem um `Pagamento`; a decomposição por método fica nos
  comprovantes.
