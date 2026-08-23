# Delta: payment-processing

## Purpose

Definir a integração de pagamento via Mercado Pago Checkout Pro (Pix/cartão), incluindo criação de preferência, webhook assinado com processamento idempotente, guarda do evento bruto para auditoria, reprocessamento em falha e baixa de estoque somente após aprovação.

## ADDED Requirements

### Requirement: Criação de preferência de pagamento

Ao finalizar o checkout o sistema SHALL criar uma preferência no Mercado Pago Checkout Pro com valor e itens validados no servidor e redirecionar o cliente ao checkout do provedor. O sistema NÃO deve armazenar número de cartão nem credenciais de pagamento.

#### Scenario: Redirecionamento ao provedor
- **WHEN** o cliente conclui o checkout
- **THEN** uma preferência é criada com o valor correto calculado no servidor e o cliente é direcionado ao Checkout Pro

### Requirement: Webhook assinado e idempotente

O endpoint de webhook SHALL validar assinatura/origem das notificações do provedor antes de processar e MUST processar eventos de forma idempotente: o mesmo evento processado duas vezes não produz efeito duplicado.

#### Scenario: Evento duplicado ignorado
- **WHEN** o provedor reenvia a mesma notificação já processada
- **THEN** nenhuma segunda baixa de estoque ou duplo status ocorre e a resposta indica sucesso

#### Scenario: Assinatura inválida rejeitada
- **WHEN** uma chamada chega ao webhook sem assinatura válida
- **THEN** ela é rejeitada sem alterar pedidos ou pagamentos

### Requirement: Atualização do pedido por evento

Pagamento aprovado SHALL atualizar o pedido para "pago" de forma independente do navegador do cliente e efetivar a baixa/reserva definitiva do estoque; pagamento recusado ou pendente NÃO deve baixar estoque.

#### Scenario: Aprovação atualiza pedido e estoque
- **WHEN** o webhook confirma pagamento aprovado
- **THEN** o pedido passa a "pago" e o estoque reservado é definitivamente baixado

#### Scenario: Recusa não baixa estoque
- **WHEN** o pagamento é recusado
- **THEN** o pedido permanece sem baixa definitiva de estoque e sinaliza falha/pendente conforme o caso

### Requirement: Auditoria e reprocessamento de webhooks

O sistema SHALL guardar o evento bruto recebido para auditoria e SHALL permitir reprocessamento manual ou automático quando o processamento inicial falhar.

#### Scenario: Evento bruto armazenado
- **WHEN** qualquer notificação chega ao webhook
- **THEN** o payload bruto fica persistido com data e resultado do processamento

#### Scenario: Falha permite reprocessar
- **WHEN** o processamento de um evento falha por erro interno
- **THEN** o evento pode ser reprocessado depois sem perder consistência do pedido
