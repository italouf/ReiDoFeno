# Delta: access-control

## Purpose

Define autenticação, autorização por perfil (Administrador, Gestor, Vendedor, Cliente), isolamento de dados entre usuários, trilha de auditoria de ações críticas e healthcheck da aplicação.

## ADDED Requirements

### Requirement: Autenticação de usuários

O sistema SHALL permitir login e logout com credenciais válidas, recuperação de senha por e-mail e MUST rejeitar credenciais inválidas. O acesso a qualquer área interna SHALL exigir usuário autenticado e ativo.

#### Scenario: Login válido
- **WHEN** um usuário submete credenciais corretas
- **THEN** o sistema inicia a sessão e direciona o usuário para sua área conforme o perfil

#### Scenario: Login inválido
- **WHEN** um usuário submete credenciais incorretas
- **THEN** o sistema recusa o acesso e não revela se o e-mail existe

#### Scenario: Recuperação de senha
- **WHEN** um usuário solicita recuperação informando seu e-mail cadastrado
- **THEN** o sistema envia link temporário de redefinição sem expor se o e-mail está ou não cadastrado

### Requirement: Papéis e permissões por perfil

O sistema SHALL organizar a autorização real em grupos e permissões (não apenas em um campo de perfil), com quatro papéis: Administrador (acesso total, incluindo usuários, configurações, integrações e LGPD), Gestor (produtos, estoque, movimentações, custos, despesas, clientes e avisos operacionais), Vendedor (vitrine operacional, criação de pedidos, interações e métricas próprias) e Cliente (loja autenticada, próprios pedidos, perfil e direitos LGPD).

#### Scenario: Gestor acessa estoque mas não usuários
- **WHEN** um gestor autenticado acessa as telas de estoque
- **THEN** o acesso é permitido, e a tentativa de acessar a administração de usuários é negada

#### Scenario: Vendedor não altera estoque nem custos
- **WHEN** um vendedor tenta abrir telas administrativas de estoque, custos ou preços
- **THEN** o sistema nega o acesso e registra a negativa quando relevante

#### Scenario: Cliente não acessa painel interno
- **WHEN** um cliente tenta acessar qualquer área interna de gestão
- **THEN** o sistema nega o acesso

### Requirement: Bloqueio após tentativas repetidas de login

O sistema MUST limitar tentativas de login consecutivas falhas por conta/endereço e SHALL aplicar bloqueio temporário antes de permitir nova tentativa.

#### Scenario: Limite de tentativas excedido
- **WHEN** um usuário erra a senha mais vezes que o limite configurado
- **THEN** novas tentativas são recusadas por um período definido, com mensagem adequada

### Requirement: Isolamento de dados entre clientes e vendedores

O cliente SHALL visualizar somente seus próprios pedidos e dados. O vendedor SHALL visualizar somente suas próprias métricas e os pedidos que criou ou que lhe foram atribuídos. Nenhum perfil não administrativo MUST ver dados de outro titular.

#### Scenario: Cliente não vê pedido alheio
- **WHEN** um cliente tenta acessar diretamente o pedido de outro cliente
- **THEN** o sistema retorna negação de acesso (sem expor existência/conteúdo)

#### Scenario: Métrica de vendedor é individual
- **WHEN** um vendedor abre sua tela de métricas
- **THEN** somente os indicadores das próprias interações e vendas são exibidos

### Requirement: Trilha de auditoria de ações críticas

O sistema SHALL registrar log de auditoria imutável (usuário, ação, objeto, valores antes/depois, IP, data/hora) para toda alteração crítica, incluindo produtos, preços/custos, estoque, permissões, configurações fiscais e ações LGPD. Ações do Administrador DEVEM ser auditadas obrigatoriamente.

#### Scenario: Alteração crítica gera registro
- **WHEN** um gestor altera o preço online de um produto
- **THEN** um registro de auditoria é criado com antes/depois, autor, IP e data

#### Scenario: Log não pode ser apagado pela aplicação
- **WHEN** qualquer perfil tenta excluir ou editar um registro de auditoria pelas telas do sistema
- **THEN** a operação não é oferecida/negada

### Requirement: Healthcheck público

A aplicação SHALL expor endpoint de saúde `/healthz/` respondendo 200 quando a aplicação estiver operacional, sem exigir autenticação e sem expor dados sensíveis.

#### Scenario: Aplicação saudável
- **WHEN** o serviço está em execução e recebe requisição em `/healthz/`
- **THEN** responde HTTP 200

### Requirement: Segurança de sessão e formulários

Em produção, o sistema MUST usar cookies de sessão seguros (Secure/HttpOnly), proteção CSRF em todos os formulários e hash forte de senhas conforme padrão do framework, sem segredos versionados no repositório.

#### Scenario: Formulário sem token CSRF é rejeitado
- **WHEN** uma requisição de escrita é enviada sem o token CSRF válido
- **THEN** o servidor recusa a operação

#### Scenario: Segredos fora do código
- **WHEN** o repositório é inspecionado
- **THEN** nenhuma credencial ou chave secreta aparece em texto puro no código-fonte
