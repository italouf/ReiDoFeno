## Context

Repositório vazio (greenfield): não há código Django ainda. A fonte funcional é `rei-do-feno-implementacao-django.md` na raiz, que define stack obrigatória, modelo de dados inicial (17 entidades), perfis, regras críticas de estoque/pedido/pagamento/fiscal e o roteiro em sprints. O protótipo HTML original é referência visual apenas. Meta: MVP operacional em até 30 dias, com QA e segurança verificados a cada sprint.

## Goals / Non-Goals

**Goals:**

- Base Django executável localmente e em PaaS desde a Fase 0 (login, papéis, `/healthz/`, CI verde).
- Integridade de estoque garantida mesmo sob concorrência (ledger imutável, sem saldo negativo).
- Pagamento e fiscal desacoplados via adapters testáveis com mock/sandbox.
- Webhook de pagamento seguro (assinatura validada, idempotente, evento bruto auditável).
- LGPD operante desde o início: consentimentos, direitos do titular, auditoria, minimização em logs.
- Cobertura ≥ 80% nos apps de domínio; fluxos críticos cobertos por Playwright.

**Non-Goals:**

- Emissão própria de NF-e (SEFAZ), app mobile nativo, WhatsApp automático, multiempresa complexa, contabilidade completa, WMS avançado, marketplace multi-loja.
- SPA complexa; API pública versionada nesta fase.

## Decisions

1. **Monólito Django modular** sobre PostgreSQL gerenciado. *Alternativa considerada*: API + front separado — descartada por prazo (30 dias), equipe enxuta e necessidade de permissões/LGPD centralizadas. Apps: `config` (projeto) + `accounts`, `core`, `catalog`, `customers`, `stock`, `sales`, `costs`, `fiscal`, `privacy`, `analytics`.
2. **Usuário customizado logo na primeira migration**: `accounts.Usuario` (herda de `AbstractUser`) com telefone/perfil. *Por quê*: trocar usuário depois é caro. Grupos "Administrador", "Gestor", "Vendedor", "Cliente" semeados por management command (`seed_groups`) com matriz de permissões declarativa.
3. **Autorização por Groups + permissões customizadas** aplicadas via mixins/decorators nas views; campo `perfil` é apenas conveniência de exibição. Toda view interna exige login; matrizes de acesso viram testes parametrizados.
4. **Modelos conforme doc §6**: Empresa, Unidade, Usuario, Cliente, Categoria, Produto, Estoque, MovimentoEstoque, Despesa, Pedido, ItemPedido, Pagamento, NotaFiscal, Aviso, InteracaoVendedor, ConsentimentoLGPD, SolicitacaoTitular, LogAuditoria. `MovimentoEstoque` e `LogAuditoria` são append-only (sem delete/update pela aplicação).
5. **Estoque como serviço transacional** (`stock.services.registrar_movimento`): `select_for_update` na linha de saldo, validação de saldo ≥ 0 (exceto ajuste autorizado com motivo), transferência cria dois movimentos vinculados; reserva de pedido usa campo `quantidade_bloqueada`; baixa definitiva só na aprovação do pagamento. Constraint de banco impede saldo negativo.
6. **Status de pedido explícito** (`rascunho→aguardando_pagamento→pagamento_pendente→pago→em_separacao→pronto_para_entrega→enviado→concluido|cancelado|falhou`) com transições válidas centralizadas em máquina simples no app `sales`.
7. **Adapters externos atrás de interfaces**: `MercadoPagoClient` (criar preferência, consultar pagamento) e `BlingClient` (criar NFe, consultar status) implementados contra interfaces próprias; em testes usam fakes/sandbox. Credenciais só por env vars.
8. **Webhook idempotente**: tabela `PagamentoWebhookEvento` com payload bruto + hash/id externo únicos; processamento dentro de transação atômica; assinatura `x-signature` do Mercado Pago validada antes de qualquer estado; falhas ficam marcadas para reprocessamento por comando agendado.
9. **Fiscal com fila simples**: sem Celery nesta fase — `NotaFiscal` guarda status/tentativas e um management command agendado (cron da plataforma) varre pedidos pagos elegíveis, envia ao Bling e reprocessa falhas com backoff; fallback manual registra origem "manual".
10. **Front-end server-rendered**: Django Templates + HTMX, Alpine.js pontual, CSS próprio com tokens (cores/tipografia/espaçamento) e componentes (botão, campo, tabela, card, badge de status, alerta, navegação, paginação) seguindo as seções Painel/Produtos/Movimentações/Custos/Clientes/Loja/Vitrine/Avisos. *Alternativa*: Tailwind — descartada para evitar toolchain Node extra; estados vazio/carregando/erro/sucesso/sem-permissão padronizados.
11. **Configuração por ambiente**: settings base + desenvolvimento + produção, lidas de variáveis de ambiente (12-factor); WhiteNoise para estáticos, Gunicorn como servidor, mídia em Cloudflare R2/S3 via django-storages, e-mails via SMTP configurável (Resend/Postmark/SES).
12. **LGPD no domínio**: `ConsentimentoLGPD` versionado por finalidade (marketing sempre separado); `SolicitacaoTitular` com fluxo acesso/correção/exportação/exclusão e prazos; exclusão anonimiza dados pessoais preservando registros fiscais; utilitário central de anonimização reutilizado por métricas.
13. **Auditoria transversal**: helper `registrar_auditoria(usuario, acao, objeto, antes, depois, ip)` invocado nas services de alterações críticas (produtos/preços/estoque/permissões/fiscal/LGPD); nunca editável pelas views.
14. **Qualidade**: pytest + pytest-django + factory-boy + coverage (meta 80%); Playwright para compra completa e login; ruff para lint; Bandit, pip-audit (e Semgrep opcional) por sprint; CI no GitHub Actions rodando lint, testes e segurança em cada PR.
15. **Deploy**: Render (primário) — build `pip install && collectstatic && migrate`, start `gunicorn config.wsgi:application --bind 0.0.0.0:$PORT --workers 2 --timeout 60`, healthcheck `/healthz/`; Sentry + UptimeRobot; Railway mantido como alternativa equivalente.

