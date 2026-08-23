# Tasks: implement-rei-do-feno-mvp

Ordem de execução por fases (espelha os sprints do documento técnico). Cada tarefa indica a verificação de conclusão. Não avançar de fase com testes quebrando ou vulnerabilidade alta/crítica sem mitigação.

## 1. Fase 0 — Fundação do projeto

- [x] 1.1 Criar projeto Django `config` e apps `accounts`, `core`, `catalog`, `customers`, `stock`, `sales`, `costs`, `fiscal`, `privacy`, `analytics`; requirements.txt pinado. Verificar: `python manage.py check` sem erros.
- [x] 1.2 Implementar `accounts.Usuario` customizado (AbstractUser + telefone/perfil) definido na primeira migration. Verificar: `migrate` aplica do zero em banco limpo.
- [x] 1.3 Configurar settings por ambiente (desenvolvimento/produção) com variáveis de ambiente, WhiteNoise para estáticos e logging estruturado sem PII. Verificar: `runserver` sobe em dev e `/healthz/` responde 200.
- [x] 1.4 Criar management command `seed_groups` semeando grupos Administrador/Gestor/Vendedor/Cliente com permissões declarativas. Verificar: teste automatizado confirma criação de grupos/permissões.
- [x] 1.5 Implementar login, logout, recuperação de senha e limitador de tentativas falhas. Verificar: testes de login válido, login inválido (sem revelar existência do e-mail) e bloqueio temporário passam.
- [x] 1.6 Criar mixins/decorators de autorização, templates base com navegação (Painel, Produtos, Movimentações, Custos, Clientes, Loja, Vitrine, Avisos) e endpoint `/healthz/`. Verificar: testes parametrizados provam gestor acessa estoque mas não usuários, vendedor não acessa estoque administrativo, cliente não acessa painel interno.
- [x] 1.7 Configurar pytest + pytest-django + factory-boy + coverage, ruff e CI no GitHub Actions (lint, testes, Bandit, pip-audit). Verificar: pipeline verde com relatórios JUnit XML e coverage gerados.
- [x] 1.8 Portão de qualidade Fase 0: consolidar relatórios pytest/coverage/lint/Bandit/pip-audit e checklist de segurança (CSRF nos formulários, hash forte de senha, validadores ativos, SECRET_KEY fora do repositório, cookies seguros). Entregável: base com login, papéis, healthcheck e CI funcionando.

## 2. Fase 1 — Cadastros, estoque, custos e clientes

- [x] 2.1 Criar modelos Unidade, Categoria e Produto (NCM, unidade de medida, custo, preço balcão, preço online, ativo) com migrations e factories. Verificar: migrations aplicam e testes de modelo passam.
- [x] 2.2 Implementar CRUD de produtos, categorias e unidades restrito a administrador/gestor. Verificar: testes de permissão negam vendedor e cliente nas URLs diretas.
- [x] 2.3 Implementar validadores brasileiros de CPF e CNPJ. Verificar: testes cobrem dígitos verificadores válidos/inválidos e formatação.
- [x] 2.4 Criar modelo Cliente (PF/PJ, categoria, contatos, endereço, preferência) e CRUD com documento validado. Verificar: CPF/CNPJ inválido é rejeitado com mensagem específica.
- [x] 2.5 Criar modelos Estoque (por unidade, mínimo, quantidade bloqueada/reservada) e MovimentoEstoque append-only; serviço transacional `registrar_movimento` com `select_for_update` e constraint de saldo não negativo. Verificar: testes de concorrência e de bloqueio de saldo negativo passam.
- [x] 2.6 Criar telas de estoque/movimentações com formulários entrada, saída, ajuste (motivo obrigatório) e transferência entre unidades. Verificar: testes provam entrada aumenta saldo, saída diminui, saída acima do saldo bloqueada, ajuste sem motivo rejeitado, transferência gera dois movimentos vinculados, movimento não deletável.
- [x] 2.7 Criar modelo Despesa (categoria, tipo, fornecedor, CNPJ, valor, recorrência simples) e CRUD. Verificar: teste confirma despesa recorrente refletindo no lucro estimado.
- [x] 2.8 Implementar trilha de auditoria (usuário, ação, objeto, antes/depois, IP, data) nas alterações críticas de produtos/preços/custos/estoque. Verificar: registro imutável criado e sem exclusão via views.
- [x] 2.9 Criar painel inicial interno com total de produtos, estoque baixo, últimas movimentações e despesas recentes. Verificar: painel renderiza dados reais com estados vazio/erro tratados.
- [x] 2.10 Gerar aviso interno automático quando saldo atingir o mínimo da unidade. Verificar: teste cria aviso de estoque baixo ao atingir o limite.
- [x] 2.11 Rodar bateria de testes de permissão em todas as URLs diretas da fase (incluindo cliente tentando produtos internos). Verificar: todos negam conforme matriz de acesso.
- [x] 2.12 Portão de qualidade Fase 1: relatórios pytest, coverage por app, testes de permissão, Bandit, pip-audit, Semgrep + checklist de segurança de CRUD/estoque (XSS em formulários, ORM sem SQL cru, limites de campo, stack trace oculto em produção).

