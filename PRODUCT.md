# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Primário: gestão interna da Rei do Feno (dono/gestores) acompanhando vendas, estoque, custo e lucro das duas unidades. Perfis confirmados no sistema: Administrador, Gestor, Vendedor e Cliente.

Públicos secundários (confirmados pelo escopo): equipe de balcão/vendedores (pedidos internos, métricas próprias) e clientes finais (PF ou PJ) comprando na loja online.

## Product Purpose

Sistema web multiusuário "Rei do Feno — Gestão" para a N D Comércio de Alimentos para Animais LTDA (CNPJ 64.092.879/0001-21): painel de vendas/estoque/lucro, catálogo com preço de balcão e online, estoque por unidade com movimentações, cadastro de clientes com CPF/CNPJ validado, custos e despesas, loja online (vitrine, carrinho, checkout) com pagamento Mercado Pago (Pix e cartão) e integração fiscal via Bling.

Fase atual: pré-lançamento — em desenvolvimento, ainda sem uso operacional real.

Sucesso nos próximos meses (definido pelo usuário):
1. Vender online ponta a ponta — pedido pago e NF-e emitida sem intervenção manual.
2. Decisão por número — estoque, custo e lucro confiáveis para decidir compra e recompra.
3. Menos trabalho manual — balcão, fiscal e cobrança rodando com pouca intervenção humana.

## Positioning

Sistema próprio e integrado (vitrine + estoque por unidade + CRM de recompra + inteligência de custo/lucro) construído sob medida para o negócio de alimentos para animais, usando emissor fiscal pronto (Bling) em vez de NF-e caseira. Um e-commerce genérico não teria, de forma verídica, a visão de lucro por produto/unidade amarrando venda de balcão e online deste comércio.

## Operating Context

- Duas unidades físicas: Feira de Santana — BA e Iaçu — BA.
- Todo o produto e a comunicação em português (pt-BR).
- Rotinas agendadas: expiração de pedidos (a cada 15 min, timeout de 240 min), processamento fiscal (30 min), geração de avisos comerciais (diária, 08:00).
- Ciclo padrão de recompra de cliente: 30 dias.
- Deploy em Render (plano starter) com PostgreSQL 15 gerenciado, WhiteNoise para estáticos, Sentry para observabilidade; desenvolvimento local usa SQLite.
- Documento funcional único: `rei-do-feno-implementacao-django.md`; protótipo original `rei-do-feno-gestao.html` serve de referência de negócio, não como código final.

## Capabilities and Constraints

- Autenticação e autorização por perfil: administrador, gestor, vendedor, cliente.
- Produtos: nome, categoria, NCM, unidade de medida, custo, preço balcão, preço online, ativo/inativo.
- Estoque por unidade com mínimo, bloqueio/reserva e movimentações (entrada, saída, ajuste, transferência).
- Clientes PF/PJ com CPF/CNPJ validado, categoria, contato, endereço, histórico de pedidos.
- Custos e despesas com fornecedores e recorrência simples, refletindo no painel de lucro.
- Loja pública: catálogo, preço online, carrinho, checkout, entrega ou retirada.
- Pagamento exclusivamente via Mercado Pago Checkout Pro (Pix e cartão); nunca armazenar cartão; estoque só baixa após pagamento aprovado; webhook para confirmação.
- Fiscal via Bling API (ou similar); não construir emissão de NF-e própria nesta fase.
- Conformidade com a LGPD é requisito (app dedicado `privacy` com política e termos).
- Front-end: Django Templates + HTMX + Alpine.js pontual; monólito Django modular; testes com pytest e Playwright (fluxos críticos de compra e login).
- Fato em aberto (decidido pelo usuário, não inventado): nenhum outro escopo de MVP foi reaberto nesta conversa.

## Brand Commitments

- Nome: "Rei do Feno" (uso consolidado na interface e documentos).
- Razão social: N D Comércio de Alimentos para Animais LTDA — deve aparecer em rodapé/documentos legais.
- Contato oficial de atendimento (informado pelo usuário): WhatsApp **75 98145-7227** (`https://wa.me/5575981457227`) — usar no header/footer da loja.
- Idioma obrigatório: pt-BR em toda a interface.
- Direção registrada no código vigente (`static/css/app.css`): sóbrio, operacional, sem ornamentos; cores com propósito (verde = confirmado, amarelo = atenção, vermelho = bloqueio/falha). Tratado como compromisso vigente até decisão explícita em contrário.

## Evidence on Hand

- Especificação funcional completa: `rei-do-feno-implementacao-django.md`.
- Specs por capacidade em `openspec/specs/` (access-control, business-insights, catalog-and-inventory, customers-and-costs, fiscal-integration, online-store, payment-processing, privacy-lgpd).
- Relatórios de QA por sprint: `docs/relatorios/sprint-0..4-qa.md`, além de `docs/runbook.md` e `docs/incidentes.md`.
- Protótipo HTML original: `rei-do-feno-gestao.html` (referência visual/negócio).
- Ausências que trabalho futuro NÃO deve fabricar: logotipo/marca gráfica, fotos reais de produtos, depoimentos, dados de clientes ou números de vendas reais.

## Product Principles

1. Número confiável antes de tudo — estoque, custo e lucro que a gestão pode acreditar para decidir.
2. Ponta a ponta sem intervenção — pedido pago baixa estoque e emite nota sozinho.
3. Operação simples para quem não é técnico — telas claras, fluxos curtos, pt-BR direto.
4. Conformidade embutida — LGPD e obrigações fiscais fazem parte do fluxo, não são anexo.
5. Duas unidades, uma verdade — Feira de Santana e Iaçu compartilham o mesmo dado oficial.
