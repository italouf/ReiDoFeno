# Delta: fiscal-integration

## Purpose

Definir a integração de emissão de NF-e via ERP externo (Bling) para pedidos pagos com documento válido, incluindo acompanhamento de status, armazenamento de número/chave/link, tratamento de erros com aviso/retry e fallback manual nas primeiras semanas.

## ADDED Requirements

### Requirement: Elegibilidade para emissão fiscal

Somente pedidos pagos cujo cliente possua CPF/CNPJ válido SHALL ser enviados automaticamente para emissão de NF-e. Pedidos fora dessa condição NÃO devem ser enviados e devem ficar sinalizados para correção.

#### Scenario: Pedido pago elegível segue para emissão
- **WHEN** um pedido pago possui documento válido do cliente
- **THEN** o sistema envia o pedido ao Bling e registra a tentativa

#### Scenario: Documento inválido bloqueia envio
- **WHEN** um pedido pago está com CPF/CNPJ ausente ou inválido
- **THEN** o envio fiscal não ocorre e um aviso orienta a correção

### Requirement: Registro dos dados da nota

Para cada emissão o sistema SHALL armazenar número, chave de acesso, status, link/arquivo do XML/DANFE, tentativas e eventuais erros retornados pela API fiscal.

#### Scenario: Nota emitida é registrada
- **WHEN** o Bling confirma a emissão da NF-e
- **THEN** número, chave, status e link ficam disponíveis na tela do pedido

### Requirement: Tratamento de erro com aviso e retry

Falhas na integração fiscal SHALL gerar aviso interno, NÃO devem quebrar/cancelar o pedido e DEVEM permitir reprocessamento posterior (automático ou manual) sem duplicar emissão já confirmada.

#### Scenario: Erro da API gera aviso e permite reprocessar
- **WHEN** a API fiscal retorna erro na criação da NF-e
- **THEN** o pedido permanece "pago", um aviso é criado e a emissão pode ser reprocessada com segurança

#### Scenario: Reprocessamento não duplica nota
- **WHEN** uma emissão já confirmada é alvo de nova tentativa por engano
- **THEN** o sistema detecta a existência da nota e não solicita segunda emissão

### Requirement: Fallback de emissão manual

Nas primeiras semanas o sistema SHALL aceitar registro manual da NF-e (número/chave/link informados por perfil autorizado), marcando a origem como manual para auditoria.

#### Scenario: Registro manual aceito
- **WHEN** um administrador/gestor informa os dados de uma NF-e emitida fora do sistema
- **THEN** a nota fica vinculada ao pedido como emissão manual auditável

### Requirement: Acesso restrito aos dados fiscais

O acesso ao XML/DANFE e aos dados fiscais SHALL ser restrito aos perfis autorizados (administrador/gestor), e as credenciais do provedor fiscal MUST residir exclusivamente em variáveis de ambiente, jamais em logs.

#### Scenario: Cliente não baixa XML
- **WHEN** um cliente tenta acessar arquivos fiscais de outro pedido
- **THEN** o acesso é negado

#### Scenario: Token fiscal fora dos logs
- **WHEN** ocorre erro de integração com a API fiscal
- **THEN** os logs registram a falha sem expor token ou segredo
