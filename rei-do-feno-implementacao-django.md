# Plano Técnico de Implementação — Sistema Rei do Feno com Python/Django

Documento  único para ser salvo como: `rei-do-feno-implementacao-django.md`

\---

## 1\. Contexto do projeto

O sistema “Rei do Feno — Gestão” deve evoluir de um protótipo local, com dados salvos no dispositivo, para uma aplicação web multiusuária, com banco de dados na nuvem, controle de permissões, gestão de estoque, vitrine de vendas online, pagamentos, integração fiscal e conformidade com a LGPD.

Os arquivos originais em HTML e Markdown servem como referência visual e de negócio. Eles não devem ser tratados como código final, mas como especificação funcional inicial.

### Dados de contexto

* Negócio: Rei do Feno
* Empresa: N D Comércio de Alimentos para Animais LTDA
* CNPJ: 64.092.879/0001-21
* Unidades: Feira de Santana — BA e Iaçu — BA
* Meta: MVP operacional em até 30 dias
* Arquitetura recomendada: caminho híbrido

  * Sistema próprio para vitrine, CRM, recompra, estoque e inteligência do negócio
  * Emissor fiscal pronto, como Bling, Tiny, Focus NF-e ou eNotas
  * Não construir emissão de NF-e do zero nesta fase

\---

## 2\. Decisão de arquitetura

### Arquitetura recomendada

Monólito Django modular com PostgreSQL gerenciado.

Motivos:

* Mais simples para começar com Python/Django
* Menos complexidade de infraestrutura
* Fácil evolução para APIs no futuro
* Deploy simples em PaaS
* Melhor controle de permissões, LGPD e testes
* Menos retrabalho para quem já conhece Django

### Diagrama simplificado

&#x20;   Navegador do administrador/gestor/vendedor/cliente
                          |
                          v
                 Aplicação Django
                          |
        +-----------------+-----------------+
        |                 |                 |
        v                 v                 v
    PostgreSQL       Mercado Pago         Bling
                    pagamentos           NF-e
        |
        v
    Storage para mídia
    Cloudflare R2 / S3


\---

## 3\. Stack técnica recomendada

|Camada|Tecnologia|Observação|
|-|-|-|
|Linguagem|Python 3.12+|Versão LTS moderna|
|Framework|Django 5.x|Monólito modular|
|Banco de dados|PostgreSQL 15+|Usar banco gerenciado|
|Frontend interno|Django Templates + HTMX|Simples, produtivo e sem SPA complexa|
|Interatividade leve|Alpine.js|Apenas onde necessário|
|Estilos|CSS próprio ou Tailwind com design system fechado|Evitar visual genérico de IA|
|Testes|pytest, pytest-django, factory-boy, coverage|Base de QA|
|Testes de navegador|Playwright|Fluxos críticos de compra e login|
|Segurança|Bandit, pip-audit, Semgrep, OWASP ZAP baseline|Relatórios por sprint|
|Pagamento|Mercado Pago Checkout Pro + webhook|Não armazenar cartão|
|Nota fiscal|Bling API ou similar|Não reinventar SEFAZ|
|E-mail|SMTP, Resend, Postmark ou Amazon SES|E-mails transacionais|
|Estáticos|WhiteNoise|Produção simples|
|Mídia|Cloudflare R2 ou Amazon S3|Não depender de disco local em produção|
|Deploy|Render ou Railway|Deploy simples e fácil|
|Observabilidade|Sentry + logs estruturados + UptimeRobot|Monitorar erros e disponibilidade|

\---

## 4\. Escopo técnico do MVP

### Entrará no MVP

1. Autenticação e autorização por perfil:

   * Administrador
   * Gestor
   * Vendedor
   * Cliente
2. Painel administrativo:

   * Visão geral de vendas, estoque e lucro
   * Avisos importantes
   * Estoque baixo
   * Pedidos recentes
3. Produtos:

   * Nome
   * Categoria
   * NCM
   * Unidade de medida
   * Custo
   * Preço balcão
   * Preço online
   * Ativo/inativo
4. Estoque por unidade:

   * Feira de Santana
   * Iaçu
   * Quantidade atual
   * Estoque mínimo
   * Bloqueio/quantidade reservada
   * Movimentações de entrada, saída, ajuste e transferência
5. Clientes:

   * Pessoa física ou jurídica
   * CPF ou CNPJ validado
   * Categoria do cliente
   * Contato
   * Endereço
   * Preferência de compra
   * Histórico de pedidos
6. Custos e despesas:

   * Custo por produto
   * Despesas por categoria
   * Fornecedores
   * Recorrência simples
   * Impacto em painel de lucro
7. Vitrine/Loja:

   * Catálogo público
   * Preço online
   * Carrinho
   * Checkout
   * Entrega ou retirada
   * Pedido do cliente
8. Pagamento:

   * Mercado Pago Checkout Pro
   * Pix e cartão via provedor
   * Webhook para confirmação
   * Pedido só baixa estoque após pagamento aprovado
9. Fiscal:

   * Integração com Bling ou similar
   * Envio de pedido pago para emissão de NF-e
   * Armazenamento de número, chave, status e link
   * Fallback manual nas primeiras semanas
10. LGPD:
* Política de privacidade
* Consentimentos
* Exportação de dados do titular
* Solicitação de exclusão
* Trilha de auditoria
* Minimização de dados
11. Vendedor:
* Registro de interações com clientes
* Métricas próprias de atendimento/vendas
* Log de ações relevantes
12. Avisos e recompra:
* Alerta de estoque baixo
* Alerta simples de possível recompra baseado em histórico
* Link manual para WhatsApp em pedidos/clientes

### Não entrará no MVP inicial

* Emissão fiscal própria sem ERP
* Aplicativo mobile nativo
* Integração automática completa com WhatsApp
* Multiempresa complexa
* Contabilidade completa
* WMS avançado
* Marketplace multi-loja

\---

## 5\. Perfis de usuário e permissões

### Modelo de autorização

