# Visual SDD — Rei do Feno · Camada Visual

Spec-Driven Design · v1.0 · Ciclo 1
Decisões confirmadas pelo usuário: **evoluir o sistema Django real** (templates existentes com `{% url %}` e contexto verdadeiro) e **refinar a identidade vigente** (verde escuro sobre areia quente).

---

## 1. Resumo do produto

Sistema web de gestão e vitrine online da Rei do Feno (N D Comércio de Alimentos para Animais LTDA), duas unidades — Feira de Santana e Iaçu (BA). Duas faces:

- **Gestão interna** (Operate): painel, produtos, estoque por unidade, movimentações, custos, clientes, pedidos, avisos fiscais/comerciais. Usuário primário: dono/gestor não técnico.
- **Loja pública** (vitrine + checkout): catálogo, produto, carrinho, pagamento Mercado Pago. Cliente PF/PJ compra feno e suplementos, majoritariamente pelo celular.

Sucesso visual = a gestão confia nos números à primeira vista; o balcão opera rápido; o cliente finaliza sem atrito. Fase: pré-lançamento.

## 2. Perfis de usuário e necessidades visuais

| Perfil | Cena de uso | Necessidades visuais |
|---|---|---|
| Administrador/Gestor | Desktop no escritório ou celular na rua | Painel escaneável, numerais tabulares confiáveis, estoque baixo impossível de ignorar, avisos priorizados |
| Vendedor | Celular/tablet no balcão, cliente na frente | Ações grandes, consulta rápida de preço/estoque, cadastro sem erro, métricas próprias |
| Cliente | Celular, decide sozinho | Vitrine clara, preço óbvio, carrinho/checkout curtos, status compreensível |

Consequência: mobile é cenário de trabalho, não exceção. Toda tela de gestão precisa ser operável a uma mão.

## 3. Arquitetura de informação

Duas árvores, dois shells:

- **Gestão** (`base.html`): sidebar persistente + barra superior contextual (unidade ativa, contador de avisos, usuário). Mobile: sidebar vira gaveta off-canvas.
- **Loja** (`base_loja.html`): cabeçalho de e-commerce (marca, busca, carrinho com contador, conta) + rodapé legal (razão social, unidades, LGPD).

Grupos da sidebar:
1. **Visão**: Painel · Avisos
2. **Catálogo**: Produtos · Categorias
3. **Operação**: Estoque · Movimentações · Pedidos
4. **Comercial**: Clientes · Custos
5. **Conta**: Minhas métricas (vendedor) · Minha privacidade · Sair

## 4. Mapa de telas (briefing → arquivos reais)

| Briefing | Arquivo real | Shell |
|---|---|---|
| dashboard/painel | `core/painel.html` | gestão |
| products/list+form+detail | `catalog/produto_list.html`, `produto_form.html`; detalhe interno não existe como rota (§17) | gestão |
| categorias | `catalog/categoria_list.html`, `categoria_form.html` | gestão |
| stock/estoque_list | `stock/estoque_list.html` | gestão |
| movimentações list/form | `stock/movimento_list.html`, `movimento_form.html` | gestão |
| costs/custos_list+despesa_form | `costs/despesa_list.html`, `despesa_form.html` | gestão |
| clientes list/detail/form | `customers/cliente_list.html`, `cliente_detail.html`, `cliente_form.html`, `interacao_form.html` | gestão |
| pedidos list/detail | `sales/pedido_list_interna.html`, `pedido_interno_detail.html` | gestão |
| pedidos do cliente/métricas/status | `sales/meus_pedidos.html`, `minhas_metricas.html`, `pedido_status.html` | loja/gestão |
| store/vitrine·produto·carrinho·checkout·confirmação | `catalog/catalogo.html`, `catalog/produto_loja.html`, `sales/carrinho.html`, `checkout.html`, `pedido_status.html` | loja |
| alerts/avisos_list | `analytics/aviso_list.html` | gestão |
| perfil/privacidade/consentimentos | `privacy/minha_privacidade.html` (+ `politica.html`, `termos.html`) | loja |
| accounts/login+recuperar_senha | `registration/login.html` + suíte `password_reset_*`, `logged_out.html` | auth |
| errors/403·404·500 | novos em `templates/errors/` (wiring §17) | erro |
| extras reais | `fiscal/nota_manual_form.html`, `core/unidade_list.html`, `unidade_form.html`, `sales/simulador_pagamento.html` | gestão |