## 3. Fase 2 — Vitrine, pedidos e pagamento

- [x] 3.1 Criar catálogo público e página de produto listando somente ativos com preço online. Verificar: testes provam ativo aparece e inativo some.
- [x] 3.2 Implementar carrinho com adicionar/alterar/remover itens e validação de quantidade/saldo no servidor. Verificar: testes de ajuste de carrinho recalculam totais no servidor.
- [x] 3.3 Criar modelos Pedido, ItemPedido e Pagamento com máquina de status (rascunho→aguardando_pagamento→pagamento_pendente→pago→em_separacao→pronto_para_entrega→enviado→concluido|cancelado|falhou). Verificar: testes cobrem transições válidas/inválidas.
- [x] 3.4 Implementar checkout com identificação (CPF/CNPJ válido), endereço para entrega ou retirada por unidade. Verificar: documento inválido impede pedido; retirada vincula unidade escolhida.
- [x] 3.5 Criar adapter `MercadoPagoClient` (criar preferência/consultar pagamento) com fake/sandbox para testes e criar preferência ao concluir checkout com valores calculados no servidor. Verificar: teste confirma valor correto e redirecionamento ao Checkout Pro.
- [x] 3.6 Implementar endpoint de webhook com validação de assinatura (`x-signature`), persistência do evento bruto e processamento idempotente em transação atômica. Verificar: testes provam evento duplicado não duplica efeito, assinatura inválida é rejeitada.
- [x] 3.7 Implementar baixa definitiva de estoque somente na aprovação do pagamento e liberação de reserva no cancelamento/recusa. Verificar: testes provam aprovação atualiza pedido para pago e baixa estoque; recusa mantém estoque; cancelamento devolve reserva.
- [x] 3.8 Criar telas de pedidos do cliente (apenas próprios) e visão interna vendedor/admin (vendedor vê só criados/atribuídos a ele). Verificar: testes de isolamento entre clientes e de recorte do vendedor passam.
- [x] 3.9 Enviar e-mails transacionais de pedido criado, pagamento aprovado e pedido cancelado via backend SMTP configurável. Verificar: testes com backend locmem confirmam envio sem PII excessiva.
- [x] 3.10 Implementar regra de expiração/cancelamento automático de pedidos com pagamento pendente. Verificar: teste confirma transição após timeout configurado liberando reserva.
- [x] 3.11 Escrever fluxo E2E Playwright da compra completa (produto→carrinho→checkout→pagamento mockado→pedido pago→estoque baixado). Verificar: suíte E2E verde e relatório gerado.
- [x] 3.12 Portão de qualidade Fase 2: relatórios pytest, E2E, idempotência de webhook, coverage, Bandit, pip-audit, segurança do fluxo de pagamento (sem cartão armazenado, valores validados no servidor, IDs não enumeráveis) e checklist de privacidade no checkout.

## 4. Fase 3 — Fiscal, painel, métricas do vendedor e recompra