Usar Django Groups + permissões customizadas. O usuário pode ter um campo `perfil`, mas a autorização real deve ser feita por permissões e grupos.

### Papéis

|Perfil|Permissões principais|Limitações|
|-|-|-|
|Administrador|Acesso total: usuários, configurações, produtos, estoque, financeiro, fiscal, LGPD, integrações e auditoria|Deve usar MFA e ter ações auditadas|
|Gestor|Adicionar, editar e retirar itens do estoque; movimentações, produtos, custos, despesas, clientes e avisos operacionais|Não administra usuários, não altera configurações fiscais críticas e não acessa áreas administrativas sensíveis|
|Vendedor|Acessar vitrine operacional, criar pedidos, registrar interações, consultar métricas próprias e logs de atendimento|Não altera estoque, custos, preços, fiscal ou usuários|
|Cliente|Acessar loja autenticada, ver próprios pedidos, editar perfil permitido, consentimentos e solicitar direitos LGPD|Não vê estoque, custos, outros clientes, métricas internas ou painel administrativo|

### Regras importantes

1. Todo acesso administrativo deve ser autenticado.
2. Vendedor só pode ver métricas próprias ou dados permitidos pelo administrador.
3. Cliente nunca pode ver dados de outro cliente.
4. Gestor não deve acessar funções administrativas sensíveis.
5. Toda alteração crítica deve gerar log de auditoria.
6. Permissões devem ser testadas automaticamente.

\---

## 6\. Modelo de dados inicial

Abaixo está uma proposta de modelos Django. Os nomes podem ser ajustados durante a especificação detalhada.

|Modelo|Objetivo|Campos principais|
|-|-|-|
|Empresa|Dados do emitente|Razão social, CNPJ, IE, endereço, regime fiscal|
|Unidade|Loja/depósito|Nome, cidade, tipo, ativa|
|Usuario|Usuário do sistema|Nome, e-mail, telefone, perfil, ativo, data de criação|
|Cliente|Cliente da loja|Nome, CPF/CNPJ, IE, categoria, contato, endereço, preferência|
|Categoria|Categoria de produto|Nome, descrição, ativa|
|Produto|Produto comercializado|Nome, categoria, NCM, unidade, custo, preço balcão, preço online, ativo|
|Estoque|Saldo por produto/unidade|Produto, unidade, quantidade, mínimo, bloqueio|
|MovimentoEstoque|Ledger de estoque|Produto, unidade, tipo, quantidade, motivo, usuário, data, pedido relacionado|
|Despesa|Custos e despesas|Categoria, tipo, fornecedor, CNPJ, valor, recorrência, observação|
|Pedido|Pedido de venda|Cliente, itens, total, status, pagamento, entrega/retirada, unidade, canal|
|ItemPedido|Item do pedido|Produto, quantidade, preço, subtotal, unidade|
|Pagamento|Pagamento processado|Pedido, provedor, ID externo, status, valor, data, webhook|
|NotaFiscal|NF-e integrada|Pedido, número, chave, status, XML/DANFE, erro, tentativa|
|Aviso|Alertas internos|Tipo, severidade, mensagem, origem, lido, relacionado|
|InteracaoVendedor|Log do vendedor|Vendedor, cliente, tipo, observação, pedido, data|
|ConsentimentoLGPD|Consentimentos|Titular, finalidade, versão, aceito, data, IP|
|SolicitacaoTitular|Pedidos LGPD|Titular, tipo, status, dados, prazo, responsável|
|LogAuditoria|Auditoria|Usuário, ação, objeto, antes/depois, IP, data|

\---

## 7\. Regras de negócio críticas

### Estoque

1. Estoque é sempre por unidade.
2. Toda alteração de estoque deve gerar `MovimentoEstoque`.
3. Movimento de estoque não deve ser apagado; se necessário, fazer estorno.
4. Estoque negativo não é permitido por padrão.
5. Ajuste manual exige motivo obrigatório.
6. Transferência entre unidades gera duas movimentações:

   * saída na origem
   * entrada no destino
7. Produto pode ter quantidade bloqueada/reservada para pedidos em andamento.

### Pedidos

Status sugerido:

&#x20;   rascunho
    aguardando\_pagamento
    pagamento\_pendente
    pago
    em\_separacao
    pronto\_para\_entrega
    enviado
    concluido
    cancelado
    falhou


Regras:

1. Pedido não pago não reduz estoque definitivamente.
2. Pagamento aprovado deve atualizar pedido de forma indepentente.
3. Pedido cancelado deve liberar reserva de estoque, se houver.
4. Pedido pago pode ser enviado para emissão fiscal.
5. Cliente só vê pedidos próprios.
6. Vendedor pode acompanhar pedidos que criou ou que lhe foram atribuídos.

### Pagamento

1. Usar Mercado Pago Checkout Pro.
2. Não armazenar número de cartão.
3. Receber webhook com validação de assinatura/origem.
4. Processar webhook com idempotência.
5. Guardar evento bruto do webhook para auditoria.
6. Se o webhook falhar, permitir reprocessamento manual ou automático.

### Fiscal

1. Não construir emissão NF-e do zero.
2. Integrar com Bling ou similar.
3. Somente pedido pago e com CPF/CNPJ válido deve ir para emissão.
4. Guardar status, número, chave e link da NF-e.
5. Em caso de erro, criar aviso e permitir reprocessamento.
6. Nas primeiras semanas, aceitar emissão manual como fallback.

\---

## 8\. Requisitos de LGPD

### Princípios

1. Minimização de dados
2. Finalidade explícita
3. Consentimento quando aplicável
4. Transparência
5. Segurança
6. Retenção controlada
7. Direitos do titular atendíveis

### Dados prováveis

* Nome
* CPF/CNPJ
* Inscrição Estadual, quando aplicável
* Telefone/WhatsApp
* E-mail
* Endereço de entrega/cobrança
* Histórico de pedidos
* Logs de acesso e auditoria

### Implementação mínima

