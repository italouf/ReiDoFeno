# Relatório Impeccable — Camada Visual Rei do Feno v2

> **Apêndice (23/08/2026, rodada 2):** corrigido o 404 pós-login (`LOGIN_REDIRECT_URL` → `/painel/painel/` e link "Painel interno" em `base_loja.html`); vitrine ganhou fotos de banco licenciadas (Wikimedia Commons, proveniência em `docs/imagens-produtos.md` + origem embutida nos JPEGs via embed-prompt), componente `produto_imagem.html` com fallback desenhado, faixa de benefícios, página de produto com foto grande e nota "imagem ilustrativa"; banco dev limpo (debug removido) e semeado com catálogo coerente (6 produtos, 3 categorias); DESIGN.md atualizado com a rampa tipográfica real (`typography.scale`), cores de estado e raio de foco — detector **0 findings**; 170 testes verdes; capturas em `.impeccable/review/vitrine-fotos-*.png` e `produto-fotos-desktop.png`.

Data: 23/08/2026 · Executado via skill Impeccable (SDD em `docs/visual-sdd.md`)
Revisão final inline (substituição divulgada: este harness não expõe os subagentes `impeccable-finish-reviewer`/`impeccable-documenter`; o pass seguiu `degraded/finish-reviewer.md` + `degraded/documenter.md`).

## 1. Veredito

**Ship.** Detector mecânico limpo (`[]`, modo regex degradado), 170 testes passando, ruff limpo, 10 capturas desktop+mobile inspecionadas em 2 rodadas limitadas; correções da rodada confirmadas por recaptura.

## 2. Evidência

- Capturas: `.impeccable/review/*.png` (gestão desktop/mobile + gaveta, produtos, vitrine, carrinho, login — desktop e mobile).
- Detector: `node scripts/detect.mjs --json …` → `[]`.
- Testes: `pytest -q` → 170 passed / 140 subtests.
- Sistema documentado: `DESIGN.md` + `.impeccable/design.json`.

## 3. Correções aplicadas na revisão

1. **Bordas-acento grossas removidas** (detector): toasts, cartão de auth, produto-cartao, pagamento, checkout, simulador. Fio de palha migrado para tipografia e regras de 1px.
2. **Hamburger visível no desktop** — base `.btn-gaveta` vinha depois do media query (cascata); override adicionado após a base.
3. **Rodapé da sidebar fora do viewport** — sidebar virou flex column com `menu-rodape` fixo por `margin-top:auto`; densidade do menu reduzida no desktop (itens 40px) para caber em 900px. Confirmado: rodapé y=803, visível.
4. **KPI "Produtos ativos"** herdava alinhamento à direita de `.num`; agora à esquerda com tabular-nums próprio.
5. **Bug pré-existente de produção corrigido**: `STATICFILES_DIRS` inexistente em `config/settings/base.py` — o CSS do projeto nunca seria servido (nem antes desta reforma). Adicionado `[BASE_DIR / "static"]`.
6. **Dev-only**: `WHITENOISE_USE_FINDERS/AUTOREFRESH` em `config/settings/development.py` para estáticos ao vivo no runserver.
7. Teste estrutural do painel alinhado à nova marcação (`Aguardando pagamento</th>` → `>Aguardando pagamento<`) — intenção preservada.

## 4. Checklist de acessibilidade (AA)

- [x] Contraste: pares texto/fundo verificados (tinta sobre areia/branco ≥7:1; palha-600 #8a6a14 sobre claro ≈5,5:1; textos de status escuros sobre fundos claros).
- [x] Foco visível universal (`:focus-visible` 2px verde; claro sobre verde-900).
- [x] Labels associados; erros em listas `role="alert"`; mensagens Django como `role="status"/"alert"`.
- [x] HTML semântico (`nav/main/section/table/th scope`); `lang="pt-br"`.
- [x] Ícones decorativos `aria-hidden="true"`; sprite com símbolos nomeados.
- [x] Status nunca só por cor (badge sempre com rótulo; ícone nos críticos).
- [x] Gaveta mobile: foco preso, ESC fecha, véu clicável, `aria-expanded`, retorno de foco.
- [x] Alvos de toque ≥44px (36–40px só em densidade desktop com mouse); link "pular para conteúdo".
- [x] `prefers-reduced-motion` desliga animações/transições globalmente.

## 5. Checklist anti-AI-SLOP

- [x] Sem gradiente/neon/roxo de dashboard/ciano/glassmorphism/dark mode neon.
- [x] Sem cards decorativos sem propósito; sem gráfico sem dado real.
- [x] Sem lorem ipsum; sem métrica inventada; dados demo coerentes (Tifton 85, Coastcross, Alfafa…).
- [x] Sem emoji como ícone; sprite SVG próprio com vocabulário fechado.
- [x] Sem hero de startup; loja é grade comercial direta.
- [x] Sem eyebrow/kicker sobre títulos (proibição respeitada no sistema).
- [x] Sombras mínimas com offset+blur, só em flutuantes.
- [x] Identidade própria reconhecível: areia + verde lona + fio de palha + micro-rótulos + Archivo auto-hospedada.

## 6. Pendências (não bloqueiam)

1. Detalhe interno de produto não existe como rota (avaliar com backend).
2. Filtro de categoria/vitrine usa `onchange` + `noscript` fallback; HTMX pode substituir depois.
3. Fotos reais de produtos: inexistem; cards são tipográficos de propósito até chegarem fotos (não fabricar).
4. Fonte: Archivo cobre display/body; se um dia houver identidade de marca própria, re-hospedar variável específica.
5. Dados de demonstração deixados no banco dev (usuário `demo`/`demo-12345`, 5 produtos, unidades) para conferência visual — limpar antes de produção.

## 7. Arquivos entregues

Ver relatório no chat (seção "Arquivos criados ou alterados") — tokens/shells/componentes/38 templates + DESIGN.md + sidecar + SDD + este relatório.