- [x] 4.1 Criar adapter `BlingClient` (criar NF-e/consultar status) com fake/sandbox e envio automático somente de pedido pago com CPF/CNPJ válido. Verificar: testes provam elegível enviado e documento inválido bloqueado com aviso.
- [x] 4.2 Criar modelo NotaFiscal (número, chave, status, link/XML-DANFE, tentativas, erro) e comando agendado que varre pedidos pagos elegíveis com retry/backoff sem Celery. Verificar: erro da API gera aviso, pedido permanece pago e reprocessamento não duplica nota já emitida.
- [x] 4.3 Implementar fallback de emissão manual (registro manual de número/chave/link por perfil autorizado, origem auditável). Verificar: teste confirma nota manual vinculada ao pedido.
- [x] 4.4 Completar painel com vendas por período, produtos mais vendidos, estoque baixo, despesas, lucro estimado e pedidos aguardando pagamento; cancelados fora das métricas. Verificar: testes de cálculo por período passam.
- [x] 4.5 Implementar InteracaoVendedor (tipo, observação, pedido) e tela de métricas do vendedor (pedidos do dia, vendas, clientes atendidos, pendentes) restrita aos próprios dados. Verificar: teste confirma isolamento entre vendedores.
- [x] 4.6 Criar central de avisos (tipo, severidade, mensagem, origem, lido/não lido) com avisos automáticos de pedido pago sem NF-e e pagamento pendente há muito tempo. Verificar: testes geram cada tipo de aviso no limite configurado.
- [x] 4.7 Implementar heurística simples de recompra (cliente sem compra há X dias configuráveis pelo histórico/ciclo) sinalizada em aviso/lista. Verificar: teste marca cliente elegível após o intervalo.
- [x] 4.8 Adicionar botão/link manual de WhatsApp nas telas de pedidos e clientes montado do telefone cadastrado (sem envio automático). Verificar: teste valida URL gerada.
- [x] 4.9 Portão de qualidade Fase 3: relatório de integração fiscal em sandbox, relatório de painel/métricas, segurança de integrações externas (credenciais só em env vars, token fora dos logs, XML/DANFE restrito), Bandit, pip-audit e checklist LGPD dos dados exibidos no painel.

## 5. Fase 4 — LGPD, hardening, deploy e operação

- [x] 5.1 Publicar páginas de Política de Privacidade e termos acessíveis sem autenticação. Verificar: teste acessa como visitante anônimo.
- [x] 5.2 Implementar ConsentimentoLGPD versionado por finalidade (marketing sempre separado) com registro de data/IP e revogação a qualquer momento. Verificar: testes provam consentimento registrado na coleta e revogação interrompe uso para a finalidade.
- [x] 5.3 Implementar SolicitacaoTitular com fluxo de acesso, correção, exportação e exclusão (status/prazo/responsável registrados) e arquivo de exportação legível dos dados do titular. Verificar: testes cobrem exportação e correção auditadas.
- [x] 5.4 Implementar exclusão condicionada à retenção legal: anonimizar dados pessoais preservando pedidos/notas obrigatórios. Verificar: teste confirma anonimização com integridade fiscal mantida.
- [x] 5.5 Aplicar minimização de PII em logs (filtro de sanitização) e restrição de acesso a dados pessoais por perfil. Verificar: testes confirmam ausência de documentos/contatos em texto puro nos logs e negativa de acesso indevido.
- [ ] 5.6 Endurecer headers (HSTS, X-Content-Type-Options, X-Frame-Options, CSP básica), cookies Secure/HttpOnly e rate limiting; rodar OWASP ZAP baseline. Verificar: scan executado e achados altos/críticos mitigados ou documentados.
- [ ] 5.7 Configurar Sentry, monitoramento de uptime (UptimeRobot) e logs estruturados em produção. Verificar: alerta de erro recebido em teste real e uptime monitorado.
- [ ] 5.8 Configurar backup automático do PostgreSQL com exportação periódica para storage e testar restauração em ambiente de teste. Verificar: relatório de backup/restore com restore bem-sucedido.
- [ ] 5.9 Preparar deploy no Render (build/start commands, variáveis de ambiente mínimas do doc, healthcheck `/healthz/`, domínio próprio, HTTPS automático) com staging antes de produção. Verificar: smoke test em produção com usuário administrativo passa.
- [x] 5.10 Escrever runbook operacional (deploy, rollback, backup/restore, monitoramento) e plano de resposta a incidente em `docs/`. Verificar: documentos revisados e checklist de produção completo marcado.
- [ ] 5.11 Executar validação final E2E em ambiente simulando produção (cadastro→compra→pagamento→NF-e→pedido), fluxo mobile básico e páginas de erro sem detalhes técnicos. Verificar: relatório final de QA, segurança e LGPD consolidados; MVP aceito conforme critérios do doc §17.
