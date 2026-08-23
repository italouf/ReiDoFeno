# Delta: privacy-lgpd

## Purpose

Definir a conformidade com a LGPD: política de privacidade, registro de consentimentos por finalidade, atendimento aos direitos do titular (acesso, correção, exportação, exclusão condicionada à retenção fiscal), anonimização para métricas e minimização de dados pessoais em logs.

## ADDED Requirements

### Requirement: Política de privacidade pública

O sistema SHALL disponibilizar página pública de Política de Privacidade acessível também sem autenticação, descrevendo dados coletados, finalidades, bases legais, retenção e canais de contato do titular.

#### Scenario: Acesso à política
- **WHEN** qualquer visitante abre a página da Política de Privacidade
- **THEN** o conteúdo é exibido integralmente sem exigir login

### Requirement: Registro e revogação de consentimento

Todo consentimento SHALL ser registrado com titular, finalidade específica, versão do texto, aceito/recusado, data/hora e IP. Dados não podem ser usados para marketing sem consentimento separado, e o titular SHALL poder revogar consentimento a qualquer momento.

#### Scenario: Consentimento registrado na coleta
- **WHEN** um cliente aceita uma finalidade no cadastro/checkout
- **THEN** o consentimento fica registrado com finalidade, versão, data e IP

#### Scenario: Revogação interrompe uso
- **WHEN** o titular revoga um consentimento de marketing
- **THEN** novos disparos para aquela finalidade deixam de ocorrer e a revogação fica registrada

### Requirement: Direitos do titular

O titular SHALL solicitar acesso, correção, exportação e exclusão dos próprios dados por fluxo próprio; cada solicitação SHALL ser registrada com tipo, status, prazo e responsável, e a exportação SHALL gerar arquivo legível com os dados pessoais do titular.

#### Scenario: Exportação de dados
- **WHEN** o titular solicita exportação dos seus dados
- **THEN** o sistema gera arquivo contendo seus dados pessoais e registra a solicitação

#### Scenario: Correção pelo titular
- **WHEN** o titular corrige seus dados cadastrais
- **THEN** a alteração é aplicada nos dados dele e registrada em auditoria

### Requirement: Exclusão condicionada à retenção legal

A exclusão de dados SHALL considerar bloqueios legais: registros fiscais (pedidos e notas) podem ter retenção obrigatória. Nesses casos o sistema MUST anonimizar/pseudonimizar os dados pessoais mantendo os registros obrigatórios íntegros.

#### Scenario: Exclusão com retenção fiscal
- **WHEN** o titular solicita exclusão mas possui pedidos/notas sujeitos a retenção legal
- **THEN** os dados pessoais são anonimizados e os registros fiscais permanecem preservados

#### Scenario: Solicitação registrada
- **WHEN** qualquer direito do titular é acionado
- **THEN** uma solicitação com tipo, status e prazo fica registrada para acompanhamento

### Requirement: Minimização e proteção de dados

Logs SHALL evitar dados pessoais desnecessários; acesso a dados pessoais SHALL ser restrito por perfil; backups DEVEM ser criptografados ou com acesso restrito; e métricas/relatórios DEVEM preferir dados anonimizados quando possível.

#### Scenario: Log sem PII sensível
- **WHEN** operações rotineiras são registradas em log
- **THEN** documentos completos e dados de contato não aparecem em texto puro

#### Scenario: Restrição por perfil
- **WHEN** um perfil sem permissão tenta listar dados pessoais de clientes
- **THEN** o acesso é negado e a tentativa pode ser auditada
