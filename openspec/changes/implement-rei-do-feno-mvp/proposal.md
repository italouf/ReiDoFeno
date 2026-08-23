## Why

O "Rei do Feno — Gestão" hoje existe apenas como protótipo local (rei-do-feno-gestao.html) (HTML/Markdown) com dados no dispositivo. O negócio (2 unidades: Feira de Santana e Iaçu — BA) precisa de uma aplicação web multiusuária com banco de dados na nuvem, controle de permissões, gestão de estoque, vitrine de vendas online, pagamentos, integração fiscal e conformidade com a LGPD, com meta de MVP operacional em até 30 dias.

## What Changes

- Criar do zero um monólito Django modular (Python 3.12+, Django 5.x, PostgreSQL) substituindo o protótipo estático, que passa a servir apenas como referência visual/funcional.
- Implementar autenticação e autorização por perfil: Administrador, Gestor, Vendedor e Cliente (Django Groups + permissões customizadas).
- Implementar operação interna: produtos/categorias, estoque por unidade com ledger imutável de movimentações, clientes PF/PJ com validação de CPF/CNPJ, custos e despesas.
- Implementar loja online: catálogo público, carrinho, checkout com entrega ou retirada, pedidos com ciclo de vida completo.
- Integrar pagamento via Mercado Pago Checkout Pro com webhook assinado e idempotente; estoque só baixa após pagamento aprovado.
- Integrar emissão fiscal via Bling (NF-e) para pedidos pagos, com fallback manual nas primeiras semanas.
- Implementar conformidade LGPD: política de privacidade, consentimentos, direitos do titular (acesso, correção, exportação, exclusão) e trilha de auditoria.
- Implementar painel operacional, métricas do vendedor, avisos (estoque baixo, pagamento pendente, pedido sem NF-e) e heurística simples de recompra.
- Preparar deploy em PaaS (Render como alvo primário), CI com testes/QA/segurança, observabilidade (Sentry, logs estruturados, uptime).

## Capabilities

### New Capabilities

- `access-control`: Autenticação (login/logout/recuperação de senha), papéis Administrador/Gestor/Vendedor/Cliente via grupos e permissões, restrições de acesso por perfil, healthcheck `/healthz/` e trilha de auditoria para ações críticas.
- `catalog-and-inventory`: Cadastro de produtos/categorias (NCM, unidade, custo, preço balcão, preço online), estoque por unidade com saldo mínimo e bloqueio/reserva, ledger imutável de movimentações (entrada, saída, ajuste, transferência) e alerta de estoque baixo.
- `customers-and-costs`: Gestão de clientes PF/PJ com validação de CPF/CNPJ, categorias e histórico; registro de interações do vendedor; despesas por categoria, fornecedores e recorrência simples com impacto no lucro do painel.
- `online-store`: Vitrine pública com preço online, carrinho, checkout (identificação, CPF/CNPJ, endereço, entrega ou retirada por unidade), ciclo de vida do pedido (rascunho → pago → concluído), cancelamento com liberação de reserva e e-mails transacionais.
- `payment-processing`: Mercado Pago Checkout Pro (Pix/cartão), criação de preferência, webhook com validação de assinatura e processamento idempotente, armazenamento de evento bruto, reprocessamento em falha e baixa de estoque somente após aprovação.
- `fiscal-integration`: Envio de pedido pago (com documento válido) ao Bling para emissão de NF-e, consulta de status, armazenamento de número/chave/status/link, aviso e retry em erro, e fallback manual.
- `privacy-lgpd`: Política de privacidade, registro de consentimentos por finalidade/versionados, direitos do titular (acesso, correção, exportação, exclusão condicionada à retenção fiscal), anonimização para métricas e minimização de dados em logs.
- `business-insights`: Painel administrativo (vendas, estoque, lucro estimado, pedidos recentes), métricas próprias do vendedor, avisos internos (estoque baixo, pedido pago sem NF-e, pagamento pendente, possível recompra) e link manual de WhatsApp.

### Modified Capabilities

(nenhuma — projeto greenfield)

## Impact

- **Código**: repositório atualmente vazio; toda a base Django será criada na raiz (`config/` + apps `accounts`, `core`, `catalog`, `customers`, `stock`, `sales`, `costs`, `fiscal`, `privacy`, `analytics`).
- **Infraestrutura/dependências**: PostgreSQL gerenciado, WhiteNoise, Gunicorn, storage externo S3/R2 para mídia, SMTP transacional, Sentry, Render/Railway, GitHub Actions.
- **Integrações externas**: Mercado Pago (Checkout Pro + webhook) e Bling API (NF-e); credenciais exclusivamente via variáveis de ambiente.
- **Sistemas existentes**: nenhum sistema em produção é afetado; o protótipo HTML permanece apenas como referência.