1. Criar página de Política de Privacidade.
2. Registrar consentimento para finalidades específicas.
3. Não usar dados para marketing sem consentimento separado.
4. Criar fluxo para o titular:

   * acessar dados
   * corrigir dados
   * exportar dados
   * solicitar exclusão
   * revogar consentimento
5. Registrar solicitações LGPD em `SolicitacaoTitular`.
6. Exclusão deve considerar bloqueios legais:

   * dados fiscais podem precisar ser mantidos
   * pedidos e notas podem ter retenção obrigatória
7. Anonimizar ou pseudonimizar dados para métricas quando possível.
8. Logs não devem expor dados pessoais desnecessários.
9. Acesso a dados pessoais deve ser restrito por perfil.
10. Backups devem ser criptografados ou protegidos por acesso restrito.

### Documentos recomendados

* Política de Privacidade
* Registro de bases legais
* Registro de retenção por categoria de dado
* Procedimento de resposta a incidente
* Procedimento de atendimento ao titular

\---

## 9\. Diretrizes de UI/UX para evitar design genérico

O design não deve parecer “template genérico de IA”. Ele precisa ser sóbrio, funcional e coerente com um negócio de atacado de feno.

### Princípios visuais

1. Interface limpa e operacional.
2. Priorizar leitura de dados: estoque, preço, quantidade, status.
3. Nada de dashboards fake ou gráficos decorativos sem dados reais.
4. Usar cores com propósito:

   * verde/sucesso para confirmado
   * amarelo/alerta para atenção
   * vermelho/erro para bloqueio ou falha
5. Tipografia legível.
6. Espaçamento consistente.
7. Formulários claros e com validação visível.
8. Tabelas responsivas e úteis.
9. Mobile-first para cliente e vendedor.
10. Estados visíveis:

    * vazio
    * carregando
    * erro
    * sucesso
    * sem permissão

### O que evitar

* Gradientes excessivos
* Glassmorphism sem necessidade
* Ícones genéricos inconsistentes
* Lorem ipsum
* Cards decorativos sem função
* Neon ou dark mode exagerado sem propósito
* Animações que atrapalhem a operação
* Textos artificiais demais
* Dashboard com métricas inventadas

### Estratégia recomendada

Criar um design system simples:

&#x20;   tokens/
      cores
      tipografia
      espaçamento
      bordas
      sombras

    componentes/
      botão
      campo de formulário
      tabela
      card
      badge de status
      alerta
      navegação
      paginação


Usar o protótipo HTML original como referência de rótulos e seções:

&#x20;   Painel
    Produtos
    Movimentações
    Custos
    Clientes
    Loja
    Vitrine
    Avisos


\---

## 10\. Roteiro técnico por sprints

Cada sprint deve conter:

1. Atividades de código
2. Testes de QA
3. Testes de segurança
4. Relatório de QA
5. Relatório de segurança
6. Entregável

\---

### Sprint 0 — Fundação do projeto

Duração sugerida: 1 a 3 dias

#### Objetivo

Criar a base do projeto Django com autenticação, permissões, estrutura de apps, CI e esqueleto visual.

#### Atividades de código

1. Criar repositório Git privado.
2. Criar projeto Django:

   * `config`
3. Criar apps iniciais:

   * `accounts`
   * `core`
   * `catalog`
   * `customers`
   * `stock`
   * `sales`
   * `costs`
   * `fiscal`
   * `privacy`
   * `analytics`
4. Configurar usuário customizado.
5. Criar login, logout e recuperação de senha.
6. Criar grupos iniciais:

   * Administrador
   * Gestor
   * Vendedor
   * Cliente
7. Criar comando para semear grupos e permissões.
8. Criar templates base com navegação do protótipo.
9. Criar endpoint `/healthz/`.
10. Configurar settings por ambiente:

    * desenvolvimento
    * produção
11. Configurar WhiteNoise para estáticos.
12. Configurar logs estruturados.
13. Configurar pytest, coverage e factories.
14. Configurar CI com GitHub Actions:

    * lint
    * testes
    * segurança básica

#### QA

Testes obrigatórios:

1. Usuário cria conta ou é criado por admin.
2. Login funciona com credenciais válidas.
3. Login falha com credenciais inválidas.
4. Usuário sem permissão não acessa área administrativa.
5. Cliente não acessa painel interno.
6. Vendedor não acessa estoque administrativo.
7. Gestor acessa estoque, mas não acessa usuários.
8. Endpoint `/healthz/` responde 200.
9. Templates base renderizam sem erro.

#### Segurança

1. Testar CSRF em formulários.
2. Garantir senha com hash forte padrão Django.
3. Ativar validadores de senha.
4. Limitar tentativas de login.
5. Garantir que `SECRET\_KEY` não está no repositório.
6. Rodar `pip-audit`.
7. Rodar `bandit`.
8. Verificar se não há credenciais em texto puro.
9. Garantir cookies de sessão seguros em produção.

#### Relatórios obrigatórios

1. Relatório pytest com JUnit XML.
2. Relatório de coverage.
3. Relatório de lint.
4. Relatório Bandit.
5. Relatório pip-audit.
6. Checklist de segurança da Sprint 0.

#### Entregável

Aplicação Django base com login, papéis, healthcheck, CI e esqueleto visual funcionando.

\---

### Sprint 1 — Cadastros, estoque, custos e clientes

Duração sugerida: 4 a 10 dias

#### Objetivo

Permitir operação interna com produtos, estoque por unidade, movimentações, clientes, custos e despesas.

#### Atividades de código

1. Criar modelos:

   * Unidade
   * Categoria
   * Produto
   * Estoque
   * MovimentoEstoque
   * Cliente
   * Despesa
2. Criar CRUD de produtos para admin/gestor.
3. Criar CRUD de categorias.
4. Criar CRUD de unidades.
5. Criar CRUD de clientes com CPF/CNPJ.
6. Criar validadores brasileiros:

   * CPF
   * CNPJ
