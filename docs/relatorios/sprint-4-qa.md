# Portão de Qualidade e Segurança — Fase 4 (parcial, pré-deploy)

Data: 2026-08-23 · Escopo: LGPD, hardening e preparação de operação.

## Status da suíte

- **Testes**: 170 passed + 140 subtests; **E2E Playwright: 1 passed** (compra completa).
- **Cobertura**: 88.18% (`reports/coverage.xml`).
- **Lint**: ruff sem erros. **Bandit (medium/high): 0. pip-audit: sem CVEs.**

## Entregue nesta fase

| Item | Estado |
|---|---|
| Política de Privacidade + Termos públicos | ✅ testado anônimo |
| Consentimentos versionados por finalidade (marketing separado) com revogação | ✅ |
| Direitos do titular: acesso/correção/exportação JSON/exclusão com prazo+responsável | ✅ |
| Exclusão condicionada: anonimização preservando integridade fiscal | ✅ |
| Minimização de PII em logs (filtro sanitizador CPF/CNPJ) + teste | ✅ |
| Restrição de acesso a dados pessoais por perfil | ✅ matriz |
| Headers HSTS/XCTO/XFO/CSP + cookies Secure/HttpOnly + rate limit login (axes) | ✅ código+testes |
| Sentry (init condicionado por DSN, `send_default_pii=False`) | ✅ código |
| Blueprint Render (`render.yaml`) com web/db/healthcheck/crons | ✅ |
| Backup script + retenção + instruções restore | ✅ scripts/runbook |
| Runbook operacional + plano de resposta a incidente + checklist go-live | ✅ `docs/runbook.md`, `docs/incidentes.md` |

## Pendências que exigem ambiente/contas externas

1. **OWASP ZAP baseline** — requer alvo publicado (staging). Comando previsto no CI pós-deploy; rodar contra staging antes do go-live.
2. **Sentry/UptimeRobot ativos** — criar projeto/monitor e definir `SENTRY_DSN`; validar alerta real.
3. **Backup automático + restore testado** — script pronto; executar contra PostgreSQL de staging e registrar evidência (`docs/relatorios/backup-restore.md`).
4. **Deploy Render + smoke de produção** — blueprint pronta; depende de conta/repo conectado e credenciais reais (MP/Bling/domínio).
5. **Validação final E2E em produção simulada** (cadastro→compra→pagamento→NF-e→pedido) — depende dos itens 1–4 (sandbox MP/Bling reais).

## Checklist LGPD final

- [x] Política publicada e versionada
- [x] Consentimentos com finalidade/versão/IP e marketing separado
- [x] Exportação legível e auditada
- [x] Exclusão com anonimização respeitando retenção fiscal
- [x] Logs sem PII (filtro testado)
- [ ] Política revisada juridicamente (externo — recomendado antes do go-live)