## 5. Princípios visuais

1. **Número primeiro.** Tabelas e totais são protagonistas: numerais tabulares, dinheiro alinhado à direita, densidade confortável. Nada decora acima de um número que precisa ser lido.
2. **Estado antes de beleza.** Toda lista nasce com seus estados desenhados (dados, vazio, busca sem resultado, carregando, erro). Estoque baixo comunica por forma + cor + texto, nunca só cor.
3. **Voz rural-discreta.** A identidade mora na paleta (verde de campo, areia, fio de palha), nos micro-rótulos em caixa alta e na linguagem comercial direta ("Preço balcão", "Possível recompra") — nunca em enfeite de fazendinha.
4. **Borda vence sombra.** Separação por borda 1px, fundo e espaço; sombra é evento raro (dropdown/modal/toast).
5. **Mobile é balcão.** Fluxo de vendedor/cliente fecha num telefone com uma mão.

## 6. Identidade visual

**Tese:** o papel de pedido de uma casa agropecuária séria virou software — areia de papel de trabalho, tinta verde-institucional, carimbo de status, fio de palha dourado como condutor discreto. Recusa o default da categoria (dashboard SaaS genérico de cards flutuantes).

- **Paleta:** verdes profundos (#1d3a24 família), areias quentes (#faf9f5→#ddd6c7), palha discreta (#f8f3e2/#d9c48a/#8a6a14), tinta cinza-esverdeada. Status: par fundo+borda+texto sempre.
- **Tipografia:** **Archivo variável** auto-hospedada (`static/fonts/archivo-var.woff2`, pesos 400–700, latin pt-BR completo, 34 KB) — caráter utilitário robusto que casa com distribuição/logística agro, sem cair nos defaults de treinamento. Fallback `system-ui`. Hierarquia por peso/tamanho/espaçamento; `tabular-nums` obrigatório em dinheiro e quantidade. Micro-rótulo 0.75rem caixa alta com tracking **apenas em cabeçalhos de tabela e grupos de menu — nunca como eyebrow sobre título**.
- **Formas:** raio 6px controles / 8px cartões; pill só em status/badge; sombra única baixa para flutuantes.
- **Ícones:** SVG inline próprios, traço 1.5px na grade 20px, vocabulário fechado (~24 operacionais). Sem biblioteca externa, sem emoji, sem fazendinha.
- **Motion:** transição única 140ms ease-out (cor/fundo/transform); `prefers-reduced-motion` global. Nenhuma animação decorativa.

## 7. Design tokens

`static/css/app.css` reescrito em camadas: tokens → base → layout → componentes → utilitários. Nomes pt-BR vigentes preservados e estendidos.

**Cor**

| Token | Valor | Papel |
|---|---|---|
| `--verde-900` | `#1d3a24` | Sidebar/topbar, autoridade |
| `--verde-700` | `#2f5d3a` | Ação primária, links fortes |
| `--verde-600` | `#3a7047` | Hover/ativo |
| `--verde-tinta` | `#14532d` | Texto sobre fundo de sucesso |
| `--areia-50` | `#faf9f5` | Fundo de página (gestão) |
| `--areia-100` | `#f6f4ef` | Zona de leitura alternada |
| `--areia-200` | `#ede9df` | Superfície afundada, th de tabela |
| `--areia-300` | `#ddd6c7` | Bordas |
| `--palha-100` | `#f8f3e2` | Fundo de destaque discreto |
| `--palha-400` | `#d9c48a` | Fio condutor, divisores especiais |
| `--palha-600` | `#8a6a14` | Destaque textual secundário (AA em claro) |
| `--tinta-900/700/500` | `#20251e/#454c41/#6d7267` | Texto principal/secundário/auxiliar |
| `--branco` | `#ffffff` | Superfícies |
| status | sucesso `#2e7d43`+`#e4f0e6`; alerta `#975a16`+`#faf0dc`; erro `#b02a37`+`#fbe9ea`; info `#3d5a80`+`#e8eef5` | Par fundo+borda+texto sempre; status nunca só por cor |

Estratégia: **Restrained** — neutros quentes + acento verde + fio de palha. Verde ocupa regiões inteiras apenas na sidebar e nos botões primários.

**Tipografia** — página 1.375rem/700 · seção 1.125rem/650 · corpo 1rem · auxiliar 0.875rem · micro-rótulo 0.75rem/650/+0.06em. Linha 1.5 (títulos 1.25).

**Espaço** — `--espaco-1..7`: 0.25 / 0.5 / 0.75 / 1 / 1.5 / 2 / 3 / 4rem. Ritmo único: mais espaço acima do título que abaixo.

**Raio/sombra/motion** — `--raio-1: 6px`, `--raio-2: 8px`; `--sombra-1` só flutuantes; transição 140ms ease-out.

## 8. Sistema de componentes

Shell em `templates/includes/`: `header_gestao.html`, `sidebar.html`, `nav_user.html`, `messages.html`, `footer_loja.html`. Biblioteca em `templates/components/`, incluída com `{% include "components/x.html" %}` e variáveis no contexto do include:

- **Formulário**: `campo.html` (input/select/textarea unificado com label, helptext, erros), `checkbox_radio.html`, `fieldset.html`, `form_acoes.html`
- **Ação**: `botao.html` (variantes primário/secundário/perigo/fantasma), `grupo_botoes.html`
- **Dados**: `tabela_responsiva.html` (wrapper com scroll + dica), `paginacao.html`, `filtro_barra.html`, `busca_input.html`
- **Estrutura**: `cartao.html`, `cabecalho_pagina.html`, `titulo_secao.html`, `abas.html` (se aplicável), `divisor.html`
- **Feedback**: `alerta.html`, `badge.html` (status→variante mapeado), `estado_vazio.html` (título/descrição/ação), `carregando.html` + `.skeleton`, `modal.html` (dialog nativo)
- **Negócio**: `status_pedido.html` (Aguardando pagamento/Pago/Em separação/Pronto para entrega/Concluído/Cancelado), `estoque_unidade.html` (saldo/disponível/mínimo por unidade com sinal de baixo), `cliente_categoria.html`, `produto_card.html` (loja), `item_carrinho.html`, `pagamento_status.html` (Mercado Pago), `aviso_item.html`

Cada componente declara defaults seguros (`{% if %}` guards) para não quebrar quando o contexto ainda não envia tudo.

## 9. Estados obrigatórios

- **Interação**: default, hover, focus-visible (anel 2px verde, nunca removido), active, disabled.
- **Listas**: com dados · vazio (com orientação e ação) · busca sem resultado · carregando (skeleton em telas HTMX/futuras; botões em estado de envio hoje) · erro.
- **Formulários**: válido, inválido (borda+texto de erro + `aria-describedby`), ajuda, botão desabilitado, enviando (`aria-busy`).
- **Sistema**: sem permissão → `errors/403.html`; indisponível → `errors/500.html`; inexistente → `errors/404.html`; dados insuficientes → estado vazio explicativo ("Sem dados por enquanto" com critério de preenchimento).
- **Pagamento/pedido**: aguardando, aprovado/pago, expirado, cancelado — forma+cor+texto.

## 10. Responsividade

Mobile-first. Breakpoints: `48rem` (tablet retrato), `64rem` (desktop), `80rem` (wide).

- **<48rem**: sidebar vira gaveta (hamburger na barra superior, foco preso, ESC fecha); tabelas densas ganham scroll horizontal com sombra-indicador OU viram cartões empilhados quando >4 colunas numéricas; ações principais fixas ao fundo no checkout.
- **48–64rem**: sidebar recolhida por padrão; formulários em 2 colunas quando o par de campos é curto.
- **≥64rem**: sidebar fixa 15rem; conteúdo máx. 76rem; tabelas completas.
- Alvos de toque ≥44×44px; inputs ≥16px (evita zoom iOS).

## 11. Acessibilidade (mínimo AA)

Contraste verificado por par (texto/fundo); foco visível universal; labels associados; erros anunciáveis (`aria-describedby`, `role="alert"` nas mensagens Django); HTML semântico (`nav/main/section/table/th scope`); ícones decorativos `aria-hidden`; status nunca só por cor (ícone/texto junto); ordem visual = ordem DOM; gaveta mobile gerencia foco e `aria-expanded`; `lang="pt-br"` mantido; alvos ≥44px.

## 12. Critérios anti-AI-SLOP

Proibido: cards coloridos sem propósito; gráfico decorativo sem dado real; gradiente roxo/azul/ciano; glassmorphism; dark mode neon; emoji como ícone; ilustração genérica; lorem ipsum; métrica inventada; badge excessivo; raio/sombra exagerados; hero de startup; texto de marketing falso.
Obrigatório: cara de sistema real; dado fictício só quando necessário e coerente (Tifton 85, Coastcross, Alfafa, Haras Boa Vista…); empty states úteis; hierarquia forte; consistência rigorosa entre as duas faces (mesma família, vozes distintas).

## 13. Critérios de aceite

1. Nenhum template genérico de IA; identidade sóbria e própria reconhecível sem logo.
2. Navegação clara nos dois shells; ativo visível.
3. Vazio/erro/carregando/sucesso presentes onde aplicável; sem permissão coberto.
4. Formulários acessíveis (label, erro descrito, foco).
5. Tabelas legíveis em mobile e desktop; dinheiro tabular à direita.
6. Sem lorem ipsum, sem gráfico sem dado, sem excesso de efeito.
7. Contraste AA; foco visível.
8. Sistema documentado (DESIGN.md ao final) + relatório `/impeccable`.
9. Templates prontos para receber backend (já recebem: usam contexto real).
10. Parece sistema real de gestão, não landing page.

## 14. Riscos visuais e mitigação

| Risco | Mitigação |
|---|---|
| Quebrar templates funcionais existentes | Mesmos nomes de bloco/contexto; classes novas aditivas; teste `pytest` + smoke visual por tela |
| Virar "template admin genérico" | Tese da identidade (§6): papel comercial + fio de palha + micro-rótulos próprios; revisão anti-slop por ciclo |
| Verde cansar / virar caricatura rural | Estratégia Restrained; palha só como fio; zero enfeite temático |
| Tabela ilegível em mobile | Padrão único decidido por tipo de coluna (scroll vs cartão), documentado no SDD |
| Duas faces divergirem | Tokens compartilhados; loja usa mesma base tipográfica/cromática com composição própria |
| JS crescer além do permitido | Um único `app.js` vanilla (<150 linhas): gaveta, dropdown, submit state, modal |

## 17. Pendências conhecidas (não bloqueiam)

- Detalhe interno de produto não existe como rota — avaliar com backend depois.
- `checkout_confirmacao` mapeia para `pedido_status.html` (confirmação pós-pagamento).
- Wiring de handlers 403/404/500 em `config/urls.py` (glue mínimo, sem lógica).
- Consentimentos LGPD granulares podem exigir ajuste de view futura.
- Auto-hospedar fonte própria é opcional e postergável.

## Plano de ciclos

- **C2 Fundação**: tokens + shells (gestão/loja/auth) + ícones SVG + `app.js`.
- **C3 Componentes**: biblioteca `templates/components/` + estados.
- **C4 Telas**: todos os arquivos do mapa §4, dados reais, estados reais.
- **C5 Revisão**: detector mecânico, acessibilidade, anti-slop, correções, relatório final.
