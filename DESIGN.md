---
name: Rei do Feno — Gestão e Loja
description: Sistema de gestão e vitrine de alimentos para animais — papel comercial de balcão agropecuário virou software.
colors:
  verde-lona-900: "#1d3a24"
  verde-lona-700: "#2f5d3a"
  verde-lona-600: "#3a7047"
  verde-tinta: "#14532d"
  areia-papel-50: "#faf9f5"
  areia-papel-100: "#f6f4ef"
  areia-papel-200: "#ede9df"
  areia-papel-300: "#ddd6c7"
  palha-seca-100: "#f8f3e2"
  palha-seca-400: "#d9c48a"
  palha-seca-600: "#8a6a14"
  tinta-formulario-900: "#20251e"
  tinta-formulario-700: "#454c41"
  tinta-formulario-500: "#6d7267"
  superficie: "#ffffff"
  sucesso-borda: "#2e7d43"
  sucesso-fundo: "#e4f0e6"
  alerta-borda: "#975a16"
  alerta-fundo: "#faf0dc"
  erro-borda: "#b02a37"
  erro-fundo: "#fbe9ea"
  info-borda: "#3d5a80"
  info-fundo: "#e8eef5"
  perigo-hover: "#971f29"
  toast-sucesso: "#5fbf7a"
  toast-erro: "#e07b84"
typography:
  display:
    fontFamily: "Archivo, system-ui, -apple-system, 'Segoe UI', Roboto, Arial, sans-serif"
    fontSize: "1.375rem"
    fontWeight: 700
    lineHeight: 1.25
    letterSpacing: "-0.01em"
  title:
    fontFamily: "Archivo, system-ui, sans-serif"
    fontSize: "1.125rem"
    fontWeight: 650
    lineHeight: 1.25
  body:
    fontFamily: "Archivo, system-ui, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.5
  scale:
    numero-destaque: "2rem"
    total-carrinho: "1.5rem"
    preco-carrinho: "1.2rem"
    titulo-card: "1.05rem"
    tabela-botao: "0.95rem"
    metadado-card: "0.9rem"
    auxiliar: "0.875rem"
    ajuda: "0.85rem"
    badge: "0.8125rem"
  label:
    fontFamily: "Archivo, system-ui, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 650
    lineHeight: 1.5
    letterSpacing: "0.06em"
rounded:
  sm: "6px"
  md: "8px"
  pill: "999px"
  foco: "2px"
spacing:
  1: "0.25rem"
  2: "0.5rem"
  3: "0.75rem"
  4: "1rem"
  5: "1.5rem"
  6: "2rem"
  7: "3rem"
  8: "4rem"
components:
  button-primary:
    backgroundColor: "{colors.verde-lona-700}"
    textColor: "{colors.superficie}"
    rounded: "{rounded.sm}"
    padding: "8px 16px"
    height: "44px"
  button-secondary:
    backgroundColor: "{colors.superficie}"
    textColor: "{colors.tinta-formulario-700}"
    rounded: "{rounded.sm}"
    padding: "8px 16px"
    height: "44px"
  card:
    backgroundColor: "{colors.superficie}"
    textColor: "{colors.tinta-formulario-900}"
    rounded: "{rounded.md}"
    padding: "24px"
  input:
    backgroundColor: "{colors.superficie}"
    textColor: "{colors.tinta-formulario-900}"
    rounded: "{rounded.sm}"
    padding: "8px 12px"
    height: "44px"
  badge-ok:
    backgroundColor: "{colors.sucesso-fundo}"
    textColor: "{colors.verde-tinta}"
    rounded: "{rounded.pill}"
    padding: "2px 8px"
---

# Design System: Rei do Feno

## Overview

**Creative North Star: "O pedido de balcão da casa agropecuária, virado software."**

Um sistema que se comporta como o papel de trabalho comercial de uma distribuidora séria de feno e suplementos: fundo de areia quente como papel, tinta cinza-esverdeada como caneta, verde de lona institucional para ações e confirmações, e um fio de palha dourada que costura a identidade sem virar enfeite. A hierarquia serve primeiro ao número — venda, saldo, lucro — porque o usuário primário decide comprando e revendo estoque. A voz é comercial e direta ("Preço balcão", "Possível recompra", "Estoque baixo"), em pt-BR, sem marketing.

A identidade é rural-discreta, nunca caricata: nada de fazendinha, texturas de madeira, fontes manuscritas ou ícones infantis. A rusticidade mora na paleta e no vocabulário, não em ornamento. As duas faces do produto (gestão interna e loja pública) compartilham tokens e tipografia; a gestão é densa e operacional, a loja é tipográfica e comercial.