7. Criar tela de estoque por unidade.
8. Criar tela de movimentações.
9. Criar formulário de movimentação:

   * entrada
   * saída
   * ajuste
   * transferência
10. Exigir motivo para ajuste manual.
11. Criar CRUD simples de despesas.
12. Criar painel inicial com:

    * total de produtos
    * estoque baixo
    * últimas movimentações
    * despesas recentes
13. Criar log de auditoria para alterações críticas.

#### QA

Testes obrigatórios:

1. Criar produto com dados válidos.
2. Rejeitar produto sem nome.
3. Rejeitar produto sem unidade de medida.
4. Criar estoque inicial por unidade.
5. Entrada aumenta saldo.
6. Saída diminui saldo.
7. Saída acima do saldo é bloqueada.
8. Ajuste exige motivo.
9. Transferência reduz origem e aumenta destino.
10. Movimento não pode ser deletado diretamente.
11. CPF inválido é rejeitado.
12. CNPJ inválido é rejeitado.
13. Cliente sem documento é bloqueado quando obrigatório.
14. Gestor acessa estoque.
15. Vendedor não acessa estoque administrativo.
16. Cliente não acessa produtos internos.

#### Segurança

1. Testar autorização por perfil em todas as views.
2. Validar entrada contra XSS em formulários.
3. Confirmar uso de ORM para evitar SQL injection.
4. Testar permissão em URLs diretas.
5. Validar tamanho máximo de campos.
6. Auditar alterações de estoque.
7. Garantir que erros não exponham stack trace em produção.
8. Revisar permissões de admin/gestor.
9. Rodar análise estática com Bandit e Semgrep.

#### Relatórios obrigatórios

1. Relatório pytest.
2. Coverage por app.
3. Relatório de testes de permissão.
4. Relatório Bandit.
5. Relatório pip-audit.
6. Relatório Semgrep.
7. Checklist de segurança de CRUD e estoque.

#### Entregável

Sistema utilizável internamente para produtos, estoque, movimentações, clientes e custos.

\---

### Sprint 2 — Vitrine, pedidos e pagamento

Duração sugerida: 11 a 20 dias

#### Objetivo

Colocar a loja para vender com carrinho, checkout, pagamento online e atualização de estoque após confirmação.

#### Atividades de código

1. Criar catálogo público com produtos ativos.
2. Criar página de produto.
3. Criar carrinho de compras.
4. Criar checkout com:

   * identificação do cliente
   * CPF/CNPJ
   * endereço
   * entrega ou retirada
   * unidade de retirada
5. Criar modelos:

   * Pedido
   * ItemPedido
   * Pagamento
6. Criar integração com Mercado Pago:

   * criação de preferência
   * redirect para checkout
   * webhook
7. Criar processamento idempotente de webhook.
8. Atualizar pedido após pagamento aprovado.
9. Baixar estoque somente após pagamento aprovado.
10. Criar tela de pedidos para cliente.
11. Criar tela de pedidos para vendedor/admin.
12. Enviar e-mails transacionais:

    * pedido criado
    * pagamento aprovado
    * pedido cancelado
13. Criar estados de pedido.
14. Criar regra de cancelamento por pagamento pendente.

#### QA

Testes obrigatórios:

1. Produto ativo aparece na vitrine.
2. Produto inativo não aparece.
3. Adicionar produto ao carrinho.
4. Alterar quantidade no carrinho.
5. Remover item do carrinho.
6. Checkout exige CPF/CNPJ válido.
7. Checkout cria pedido com itens corretos.
8. Pedido não pago não reduz estoque definitivo.
9. Webhook aprovado atualiza pedido para pago.
10. Webhook duplicado não duplica processamento.
11. Webhook rejeitado não baixa estoque.
12. Pagamento pendente mantém pedido aguardando.
13. Pedido pago pode ser visto pelo cliente.
14. Cliente não vê pedido de outro cliente.
15. Vendedor vê pedidos permitidos.
16. Cancelamento libera estoque reservado.

#### Segurança

1. Validar assinatura/autenticidade do webhook do Mercado Pago.
2. Garantir CSRF no checkout.
3. Não armazenar cartão ou credenciais de pagamento.
4. Limitar tentativas de checkout.
5. Validar valores no servidor, nunca apenas no cliente.
6. Testar sessão de cliente isolada.
7. Evitar exposição de PII em logs.
8. Testar IDs de pedido não enumeráveis quando necessário.
9. Validar autorização nas páginas de pedido.
10. Revisar secrets do Mercado Pago.

#### Relatórios obrigatórios

1. Relatório pytest.
2. Relatório de testes E2E com Playwright.
3. Relatório de idempotência de webhook.
4. Relatório de coverage.
5. Relatório Bandit.
6. Relatório pip-audit.
7. Relatório de segurança do fluxo de pagamento.
8. Checklist de privacidade no checkout.

#### Entregável

Venda online completa: produto → carrinho → checkout → pagamento → pedido → estoque atualizado.

\---

### Sprint 3 — Fiscal, painel, métricas do vendedor e recompra

Duração sugerida: 21 a 26 dias

#### Objetivo

Integrar emissão fiscal, gerar painel operacional, logs de vendedor e alertas de recompra/estoque.

#### Atividades de código

1. Criar app de integração fiscal.
2. Configurar credenciais do Bling ou similar.
3. Enviar pedido pago para criação de NF-e.
4. Consultar status da NF-e.
5. Salvar número, chave, status e link.
6. Criar fila simples ou tarefa agendada para reprocessamento.
7. Criar fallback para emissão manual.
8. Criar painel com:

   * vendas por período
   * produtos mais vendidos
   * estoque baixo
   * despesas
   * lucro estimado
   * pedidos aguardando pagamento
9. Criar logs do vendedor:

   * pedidos criados
   * interações com clientes
   * status de pedidos
10. Criar tela de métricas do vendedor:

    * pedidos do dia
    * vendas do vendedor
    * clientes atendidos
    * pedidos pendentes
