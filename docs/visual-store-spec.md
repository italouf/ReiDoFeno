# Visual Store Spec — Loja Rei do Feno (v3)

Redesign da vitrine/loja · direção nova e independente do painel (que permanece no mundo v2/areia-verde).
Restrição estrutural: views/URLs/models intocados, **exceto** o backend mínimo autorizado (busca/ordenação/faixa de preço na view do catálogo + context processor do contador).

## 1. Mundo visual

**"Armazém agropecuário de porta aberta."** Loja terrosa e comercial: creme de papel, verde folha de ação, palha de acento raro, marrom terra de âncora. Nada de startup, nada de fazendinha caricata. O visitante precisa sentir: loja real, empresa real, preço claro, compra segura.

## 2. Paleta (com regra AA)

| Token | Valor | Uso |
|---|---|---|
| `--verde-folha` | `#4A6741` | Ação primária, header (faixa), links ativos |
| `--verde-folha-hover` | `#3E5737` | Hover de ação |
| `--verde-folha-escuro` | `#2F4229` | Overlay do hero, texto sobre palha |
| `--palha` | `#C4A95B` | Badge, detalhe, indicador — nunca texto pequeno |
| `--palha-claro` | `#F3EBD8` | Fundo de badge/faixa de benefícios |
| `--marrom-terra` | `#5C4A3A` | Títulos, preços, footer (fundo) |
| `--marrom-texto` | `#3E3428` | Corpo de texto principal (AA+ sobre creme) |
| `--creme` | `#F7F3EC` | Fundo da loja |
| `--branco-quente` | `#FDFCFA` | Cards, formulários |
| `--cinza-quente` | `#8C8279` | **Só** bordas sutis/legendas decorativas |
| `--cinza-texto` | `#6B6258` | Texto secundário (AA: 5.1:1 sobre creme) |
| `--borda` | `#E8E2DA` | Divisores, bordas de card |
| sucesso/alerta/erro/info | `#3D7A45` / `#D4A017` / `#B34040` / `#4A7A8C` | Convenção; sempre com rótulo textual |

Regras: verde folha é a ÚNICA cor de ação; palha ≤5% da tela; sem gradiente entre cores da paleta (overlay do hero é verde-escuro sólido translúcido); sombras neutras e baixas; foco visível 2px verde folha.

## 3. Tipografia

- **Corpo/UI:** Nunito Sans (variável 400–800, auto-hospedada, `display=swap`) — da lista do briefing, fora dos defaults de IA.
- **Títulos:** Lexend (variável 500–700, auto-hospedada) — da lista de acento do briefing; só em h1–h3 e logo.
- Escala: display 2.5rem/700 · h1 2rem · h2 1.5rem/600 · h3 1.25rem/600 · h4 1.125rem/500 · body 1rem/1.6 · small 0.875rem · caption 0.75rem · preço 1.5rem/700 tabular · preço antigo 1rem riscado cinza-texto.

## 4. Ícones, imagens, assets

- **Ícones:** sprite SVG próprio do sistema (traço 1.5, grade 20) — conjunto único, custo zero; novos ícones seguem a mesma gramática (Tabler-like).
- **Produtos:** fotos de banco licenciadas já integradas (`produto_imagem.html`) + placeholder desenhado honesto. Proporção 4:3.
- **Hero:** foto real licenciada de feno (`feno-graminea.jpg`) com overlay verde-folha-escuro e CTA âncora. Sem texto motivacional vazio.
- **Pagamento:** texto ("Pix · Cartão · Mercado Pago") — sem bandeiras falsas.
- **Contato oficial (fornecido pelo usuário):** WhatsApp **75 98145-7227** → `https://wa.me/5575981457227`.

## 5. Estrutura de arquivos (adaptada à realidade Django)

Views têm `template_name` fixo → páginas ficam nos caminhos atuais; o novo mundo mora em:

