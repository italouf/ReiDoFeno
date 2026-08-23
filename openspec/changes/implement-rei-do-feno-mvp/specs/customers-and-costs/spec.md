# Delta: customers-and-costs

## Purpose

Definir a gestão de clientes pessoa física/jurídica com validação de CPF/CNPJ, o registro de interações dos vendedores com clientes e o controle de custos e despesas com impacto no lucro do painel.

## ADDED Requirements

### Requirement: Cadastro de cliente PF/PJ

O sistema SHALL cadastrar clientes pessoa física ou jurídica com nome, documento (CPF ou CNPJ), categoria do cliente, contatos (telefone/WhatsApp, e-mail), endereço de entrega/cobrança e preferência de compra. Documentos inválidos MUST ser rejeitados por validação específica de CPF e de CNPJ.

#### Scenario: Cliente PF com CPF válido
- **WHEN** um cliente é cadastrado como pessoa física com CPF válido
- **THEN** o cadastro é aceito e fica disponível para pedidos

#### Scenario: CPF/CNPJ inválido é rejeitado
- **WHEN** um cadastro é enviado com dígito verificador de CPF ou CNPJ incorreto ou formatação incoerente
- **THEN** o sistema recusa e informa qual documento está inválido

### Requirement: Categoria e histórico do cliente

O sistema SHALL permitir classificar clientes por categoria e SHALL exibir o histórico de pedidos de cada cliente aos perfis autorizados.

#### Scenario: Histórico visível ao perfil correto
- **WHEN** um vendedor/administrador abre a ficha de um cliente
- **THEN** os pedidos anteriores daquele cliente são listados em ordem cronológica

### Requirement: Registro de interações do vendedor

O vendedor SHALL registrar interações com clientes (tipo, observação, pedido relacionado) e o sistema MUST manter esses registros vinculados ao vendedor e à data, servindo de base para suas métricas próprias.

#### Scenario: Interação registrada
- **WHEN** um vendedor registra uma ligação/visita/WhatsApp sobre um cliente
- **THEN** a interação fica registrada com vendedor, cliente, tipo e data

### Requirement: Gestão de custos e despesas

O sistema SHALL permitir registro de custo por produto e de despesas com categoria, tipo, fornecedor, CNPJ do fornecedor, valor e recorrência simples. Custos e despesas DEVEM alimentar o cálculo de lucro estimado exibido no painel.

#### Scenario: Despesa recorrente impacta o painel
- **WHEN** uma despesa mensal recorrente é cadastrada
- **THEN** o painel passa a considerá-la no lucro estimado do período correspondente

#### Scenario: Custo do produto altera margem
- **WHEN** o custo de um produto é atualizado
- **THEN** as margens exibidas no painel passam a refletir o novo custo nas vendas subsequentes