11. Criar avisos:

    * estoque baixo
    * pedido pago sem NF-e
    * pagamento pendente há muito tempo
    * possível recompra
12. Criar heurística simples de recompra:

    * cliente não compra há X dias
    * produto costuma ter ciclo de reposição
13. Criar botão manual de WhatsApp.

#### QA

Testes obrigatórios:

1. Pedido pago pode ser enviado para NF-e.
2. Pedido sem CPF/CNPJ válido não é enviado para NF-e.
3. Erro na API fiscal gera aviso e permite reprocessar.
4. Painel calcula vendas corretamente.
5. Vendedor vê apenas métricas permitidas.
6. Admin vê métricas gerais.
7. Estoque baixo gera aviso.
8. Possível recompra gera aviso.
9. Log do vendedor registra ação.
10. Link manual de WhatsApp abre corretamente.
11. Pedido cancelado não entra nas métricas de venda concluída.

#### Segurança

1. Credenciais fiscais somente em variáveis de ambiente.
2. Nenhum token pode aparecer em logs.
3. Acesso a XML/DANFE somente para perfis permitidos.
4. Testar permissão do painel por perfil.
5. Garantir que métricas do vendedor não exponham dados de outros vendedores.
6. Revisar exposição de CPF/CNPJ em telas.
7. Validar respostas da API fiscal.
8. Testar retry seguro em falha de integração.

#### Relatórios obrigatórios

1. Relatório pytest.
2. Relatório de integração fiscal em ambiente sandbox.
3. Relatório de painel e métricas.
4. Relatório de segurança de integrações externas.
5. Relatório Bandit.
6. Relatório pip-audit.
7. Checklist LGPD para dados exibidos em painel.

#### Entregável

Pedido pago conectado à emissão fiscal externa, painel operacional e inteligência simples de recompra.

\---

### Sprint 4 — LGPD, hardening, deploy e operação

Duração sugerida: 27 a 30 dias

#### Objetivo

Preparar produção com privacidade, backups, monitoramento, segurança e deploy definitivo.

#### Atividades de código

1. Criar página de Política de Privacidade.
2. Criar página de termos e consentimento.
3. Criar gestão de consentimentos.
4. Criar fluxo de solicitação do titular:

   * acesso
   * correção
   * exportação
   * exclusão
5. Criar exportação de dados do cliente.
6. Criar rotina de anonimização quando aplicável.
7. Configurar backup automático do PostgreSQL.
8. Configurar Sentry.
9. Configurar monitoramento de uptime.
10. Configurar logs estruturados em produção.
11. Revisar headers de segurança.
12. Revisar permissões finais.
13. Preparar deploy em produção.
14. Criar runbook operacional.
15. Criar plano de resposta a incidente.

#### QA

Testes obrigatórios:

1. Usuário solicita exportação de dados.
2. Usuário solicita exclusão.
3. Exclusão respeita retenção fiscal.
4. Consentimento é registrado com data e finalidade.
5. Backup pode ser restaurado em ambiente de teste.
6. Fluxo completo funciona em produção simulada:

   * cadastro
   * compra
   * pagamento
   * NF-e
   * pedido
7. Login, logout e recuperação funcionam.
8. Fluxo mobile básico funciona.
9. Formulários exibem erros corretamente.
10. Páginas de erro não expõem detalhes técnicos.

#### Segurança

1. Rodar OWASP ZAP baseline scan.
2. Validar headers:

   * HSTS
   * X-Content-Type-Options
   * X-Frame-Options
   * CSP básica
3. Validar cookies Secure e HttpOnly.
4. Validar CSRF.
5. Validar rate limiting.
6. Revisar dependências com pip-audit.
7. Revisar secrets.
8. Revisar permissões por perfil.
9. Verificar se logs não expõem dados sensíveis.
10. Testar restauração de backup com segurança.

#### Relatórios obrigatórios

1. Relatório final de QA.
2. Relatório final de segurança.
3. Relatório OWASP ZAP baseline.
4. Relatório de backup e restore.
5. Relatório de privacidade/LGPD.
6. Checklist de produção.
7. Runbook de operação.

#### Entregável

Sistema pronto para operação inicial em produção com controles mínimos de segurança, privacidade e observabilidade.

\---

## 11\. Prioridades se o prazo apertar

Se houver atraso, cortar nesta ordem, de baixo para cima:

1. Manter obrigatório:

   * Estoque e custos funcionando
   * Cadastro de cliente com CPF/CNPJ
   * Pedido e pagamento
2. Aceitável temporariamente:

   * NF-e manual no Bling
   * Recompras manuais
   * WhatsApp manual
   * Painel mais simples
3. Pode ficar para depois:

   * Alerta automático de recompra
   * Disparo automático de WhatsApp
   * Relatórios avançados
   * Métricas complexas do vendedor

\---

## 12\. Deploy simples e fácil

### Recomendação principal: Render

O Render é recomendado pela simplicidade para Django com PostgreSQL gerenciado, HTTPS automático e deploy via GitHub.

### Componentes

|Componente|Serviço|
|-|-|
|Aplicação Django|Render Web Service|
|Banco de dados|Render PostgreSQL|
|Mídia/imagens|Cloudflare R2 ou Amazon S3|
|E-mail|Resend, Postmark ou SMTP externo|
|Monitoramento|Sentry + UptimeRobot|
|Backup|Backup do Render + exportação periódica para storage|

### Passos de deploy

1. Subir o código para GitHub.
2. Criar banco PostgreSQL gerenciado no Render.
3. Criar Web Service apontando para o repositório.
4. Configurar build command.
5. Configurar start command.
6. Configurar variáveis de ambiente.
7. Configurar healthcheck em `/healthz/`.
8. Configurar domínio próprio.
9. Ativar HTTPS automático.
10. Testar produção com usuário administrativo.

### Build command sugerido

&#x20;   pip install --upgrade pip
    pip install -r requirements.txt
    python manage.py collectstatic --noinput
    python manage.py migrate