**Key Characteristics:**
- Borda de 1px vence sombra; superfícies planas por padrão.
- Numerais tabulares e alinhados à direita em todo dinheiro e quantidade.
- Micro-rótulos em caixa alta com tracking só em cabeçalhos de tabela e grupos de menu.
- Fio de palha (#d9c48a) como assinatura discreta: cor tipográfica secundária e regras de 1px, nunca borda-acento grossa.
- Estados desenhados antes de beleza: vazio, carregando, erro e sem permissão existem em toda lista.

## Colors

Paleta restrita de neutros quentes com um único acento institucional e um fio decorativo; status sempre em par fundo+borda+texto.

### Primary
- **Verde Lona 900** (#1d3a24): sidebar da gestão e autoridade institucional; ocupa região inteira só aqui.
- **Verde Lona 700** (#2f5d3a): ação primária (botões), links fortes, hover da sidebar.
- **Verde Lona 600** (#3a7047): hover/ativo de ações primárias e anéis de foco.

### Secondary
- **Palha Seca 600** (#8a6a14): destaque textual secundário (rótulo de categoria no cartão de produto, página ativa da loja); AA sobre claro.
- **Palha Seca 400** (#d9c48a): fio condutor — regras de 1px, seleção de texto, paginação ativa.
- **Palha Seca 100** (#f8f3e2): fundo de aviso não lido e destaques discretos.

### Neutral
- **Areia de Papel 50** (#faf9f5): fundo de página.
- **Areia de Papel 100** (#f6f4ef): cabeçalho de tabela, superfícies afundadas, hover de linhas.
- **Areia de Papel 200** (#ede9df): divisores internos.
- **Areia de Papel 300** (#ddd6c7): bordas de cartões, tabelas e campos.
- **Tinta de Formulário 900/700/500** (#20251e / #454c41 / #6d7267): texto principal / secundário / auxiliar.
- **Branco** (#ffffff): superfícies de cartão, tabela e barra superior.

### Status
- **Sucesso** (#2e7d43 sobre #e4f0e6, texto #14532d): pago, ativo, estoque OK.
- **Alerta** (#975a16 sobre #faf0dc, texto #5c3708): aguardando pagamento, estoque baixo.
- **Erro** (#b02a37 sobre #fbe9ea, texto #701a20; hover do destrutivo #971f29): cancelado, falhou, recusado.
- **Info** (#3d5a80 sobre #e8eef5, texto #24405e): em separação, pronto para entrega.
- **Acentos de toast** (#5fbf7a sucesso, #e07b84 erro): cor do ícone sobre toast escuro.

### Named Rules
**A Regra da Borda Vence Sombra.** Separação por borda 1px, fundo ou espaço. Sombra é evento de flutuação (dropdown, modal, toast), nunca estado padrão de cartão.
**A Regra do Fio de Palha.** A palha é assinatura tipográfica e fio de 1px. Nunca vira borda-acento grossa (3px+) em elemento arredondado — o tell mais reconhecível de interface genérica.
**A Regra do Par de Status.** Nenhum status comunica só por cor: sempre fundo + borda + rótulo textual (e ícone quando crítico).

## Typography

**Display/Body Font:** Archivo variável auto-hospedada, pesos 400–700 (`static/fonts/archivo-var.woff2`, subset latin pt-BR), fallback `system-ui`.
**Character:** Grotesca utilitária de caráter logístico — firme em título, econômica em tabela; zero custo de terceiros e nenhuma fonte decorativa.

### Hierarchy
- **Display** (700, 1.375rem, 1.25, -0.01em): título de página (h1).
- **Title** (650, 1.125rem, 1.25): título de seção/cartão (h2).
- **Body** (400, 1rem, 1.5): corpo e células de tabela (0.95rem em tabelas densas).
- **Auxiliares** (400–650): 2rem/1.5rem números de destaque · 1.2rem preço de carrinho · 1.05rem título de card · 0.95rem tabela/botões · 0.9rem metadado de card · 0.875rem auxiliar/rodapé · 0.85rem helptext · 0.8125rem badge.
- **Label** (650, 0.75rem, +0.06em, caixa alta): cabeçalhos de tabela e títulos de grupo de menu — nunca eyebrow sobre heading.

### Named Rules
**A Regra do Número Tabular.** Dinheiro e quantidade usam `font-variant-numeric: tabular-nums`, alinhados à direita, sem quebra de linha.

## Layout

Dois shells. **Gestão:** sidebar fixa de 15rem (verde lona 900) com grupos rotulados (Visão, Catálogo, Operação, Comercial, Conta) e rodapé de usuário fixo no fim; barra superior branca de 1px com gaveta no mobile; conteúdo máximo de 76rem sobre areia 50. **Loja:** topo de e-commerce branco (marca + Vitrine/Carrinho + conta) e rodapé legal com razão social, CNPJ e unidades. Autenticação usa cartão centrado de 26rem sobre areia 100.

Ritmo de espaço: mais acima do título que abaixo; escala 4/8/12/16/24/32/48/64px. Breakpoints: 48rem (tablet), 64rem (desktop — sidebar fixa, gaveta some, densidade de menu cai para 40px), 80rem. Mobile-first: sidebar vira gaveta off-canvas com véu, foco preso e ESC; tabelas densas rolam horizontal dentro de moldura arredondada; alvos de toque ≥44px.

## Elevation & Depth

Sistema plano por padrão; profundidade vem de borda, fundo e espaço. Duas sombras suaves, ambas com desfoque e deslocamento, reservadas a flutuantes.

### Shadow Vocabulary
- **Sombra 1** (`0 1px 2px rgb(32 37 30 / 0.06), 0 4px 12px rgb(32 37 30 / 0.07)`): cartão de autenticação.
- **Sombra 2** (`0 2px 4px rgb(32 37 30 / 0.08), 0 12px 28px rgb(32 37 30 / 0.14)`): dropdown, modal, toast, gaveta aberta.

### Named Rules
**A Regra do Plano por Padrão.** Se o elemento não flutua sobre a página, ele não tem sombra.

## Shapes

Raio 6px em controles (botões, campos, itens de menu) e 8px em cartões; pill (999px) reservado a badges de status. Bordas sempre de 1px em areia 300; a única exceção de espessura é o cartão de autenticação e o produto da loja em suas regras de palha de 1px. Ícones são SVG inline próprios, traço 1.5px na grade 20px, vocabulário fechado de ~23 símbolos operacionais — sem emoji, sem biblioteca externa.

## Components

### Buttons
- **Shape:** raio 6px, altura mínima 44px (36px na variante pequena), peso 600.
- **Primary:** verde lona 700 com texto branco; hover verde 600; disabled a 55% sem mudança de hue.
- **Secondary:** contorno areia 300, texto tinta 700; hover fundo areia 100.
- **Danger / Ghost:** vermelho sóbrio sólido para destrutivo; ghost transparente para ações terciárias.
- **Focus:** anel 2px verde 600 com offset 2px, nunca removido. Envio de formulário gira spinner no próprio botão (`aria-busy`).

### Cards / Containers
- **Corner Style:** 8px; borda 1px areia 300; fundo branco; padding 24px.
- **Shadow Strategy:** nenhuma em repouso (ver Elevation).

### Inputs / Fields
- **Style:** 44px de altura, borda areia 300, raio 6px; select com seta desenhada em gradiente CSS.
- **Focus:** contorno 2px verde 600 + borda verde 600.
- **Error:** borda vermelha + lista de erros `role="alert"` ligada ao campo; disabled com fundo areia 100.

### Tables
- **Moldura:** wrapper arredondado com scroll horizontal e foco por teclado.
- **Cabeçalho:** areia 100, micro-rótulo caixa alta tinta 500.
- **Linhas:** divisores areia 200; hover areia 100 a 60%; números à direita em tabular; `tfoot` destacado.

### Badges / Status
- **Style:** pill com par fundo+borda+texto do status; ícone de 14px quando crítico (estoque baixo, cancelado).

### Navigation
- **Sidebar (gestão):** itens de 44px (40px no desktop) com ícone 20px; ativo = fundo branco 14% + peso 600 + `aria-current="page"` por `view_name`; rodapé fixo com usuário e Sair.
- **Loja:** links de topo com estado ativo em palha 100/palha 600.
- **Mobile:** gaveta com véu, foco preso, ESC fecha, `aria-expanded` no botão.

## Do's and Don'ts

### Do:
- **Do** usar numerais tabulares alinhados à direita em toda coluna de dinheiro/quantidade.
- **Do** desenhar vazio, erro, carregando e sem permissão em toda lista nova.
- **Do** manter pt-BR direto nos rótulos ("Preço balcão", "Marcar lido", "Registrar entrada").
- **Do** reservar o verde lona para ação e institucional; é escasso de propósito.
- **Do** usar o sprite SVG próprio (`#i-…`) com traço 1.5px para qualquer ícone.

### Don't:
- **Don't** usar gradiente, neon, roxo de dashboard, glassmorphism ou dark mode.
- **Don't** usar emoji como ícone ou fonte decorativa/manuscrita em qualquer superfície.
- **Don't** inventar métrica, depoimento ou foto de produto; estado vazio é a resposta honesta.
- **Don't** aplicar borda-acento grossa (3px+) em elemento arredondado — nem na palha.
- **Don't** colocar micro-rótulo em caixa alta como eyebrow acima de título.
