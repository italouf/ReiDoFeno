# BACKUP — Backup noturno automatizado e envio offsite (R2/B2)

**Fase:** 5
**Status:** Implementada
**Depende de:** ADR-001 (PostgreSQL local), ADR-006 (NF-e manual e PDFs), ADR-012 (Retenção fiscal 5 anos), ADR-019 (Estratégia de backup).

## Objetivo

Garantir cópia de segurança diária, verificada e com envio offsite para o
ambiente VPS (`infra/docker-compose.yml`), protegendo banco PostgreSQL,
mídias/comprovantes/PDFs fiscais e configurações criptografadas, com RPO ≤ 24h.

## Garantias preservadas

- **STO-01 / ADR-003 / ADR-008:** dump lógico `pg_dump -Fc` captura
  `MovimentoEstoque`, `ReservaEstoque` e `ItemPedido.custo_unitario` em
  snapshot transacional consistente.
- **ADR-006 / ADR-012 / ADR-018:** backup de mídia inclui `ComprovantePagamento`
  e PDFs de `NotaFiscal` sem alterar `retido_ate`.
- **CUS-01:** `pg_dump` preserva encoding UTF-8 e documentos alfanuméricos.
- **Stack Docker (Fase 3):** compatível tanto com o volume Docker `media`
  quanto com bind-mount em `/opt/reidofeno/media`.

## Especificação

1. **`infra/backup/backup.sh`:**
   - Gera timestamp `YYYY-MM-DD_HHMM` (ou nomes fixos em `--dry-run`).
   - Executa `pg_dump -U reidofeno -Fc reidofeno` no serviço `db` via
     `docker compose` e valida imediatamente com `pg_restore --list`.
   - Arquiva mídia (`/app/media` do serviço `web` ou bind-mount local).
   - Arquiva configurações críticas presentes (`.env.docker`, `infra/.env`,
     `.env`, `infra/docker-compose.yml`, `infra/Caddyfile`,
     `infra/transport.caddy`, `infra/crontab`).
   - Criptografa o pacote de configurações com `age -r "$BACKUP_AGE_RECIPIENT"`
     e remove o `.tar.gz` em claro (inclusive via `trap` em erro).
   - Aplica retenção local via `infra/backup/apply-retention.sh`.
   - Envia artefatos via `rclone copy` para `BACKUP_REMOTE` (R2 ou B2) e valida
     checksum SHA-256 remoto após upload.
   - Registra log estruturado em `BACKUP_LOG` (`/var/log/reidofeno/backup.log`).
   - Em falha, grava `CRITICAL: BACKUP_FAILED: ...` e tenta notificar via
     `python manage.py reportar_backup_falha` para visibilidade no Sentry.
2. **`infra/backup/apply-retention.sh`:**
   - Retenção local padrão: mantém últimos 7 dias (`-mtime +7 -delete`) para
     dumps, mídias e configs criptografadas; retenção semanal (4) e mensal (3)
     suportada por diretórios/política do bucket offsite (30 dias diários,
     12 meses mensais).
3. **`infra/backup/cron.d/reidofeno-backup`:**
   - Agendamento no host às `02:30` (`America/Bahia`).
4. **`core/backup.py` + `reportar_backup_falha`:**
   - Função `notificar_falha_backup(reason, detail="")` que emite log
     `CRITICAL` no logger `reidofeno.backup` com prefixo `BACKUP_FAILED` (sem
     vazar segredos/PII).

## Critérios de aceite

- `backup.sh --dry-run` gera dump validável por `pg_restore --list` e config
  criptografada com `age`.
- `apply-retention.sh` remove artefatos antigos mantendo a janela configurada.
- Falha de backup gera log `CRITICAL` com `BACKUP_FAILED`.
- Scripts com final de linha LF e sintaxe válida (`bash -n`).
- Evidência real na VPS/B2/R2 registrada como tarefa operacional do operador.