### Start command sugerido

&#x20;   gunicorn config.wsgi:application --bind 0.0.0.0:$PORT --workers 2 --timeout 60


### Variáveis de ambiente mínimas

&#x20;   SECRET\_KEY
    DEBUG=False
    ALLOWED\_HOSTS
    CSRF\_TRUSTED\_ORIGINS
    DATABASE\_URL
    MERCADOPAGO\_ACCESS\_TOKEN
    BLING\_API\_TOKEN
    EMAIL\_BACKEND
    EMAIL\_HOST
    EMAIL\_PORT
    EMAIL\_HOST\_USER
    EMAIL\_HOST\_PASSWORD
    DEFAULT\_FROM\_EMAIL
    STORAGE\_BACKEND
    R2\_ACCESS\_KEY\_ID ou AWS\_ACCESS\_KEY\_ID
    R2\_SECRET\_ACCESS\_KEY ou AWS\_SECRET\_ACCESS\_KEY
    STORAGE\_BUCKET\_NAME
    SENTRY\_DSN


### Recomendações de produção

1. Nunca usar `DEBUG=True`.
2. Nunca commitar `.env`.
3. Usar HTTPS sempre.
4. Usar WhiteNoise para estáticos.
5. Usar storage externo para mídia.
6. Ativar backups automáticos do banco.
7. Testar restauração de backup.
8. Criar alerta de erro no Sentry.
9. Criar alerta de downtime no UptimeRobot.
10. Manter dependências atualizadas.

### Alternativa: Railway

Se quiser ainda menos configuração, o Railway também pode hospedar Django + PostgreSQL. A lógica é semelhante:

* serviço web Django
* banco PostgreSQL gerenciado
* variáveis de ambiente
* domínio e HTTPS
* deploy via GitHub

A escolha entre Render e Railway deve considerar conforto da equipe, custo e facilidade de backup.

\---

## 13\. Abordagem SDD

SDD aqui pode ser entendido como Software Design Document e também como Spec-Driven Development.

A regra é: nenhuma funcionalidade deve ser implementada sem uma especificação mínima.

### Documentos recomendados

Criar dentro do repositório:

&#x20;   docs/
      arquitetura.md
      modelo-de-dados.md
      permissoes.md
      api-fiscal.md
      pagamento.md
      lgpd.md
      plano-de-testes.md
      plano-de-seguranca.md
      runbook.md
      design-system.md


### Conteúdo mínimo de cada especificação

1. Objetivo
2. Histórias de usuário
3. Critérios de aceite
4. Modelos envolvidos
5. Views/telas envolvidas
6. Permissões necessárias
7. Regras de negócio
8. Testes necessários
9. Riscos de segurança
10. Pontos de LGPD

\---

## 14\. Loop-Engineering

O projeto deve ser executado em ciclos curtos de feedback.

### Loop recomendado

&#x20;   Especificar
      |
      v
    Escrever testes
      |
      v
    Implementar código mínimo
      |
      v
    Rodar QA
      |
      v
    Rodar segurança
      |
      v
    Revisar relatório
      |
      v
    Corrigir
      |
      v
    Atualizar documentação
      |
      v
    Deploy em staging
      |
      v
    Validar com usuário real
      |
      v
    Ajustar próxima sprint


### Regras do loop

1. Não avançar se testes quebrarem.
2. Não avançar com vulnerabilidade alta ou crítica sem mitigação.
3. Toda task deve ter teste.
4. Toda integração externa deve ter simulação de falha.
5. Toda tela deve ter estado vazio, erro e sucesso.
6. Toda mudança crítica deve atualizar documentação.

\---

## 15\. Prompt final para implementação da solução

Use o prompt abaixo no seu ambiente de desenvolvimento com IA, preferencialmente dentro de um harness como o Opencode.

\---

### Prompt

Você é um engenheiro de software sênior especialista em Python, Django, PostgreSQL, segurança, LGPD, arquitetura de monólitos, testes automatizados e integração com APIs externas.

Seu objetivo é implementar o sistema “Rei do Feno — Gestão e Vitrine”, um sistema web para gestão de estoque, custos, clientes, vendas online, pagamento, emissão fiscal externa e conformidade com a LGPD.

Contexto do negócio:

* Empresa: Rei do Feno
* Segmento: comércio de alimentos para animais
* Unidades: Feira de Santana e Iaçu, Bahia
* O sistema deve ter vitrine online com preço de atacado/varejo
* O estoque deve ser separado por unidade
* O sistema deve aceitar clientes com CPF ou CNPJ
* O pagamento deve ser processado por Mercado Pago
* A nota fiscal deve ser integrada via Bling ou API fiscal equivalente
* Não implementar emissão de NF-e do zero
* O protótipo HTML original é apenas referência visual

Stack obrigatória:

* Python 3.12+
* Django 5.x
* PostgreSQL
* Django Templates
* HTMX para interatividade leve
* Alpine.js somente quando necessário
* CSS próprio ou Tailwind com design system controlado
* pytest
* factory-boy
* coverage
* WhiteNoise
* Gunicorn
* Sentry
* Variáveis de ambiente para secrets

Arquitetura:

* Monólito Django modular
* Apps sugeridos:

  * accounts
  * core
  * catalog
  * customers
  * stock
  * sales
  * costs
  * fiscal
  * privacy
  * analytics
* Banco PostgreSQL gerenciado
* Deploy simples em Render ou Railway
* Mídia em storage externo S3/R2
* Estáticos com WhiteNoise

Perfis de usuário obrigatórios:

1. Administrador

   * acesso total
   * usuários e configurações
   * auditoria
   * integrações
   * LGPD
2. Gestor

   * adiciona e retira itens do estoque
   * movimenta estoque
   * gerencia produtos, custos e despesas operacionais
   * não administra usuários nem configurações críticas
3. Vendedor

   * pode usar vitrine operacional
   * criar pedidos
   * registrar interações
   * acompanhar métricas próprias por meio de logs e indicadores permitidos
   * não altera estoque, custos ou fiscal
