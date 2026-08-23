# Runbook Operacional — Rei do Feno

## 1. Visão geral

- **Aplicação**: monólito Django (`config`), Gunicorn + WhiteNoise.
- **Banco**: PostgreSQL gerenciado (Render).
- **Mídia**: Cloudflare R2 ou S3 (django-storages, `DJANGO_FILE_STORAGE`).
- **Monitoramento**: Sentry (erros) + UptimeRobot (uptime em `/healthz/`).

## 2. Deploy

Blueprint pronta: `render.yaml` (Web Service + PostgreSQL 15 + crons).

1. Conectar o repositório GitHub ao Render → "New Blueprint" → selecionar o repo.
2. Preencher as variáveis `sync: false` (secretos) listadas no blueprint.
3. Primeiro deploy cria banco e aplica migrations via build command.
4. Criar usuário administrativo:
   `python manage.py createsuperuser` (via Render Shell) e
   `python manage.py seed_groups`.
5. Apontar domínio próprio (Render → Settings → Custom Domains; HTTPS automático).
6. Configurar webhook do Mercado Pago para
   `https://SEU-DOMINIO/webhook/pagamentos/` com o mesmo segredo de
   `MERCADOPAGO_WEBHOOK_SECRET`.

### Rollback

No Render → deploys → "Rollback" para o build anterior imediato.
Migrations destrutivas exigem compatibilidade reversa (estratégia expand/contract).

## 3. Variáveis de ambiente mínimas

| Variável | Uso |
|---|---|
| DJANGO_SECRET_KEY | Segredo do Django |
| DATABASE_URL | Postgres gerenciado |
| DJANGO_ALLOWED_HOSTS / CSRF_TRUSTED_ORIGINS / SITE_URL | Domínios |
| MERCADOPAGO_ACCESS_TOKEN / MERCADOPAGO_WEBHOOK_SECRET | Pagamento |
| BLING_API_KEY | NF-e |
| SENTRY_DSN | Erros |
| EMAIL_* / DEFAULT_FROM_EMAIL | SMTP transacional |
| PEDIDO_TIMEOUT_MINUTOS / RECOMPRA_DIAS / FISCAL_ALERTA_HORAS_SEM_NFE | Regras operacionais |

## 4. Backups e restore

**Automático**: Render PostgreSQL (backups diários gerenciados) +
cron semanal do script `scripts/backup_db.sh "$DATABASE_URL"` exportando
`.sql.gz` ao storage externo.

**Restore testado (obrigatório antes do go-live):**
```bash
createdb reidofeno_restore
gunzip -c backups/reidofeno-YYYYMMDD-HHMMSS.sql.gz | psql "$DATABASE_URL_RESTORE"
# Apontar um serviço temporário para a URL de restore e validar:
#   /healthz/, login admin, contagem de pedidos/notas, emissão de teste no Bling sandbox.
```
Registrar evidência (data, tamanho, contagens) em `docs/relatorios/backup-restore.md`.

## 5. Monitoramento e alertas

| Fonte | Alerta |
|---|---|
| Sentry | Novo issue nível error → notificar canal da equipe |
| UptimeRobot | `/healthz/` a cada 5 min; down ≥ 2 checagens → SMS/e-mail |

## 6. Rotinas agendadas (crons do Render)

| Cron | Comando | Frequência |
|---|---|---|
| Expirar pedidos pendentes | `python manage.py expirar_pedidos` | 15 min |
| Fila fiscal (NF-e) | `python manage.py processar_fiscal` | 30 min |
| Avisos comerciais (recompra/pendências) | `python manage.py gerar_avisos_comerciais` | Diário 08:00 |
| Backup lógico | `scripts/backup_db.sh` | Diário |

## 7. Resposta a incidentes

Ver `docs/incidentes.md` (classificação SEV1–SEV3, papéis, comunicação,
post-mortem obrigatório para SEV1/SEV2).

## 8. Checklist de produção (go-live)

- [ ] `DEBUG=False` e `SECRET_KEY` forte definida
- [ ] HTTPS ativo e domínio próprio respondendo
- [ ] `/healthz/` monitorado (UptimeRobot)
- [ ] Sentry recebendo eventos de teste
- [ ] Webhook MP configurado + assinatura validada (teste real)
- [ ] Credenciais Bling de produção + certificado digital A1 disponível
- [ ] Backup automático ativo + **restore testado com evidência**
- [ ] Crons habilitados (expirar/fiscal/avisos)
- [ ] Usuários administrativos criados por grupo correto (sem superusuário no dia a dia)
- [ ] Política de privacidade revisada juridicamente publicada
