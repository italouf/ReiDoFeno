# Runbook de Emergência e Operação — Fase 5

**Fase:** 5
**Status:** Implementada
**Depende de:** Backup (`ADR-019`), DRILL (`validar_restore`), 2FA (`ADR-020`), Observabilidade (`/healthz/`, Sentry).

## Objetivo

Consolidar procedimentos acionáveis de emergência, deploy, rollback, plano de
fuga, backup/restore, reset de 2FA, checklists de go-live e templates de
registro operacional em `docs/runbook.md` e `docs/runbook/templates/`.

## Especificação

1. **`docs/runbook.md`:**
   - Contatos de emergência (placeholders operacionais para Nilton, Neto, Caio,
     operador técnico e provedores; sem segredos no repositório).
   - Árvore de decisão rápida para triagem de incidentes.
   - Procedimentos passo a passo (SEV1–SEV3): site fora/502, banco fora/corrupção,
     disco cheio, falha de backup, suspeita de vazamento/invasão (LGPD), perda
     de acesso 2FA.
   - Operação de backup noturno (`infra/backup/backup.sh`) e DRILL de
     restauração (`infra/backup/restore.sh` + `python manage.py validar_restore`).
   - Deploy, rollback de emergência na VPS e plano de fuga (Render + Neon).
   - Monitoramento (`/healthz/`, Sentry sem PII, UptimeRobot).
   - Rotinas agendadas, workflows Fase 4 (pagamento manual, conciliação, NF-e),
     checklists pré-deploy, pós-deploy e go-live.
2. **Templates:**
   - `docs/runbook/templates/drill-report.md` (já criado na Tarefa 2).
   - `docs/runbook/templates/incident-report.md` (template de pós-incidente).
3. **Validação automatizada (`docs/tests/test_runbook_links.py`):**
   - Garante presença das seções obrigatórias, integridade de links Markdown
     locais e resolução de rotas Django citadas no runbook.