4. Cliente

   * acessa loja autenticada
   * vê próprios pedidos
   * edita perfil permitido
   * solicita direitos LGPD
   * não acessa áreas internas

Regras críticas:

* Estoque por unidade
* Toda movimentação de estoque deve gerar registro imutável de movimento
* Estoque negativo não permitido por padrão
* Ajuste manual exige motivo
* Pedido não pago não reduz estoque definitivo
* Baixa de estoque somente após pagamento aprovado
* Webhook de pagamento deve ser idempotente e validado
* Não armazenar dados de cartão
* NF-e somente após pedido pago e CPF/CNPJ válido
* Logs não podem expor dados pessoais desnecessários
* Cliente não pode ver dados de outro cliente
* Vendedor não pode ver métricas de outro vendedor sem permissão

LGPD obrigatória:

* Política de privacidade
* Registro de consentimento
* Minimização de dados
* Fluxo de acesso, correção, exportação e exclusão
* Retenção para dados fiscais quando necessário
* Trilha de auditoria
* Proteção por perfil
* Não usar dados para marketing sem consentimento específico

UI/UX:

* Não gerar design genérico com aparência de IA
* Interface sóbria, operacional e profissional
* Usar dados reais, sem conteúdo falso
* Criar estados de vazio, carregando, erro e sucesso
* Mobile-first para cliente e vendedor
* Tabelas, formulários e badges de status bem resolvidos
* Sem gradientes excessivos, glassmorphism desnecessário ou cards decorativos
* Navegação baseada nas seções:

  * Painel
  * Produtos
  * Movimentações
  * Custos
  * Clientes
  * Loja
  * Vitrine
  * Avisos

Metodologia:

Use Spec-Driven Development e Loop-Engineering.

Antes de implementar qualquer funcionalidade:

1. Crie ou atualize o documento de especificação em docs/
2. Defina critérios de aceite
3. Escreva testes automatizados
4. Implemente o código mínimo
5. Rode testes
6. Gere relatório de QA
7. Gere relatório de segurança
8. Corrija falhas antes de prosseguir

Para cada task ou sprint, entregue obrigatoriamente:

1. Resumo do que foi implementado
2. Arquivos criados ou alterados
3. Testes adicionados
4. Resultado dos testes
5. Relatório de QA
6. Relatório de segurança
7. Vulnerabilidades encontradas
8. Correções aplicadas
9. Pendências
10. Próximo passo recomendado

Requisitos de segurança por task:

* Testar autorização por perfil
* Validar entrada de dados
* Proteger formulários com CSRF
* Não expor stack trace em produção
* Não gravar secrets em código
* Não expor PII em logs
* Validar webhooks
* Testar idempotência
* Revisar dependências
* Usar ORM para evitar SQL injection
* Proteger contra XSS em templates

Requisitos de QA por task:

* Testes unitários
* Testes de integração
* Testes de permissão
* Testes de regra de negócio
* Testes de fluxo crítico
* Cobertura mínima recomendada: 80%
* Fluxos críticos com Playwright quando aplicável

Ordem de implementação recomendada:

1. Fundação do projeto
2. Autenticação e papéis
3. Produtos, estoque, clientes e custos
4. Vitrine, pedidos e pagamento
5. Fiscal, painel e métricas
6. LGPD, hardening e deploy

Restrições:

* Não usar SPA complexa sem necessidade
* Não implementar NF-e do zero
* Não armazenar cartão
* Não usar bibliotecas sem justificativa técnica
* Não criar telas com conteúdo fake
* Não ignorar testes de segurança
* Não avançar com vulnerabilidade alta ou crítica sem mitigação

Deploy:

Prepare o projeto para deploy simples em Render ou Railway.

Entregue também:

* requirements.txt
* configurações de produção
* healthcheck
* instruções de variáveis de ambiente
* comando de build
* comando de start
* checklist de produção
* runbook básico

Se faltar informação, faça perguntas objetivas antes de implementar.

Comece criando o documento docs/sdd.md com a especificação inicial do sistema e a proposta de modelo de dados.

\---

## 16\. Seção separada — Skills recomendadas para o Harness do Opencode

Antes de iniciar o projeto, recomenda-se criar skills reutilizáveis no Harness do Opencode. Elas ajudam a padronizar implementação, QA, segurança e design.

### Skill 1 — SDD Spec Writer

Objetivo:
Criar especificações funcionais e técnicas antes da implementação.

Entrada:

* Requisito de negócio
* Perfil de usuário
* Fluxo desejado
* Regras e restrições

Saída:

* Documento em docs/
* Histórias de usuário
* Critérios de aceite
* Modelos envolvidos
* Riscos de segurança
* Requisitos LGPD

Critério de pronto:
A especificação deve permitir implementação sem ambiguidade.

\---

### Skill 2 — Django Project Bootstrap

Objetivo:
Criar a base Django com configurações seguras e ambiente de testes.

Entrada:

* Nome do projeto
* Apps desejados
* Ambiente de deploy
* Banco de dados

Saída:

* Projeto Django
* Settings separados por ambiente
* pytest configurado
* lint configurado
* healthcheck
* estrutura de apps

Critério de pronto:
O projeto deve rodar localmente e passar em testes básicos.

\---

### Skill 3 — Auth RBAC

Objetivo:
Implementar autenticação e autorização por papéis.

Entrada:

* Papéis: Administrador, Gestor, Vendedor, Cliente
* Permissões por papel

Saída:

* Usuário customizado
* Grupos
* Permissões
* Telas de login/logout
* Testes de acesso

Critério de pronto:
Usuários só acessam áreas permitidas, com testes passando.

\---

### Skill 4 — Data Model Builder

Objetivo:
Criar modelos Django, migrations e factories.

Entrada:

* Especificação SDD
* Entidades
* Relacionamentos
* Regras de validação

Saída:

* Models
* Migrations
* Admin básico
* Factories
* Testes de modelo