```
templates/store/
  base_store.html          # shell exclusivo da loja
  includes/ header.html · footer.html · breadcrumb.html · product_card.html ·
            cart_item.html · order_status_badge.html · empty_state.html ·
            pagination.html · filters.html · search_bar.html · trust_badges.html ·
            benefits_bar.html
static/css/store/ tokens.css · base.css · layout.css · components.css · pages.css · responsive.css
static/fonts/store/ nunito-sans.woff2 · lexend.woff2
static/js/store/ menu.js · quantity-selector.js · cart-feedback.js
```

Páginas (paths reais das views): `catalog/catalogo.html` (home+catálogo), `catalog/produto_loja.html`, `sales/carrinho.html`, `sales/checkout.html`, `sales/pedido_status.html` (confirmação+acompanhamento), `sales/meus_pedidos.html`, `sales/simulador_pagamento.html`, `privacy/minha_privacidade.html`, `privacy/politica.html`, `privacy/termos.html`.

## 6. Backend mínimo (autorizado)

1. `CatalogoLojaView`: aceita `q` (busca em nome/categoria), `ordenar` (`relevancia|preco|preco_desc|nome`), `preco_min`, `preco_max`. Mesma URL `/`.
2. `sales/context_processors.py`: `carrinho(request)` → `itens_carrinho` (soma das quantidades na sessão). Registrado em `TEMPLATES` (`base.py`). Não altera lógica de carrinho.

## 7. Telas (objetivo · hierarquia · CTAs · estados · mobile)

- **Home/Catálogo** (`/`): hero (frase curta + CTA "Ver produtos") → chips de categoria → barra busca/ordenação/faixa → grid de cards → faixa de benefícios → footer. CTA: card → produto. Estados: vazio, busca sem resultado (com sugestão de limpar filtros). Mobile: hero compacto, chips scrolláveis, grid 1–2 col.
- **Produto**: breadcrumb → foto grande (zoom leve no hover) + nota ilustrativa → categoria/nome/preço → specs (unidade, NCM) → seletor qtd + "Adicionar ao carrinho" → benefícios (retirada/entrega/WhatsApp) → disponibilidade textual por unidade (sem estoque ao vivo — fase 2). CTA único: adicionar.
- **Carrinho**: itens (foto, nome, qtd editável, subtotal, remover) → resumo (subtotal, total) → "Finalizar compra" + "Continuar comprando". Vazio: estado com CTA à vitrine.
- **Checkout**: passos 1–3 visuais (identificação · entrega/retirada · pagamento), formulário limpo, resumo lateral, selos textuais (CNPJ, Mercado Pago, cadeado). Erros inline acessíveis.
- **Confirmação/status** (`pedido_status`): sucesso, número, badge de status, itens, totais, próximos passos, link WhatsApp do atendimento.
- **Meus pedidos**: lista (número, data, status badge, total) → detalhe; vazio com CTA.
- **Perfil/Privacidade**: consentimentos LGPD + solicitações (o que existe hoje); edição completa de perfil = fase 2.

## 8. Micro-interações (≤200ms, `prefers-reduced-motion` respeitado)

Hover de card (elevação 2px + borda palha), transição de botão, pulso do badge ao adicionar, toast de confirmação via messages, skeleton shimmer sob imagens enquanto carregam. Proibido: parallax, bouncing, bloqueios de conteúdo.

## 9. Anti-AI-SLOP (contratos)

Sem gradientes roxo/azul/ciano, glassmorphism, neon, sombras coloridas, hero motivacional, "how it works" de 3 ícones, depoimentos/métricas inventadas, emojis como UI, raio >12px, dark mode. Obrigatório: preços visíveis, footer com dados reais (CNPJ, unidades, WhatsApp), estados vazios, identidade Rei do Feno (fardo no logo, voz comercial pt-BR).

## 10. Fase 2 (documentada, fora do escopo atual)

Busca no servidor com destaque de termos (hoje: filtro na própria listagem), produtos relacionados, campo de promoção (preço antigo), estoque ao vivo por unidade, perfil editável, página de trocas/devolução.
