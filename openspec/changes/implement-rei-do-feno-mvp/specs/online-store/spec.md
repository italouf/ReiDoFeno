# Delta: online-store

## Purpose

Definir a vitrine pública, carrinho, checkout com entrega ou retirada e o ciclo de vida completo do pedido, incluindo cancelamento, liberação de reserva e isolamento entre clientes.

## ADDED Requirements

### Requirement: Catálogo público

A vitrine SHALL listar somente produtos ativos com preço online, permitindo navegação por categoria e página individual do produto. Produtos inativos não devem ser acessíveis pela loja.

#### Scenario: Somente ativos na vitrine
- **WHEN** um visitante abre o catálogo público
- **THEN** apenas produtos ativos com preço online são exibidos

### Requirement: Carrinho de compras

O visitante/cliente SHALL poder adicionar itens ao carrinho, alterar quantidades e remover itens; o carrinho MUST validar quantidade disponível na unidade escolhida antes de avançar.

#### Scenario: Ajuste de carrinho
- **WHEN** o cliente altera a quantidade ou remove um item do carrinho
- **THEN** os totais são recalculados no servidor antes do checkout

### Requirement: Checkout com identificação e modalidade

O checkout SHALL coletar identificação do cliente com CPF/CNPJ válido, endereço quando entrega, e a modalidade entrega (com endereço) ou retirada (com unidade escolhida). Valores e disponibilidade MUST ser validados no servidor.

#### Scenario: Checkout exige documento válido
- **WHEN** o cliente conclui o checkout com CPF/CNPJ inválido ou ausente
- **THEN** o pedido não é criado e o erro é sinalizado no formulário

#### Scenario: Retirada por unidade
- **WHEN** o cliente escolhe retirada e seleciona a unidade Iaçu
- **THEN** o pedido é vinculado à unidade de retirada escolhida sem cobrar frete

### Requirement: Ciclo de vida do pedido

Todo pedido SHALL possuir status rastreável (rascunho, aguardando pagamento, pagamento pendente, pago, em separação, pronto para entrega, enviado, concluído, cancelado, falhou) com transições registradas. Pedido não pago NÃO deve reduzir estoque definitivo; a baixa definitiva ocorre somente após pagamento aprovado.

#### Scenario: Pedido aguarda pagamento
- **WHEN** o checkout gera um pedido ainda não pago
- **THEN** ele fica em status de aguardando/pagamento pendente sem baixar estoque definitivo

#### Scenario: Pagamento aprovado move o pedido
- **WHEN** o pagamento do pedido é aprovado
- **THEN** o status passa a "pago" e o estoque correspondente é efetivado/reservado conforme regra de estoque

### Requirement: Cancelamento libera reserva

O cancelamento de pedido (por cliente nos casos permitidos ou por perfis internos) SHALL liberar qualquer reserva/bloqueio de estoque associado e impedir novas transições após concluído/cancelado.

#### Scenario: Cancelamento devolve reserva
- **WHEN** um pedido com estoque reservado é cancelado antes da baixa definitiva
- **THEN** a quantidade reservada volta a ficar disponível na unidade

### Requirement: Isolamento e acompanhamento de pedidos

O cliente SHALL ver somente seus próprios pedidos. O vendedor SHALL acompanhar pedidos que criou ou que lhe foram atribuídos. Perfis internos autorizados SHALL ter visão operacional completa para separação/entrega.

#### Scenario: Vendedor acompanha seus pedidos
- **WHEN** um vendedor abre sua lista de pedidos
- **THEN** somente pedidos criados/atribuídos a ele são exibidos

### Requirement: Notificações por e-mail

O sistema SHALL enviar e-mails transacionais ao menos para criação do pedido, aprovação do pagamento e cancelamento, sem expor dados sensíveis desnecessários no conteúdo.

#### Scenario: E-mail de confirmação
- **WHEN** um pedido é criado no checkout
- **THEN** o cliente recebe e-mail de confirmação com resumo e status do pedido
