# Delta: business-insights

## Purpose

Definir o painel operacional (vendas, estoque, lucro estimado), métricas próprias do vendedor, avisos internos automáticos (estoque baixo, pedido pago sem NF-e, pagamento pendente, possível recompra) e o link manual de WhatsApp para contato.

## ADDED Requirements

### Requirement: Painel administrativo

O sistema SHALL exibir painel para perfis internos autorizados com vendas por período, produtos mais vendidos, estoque baixo, despesas, lucro estimado e pedidos aguardando pagamento. Pedidos cancelados NÃO devem entrar nas métricas de venda concluída.

#### Scenario: Cálculo de vendas do período
- **WHEN** o gestor abre o painel filtrando um período
- **THEN** vendas, despesas e lucro estimado são calculados a partir dos pedidos pagos/concluídos do período

#### Scenario: Cancelados fora das métricas
- **WHEN** um pedido cancelado existe no período
- **THEN** ele não é somado às métricas de venda concluída

### Requirement: Métricas do vendedor

O sistema SHALL exibir ao vendedor suas métricas próprias (pedidos do dia, vendas, clientes atendidos, pedidos pendentes), derivadas dos seus registros e pedidos; vendedores NÃO devem ver métricas uns dos outros sem permissão.

#### Scenario: Visão individual
- **WHEN** um vendedor abre sua tela de métricas
- **THEN** apenas dados das próprias interações/pedidos são apresentados

### Requirement: Avisos internos automáticos

O sistema SHALL gerar avisos internos para: estoque baixo, pedido pago sem NF-e, pagamento pendente há muito tempo e possível recompra, cada aviso com tipo, severidade, mensagem, origem e marcação de lido/não lido.

#### Scenario: Pedido pago sem nota gera aviso
- **WHEN** um pedido permanece pago sem NF-e emitida além do limite configurado
- **THEN** um aviso aparece na central de avisos dos perfis responsáveis

#### Scenario: Pagamento antigo pendente gera aviso
- **WHEN** um pedido aguarda pagamento por mais tempo que o configurado
- **THEN** um aviso de pagamento pendente é criado

### Requirement: Heurística de recompra

O sistema SHALL sinalizar possível recompra quando um cliente não compra há X dias configuráveis considerando seu histórico/ciclo típico de reposição, gerando aviso consultável pelos vendedores/gestor.

#### Scenario: Cliente elegível para recompra
- **WHEN** o intervalo desde a última compra de um cliente supera X dias
- **THEN** o sistema marca o cliente como possível recompra na lista/aviso correspondente

### Requirement: Contato manual via WhatsApp

Nas telas de pedidos e clientes o sistema SHALL oferecer link manual de WhatsApp montado a partir do telefone cadastrado, sem envio automático nesta fase.

#### Scenario: Link manual disponível
- **WHEN** um vendedor/administrador clica no ícone de WhatsApp em um cliente
- **THEN** o aplicativo/web WhatsApp abre uma conversa com o número do cliente