Critério de pronto:
Migrations aplicam sem erro e testes de modelo passam.

\---

### Skill 5 — Stock Ledger Guard

Objetivo:
Garantir integridade do estoque.

Entrada:

* Regras de estoque por unidade
* Tipos de movimentação
* Permissões de ajuste

Saída:

* Movimentações imutáveis
* Validação de saldo
* Motivo obrigatório
* Testes de concorrência
* Testes de permissão

Critério de pronto:
Nenhuma operação inválida de estoque passa sem erro e teste.

\---

### Skill 6 — Storefront Checkout

Objetivo:
Implementar vitrine, carrinho e checkout.

Entrada:

* Produtos ativos
* Preço online
* Regras de CPF/CNPJ
* Entrega/retirada

Saída:

* Catálogo
* Carrinho
* Checkout
* Pedidos
* Validações
* Testes E2E

Critério de pronto:
Pedido é criado corretamente e validado por perfil.

\---

### Skill 7 — Payment Webhook

Objetivo:
Integrar pagamento com webhook seguro.

Entrada:

* Provider: Mercado Pago
* Evento de pagamento
* Status possíveis

Saída:

* Criação de preferência
* Webhook
* Idempotência
* Atualização de pedido
* Testes de duplicate webhook

Critério de pronto:
Pagamento aprovado atualiza pedido uma única vez.

\---

### Skill 8 — Fiscal ERP Connector

Objetivo:
Integrar NF-e via Bling ou similar.

Entrada:

* Pedido pago
* Cliente com documento fiscal válido
* Credenciais da API

Saída:

* Envio de NF-e
* Consulta de status
* Registro de erro
* Retry
* Testes com sandbox/mock

Critério de pronto:
Falhas fiscais não quebram o pedido e permitem correção.

\---

### Skill 9 — LGPD Privacy Kit

Objetivo:
Implementar privacidade e direitos do titular.

Entrada:

* Tipos de dados pessoais
* Finalidades
* Bases legais
* Retenção

Saída:

* Política de privacidade
* Consentimentos
* Solicitações de titular
* Exportação
* Exclusão condicionada
* Logs de auditoria

Critério de pronto:
Fluxos LGPD funcionam e respeitam retenção fiscal.

\---

### Skill 10 — UI Design System Anti-Slop

Objetivo:
Evitar design genérico com aparência de IA.

Entrada:

* Identidade do negócio
* Protótipo original
* Requisitos de usabilidade
* Perfis de usuário

Saída:

* Tokens de cor, tipografia e espaçamento
* Componentes reutilizáveis
* Estados de tela
* Padrões de formulário e tabela
* Checklist visual

Critério de pronto:
Interface sóbria, real, consistente e sem elementos decorativos desnecessários.

\---

### Skill 11 — QA Report Generator

Objetivo:
Gerar relatório de qualidade após cada task.

Entrada:

* Testes executados
* Coverage
* Resultados de lint
* Resultados de E2E

Saída:

* Resumo executivo
* Testes passando/falhando
* Cobertura
* Pontos críticos
* Recomendações

Critério de pronto:
Relatório claro e acionável para decisão de release.

\---

### Skill 12 — Security Audit

Objetivo:
Executar verificações de segurança.

Entrada:

* Código
* Dependências
* Rotas
* Formulários
* Integrações externas

Saída:

* Relatório Bandit
* Relatório pip-audit
* Relatório Semgrep
* OWASP ZAP baseline
* Checklist manual
* Classificação por severidade

Critério de pronto:
Nenhuma vulnerabilidade alta ou crítica fica aberta sem mitigação documentada.

\---

### Skill 13 — Deploy Runbook

Objetivo:
Padronizar deploy e operação.

Entrada:

* Plataforma escolhida
* Variáveis de ambiente
* Comandos de build/start
* Backup
* Monitoramento

Saída:

* Passo a passo de deploy
* Checklist de produção
* Rollback
* Backup/restore
* Monitoramento

Critério de pronto:
Qualquer pessoa técnica consegue subir ou recuperar o ambiente seguindo o runbook.

\---

### Skill 14 — Loop Review

Objetivo:
Fechar o ciclo de engenharia com feedback.

Entrada:

* Relatório QA
* Relatório segurança
* Mudanças implementadas
* Pendências

Saída:

* Status da sprint
* Riscos
* Dívidas técnicas
* Melhorias para próxima iteração
* Decisão de release

Critério de pronto:
Decisão clara entre liberar, corrigir ou bloquear.

\---

## 17\. Checklist final antes de começar o projeto

Antes da Sprint 0, validar:

1. Contador consultado sobre Inscrição Estadual e NF-e.
2. Certificado digital e-CNPJ A1 disponível ou providenciado.
3. Conta no Bling ou API fiscal equivalente definida.
4. Conta Mercado Pago criada e credenciais de teste disponíveis.
5. Domínio definido.
6. Repositório Git privado criado.
7. Ambiente de produção escolhido: Render ou Railway.
8. Banco PostgreSQL gerenciado escolhido.
9. Storage externo escolhido para mídia.
10. Sentry e monitoramento configurados.
11. Design system mínimo aprovado.
12. Papéis e permissões validados com o dono do negócio.
13. Política de privacidade revisada juridicamente, se possível.
14. Plano de backup validado.
15. Critério de aceite do MVP fechado.

\---

## 18\. Resumo executivo

Para implementar o sistema Rei do Feno com Python/Django:

* Use monólito Django modular.
* Use PostgreSQL gerenciado.
* Deploy simples em Render ou Railway.
* Integre pagamento com Mercado Pago.
* Integ NF-e com Bling ou similar.
* Implemente papéis: Administrador, Gestor, Vendedor e Cliente.
* Garanta LGPD desde o início.
* Faça cada sprint com QA e relatório de segurança.
* Use SDD e Loop-Engineering para reduzir retrabalho.
* Evite design genérico: interface sóbria, real e funcional.
* Crie skills no Opencode antes de iniciar para padronizar execução.