## Risks / Trade-offs

- [Webhook duplicado/fora de ordem corrompe pedido] → idempotência por evento + payload bruto + transação atômica; testes dedicados de duplicidade.
- [Concorrência de estoque (venda simultânea)] → `select_for_update` + constraint de saldo não negativo + testes de concorrência.
- [Indisponibilidade/falha do Bling ou Mercado Pago] → adapters com timeout curto, retry com backoff, aviso interno e fallback manual (fiscal) / repocessamento (pagamento); pedido nunca se perde por erro externo.
- [Prazo de 30 dias apertado] → ordem de fases do doc §10 e plano de corte do §11 (NF-e manual, recompra manual, WhatsApp manual aceitáveis temporariamente).
- [Exclusão LGPD vs retenção fiscal] → anonimização em vez de delete físico quando houver retenção legal; matriz de retenção documentada em `privacy`.
- [Sem SPA, interatividade limitada] → HTMX cobre filtros/formulários/carrinho; Alpine apenas onde necessário; mobile-first nas telas de cliente/vendedor.
- [Vazamento de segredos/PII em logs] → env vars obrigatórias, filtro de sanitização em logging, revisão Bandit/Semgrep por sprint.

## Migration Plan

Greenfield: cada fase entrega migrations incrementais aplicáveis do zero (`migrate` limpo em CI). Deploy de staging desde a Fase 0; produção só na Fase 4 após checklist. Rollback: redeploy da release anterior (imagens/builds imutáveis) + backups diários do PostgreSQL com restore testado antes do go-live.

## Open Questions

Pré-requisitos externos do checklist §17 que não bloqueiam o design, mas precisam existir até a fase correspondente: conta Bling + credenciais de API, credenciais sandbox do Mercado Pago, domínio próprio, política de privacidade revisada juridicamente e definição de IE/regime fiscal com contador.
