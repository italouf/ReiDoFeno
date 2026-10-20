# Runbook Operacional — Rei do Feno

> **Nota de fase:** o alvo da Fase 2A é PostgreSQL **local na VPS**
> (ADR-001). As seções de Render abaixo permanecem como blueprint legado
> até a migração de infraestrutura da Fase 3; em qualquer host, o contrato é
> `DATABASE_URL` PostgreSQL com TLS e `REDIS_URL` com incremento atômico.
> O proxy reverso deve preservar o IP do cliente em `REMOTE_ADDR`; não
> confie em `X-Forwarded-For` de origem não controlada (SEC-03/rate limit).

## 1. Visão geral

- **Aplicação**: monólito Django (`config`), Gunicorn + WhiteNoise.
- **Banco**: PostgreSQL local na VPS (ADR-001), TLS obrigatório.
- **Cache**: Redis local na VPS, obrigatório para rate limiting atômico.
- **Mídia**: Cloudflare R2 ou S3 (django-storages, `DJANGO_FILE_STORAGE`).
- **Monitoramento**: Sentry (erros) + UptimeRobot (uptime em `/healthz/`).

## 2. Deploy

### VPS (alvo da Fase 2A)

1. Provisionar PostgreSQL 15 com TLS e Redis 7 com persistência adequada.
2. Definir `DATABASE_URL`, `REDIS_URL`, `DJANGO_SECRET_KEY`, domínios,
   `MERCADOPAGO_COLLECTOR_ID`, `MERCADOPAGO_LIVE_MODE=True` e demais
   segredos do quadro da seção 3.
3. Executar `python manage.py migrate --noinput`,
   `python manage.py collectstatic --noinput` e `python manage.py seed_groups`.
4. Subir Gunicorn atrás de Nginx/HTTPS, garantindo que o proxy preserve o
   IP real em `REMOTE_ADDR` e bloqueie acesso direto ao backend.
5. Configurar os jobs da seção 6 em systemd timers (ou cron) e o webhook do
   Mercado Pago em `https://SEU-DOMINIO/webhook/pagamentos/`.
6. Executar `python manage.py inventariar_legado --json` e conciliar os
   vínculos/pagamentos apontados antes de liberar histórico/fiscal.

### Render (blueprint legado)

O `render.yaml` permanece como referência até a Fase 3. Se usado, ele
provê PostgreSQL gerenciado e Redis; os mesmos contratos de `DATABASE_URL`,
`REDIS_URL`, TLS e fake mode continuam obrigatórios.

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
| DATABASE_URL | PostgreSQL (local na VPS ou gerenciado), TLS obrigatório |
| DJANGO_ALLOWED_HOSTS / CSRF_TRUSTED_ORIGINS / SITE_URL | Domínios |
| MERCADOPAGO_ACCESS_TOKEN / MERCADOPAGO_WEBHOOK_SECRET | Pagamento |
| MERCADOPAGO_COLLECTOR_ID / MERCADOPAGO_LIVE_MODE | Recebedor e ambiente do pagamento |
| MERCADOPAGO_WEBHOOK_TOLERANCE_SECONDS | Tolerância do timestamp (padrão 300) |
| REDIS_URL | Cache compartilhado com incremento atômico |
| BLING_API_KEY | NF-e |
| SENTRY_DSN | Erros |
| EMAIL_* / DEFAULT_FROM_EMAIL | SMTP transacional |
| PEDIDO_TIMEOUT_MINUTOS / RECOMPRA_DIAS / FISCAL_ALERTA_HORAS_SEM_NFE | Regras operacionais |
| RATELIMIT_LOGIN / RATELIMIT_CHECKOUT / RATELIMIT_WEBHOOK | Limites (padrão: 5/m, 10/h, 60/m) |
| RATELIMIT_CHECKOUT_IP / RATELIMIT_PAGAMENTO | Limites por IP (padrão: 30/h, 10/m) |

## 4. Backups e restore

**VPS (alvo):** `pg_dump` diário + retenção externa (S3/R2), com teste de
restore periódico. Redis é cache efêmero; a fonte da verdade continua no
PostgreSQL.

**Render (legado):** backups diários gerenciados + cron semanal do script
`scripts/backup_db.sh "$DATABASE_URL"` exportando `.sql.gz` ao storage
externo.

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

## 6. Rotinas agendadas

Na VPS, usar systemd timers (ou cron) com as mesmas frequências. No Render
legado, os crons do blueprint continuam válidos.

| Rotina | Comando | Frequência |
|---|---|---|
| Expirar pedidos pendentes | `python manage.py expirar_pedidos` | 15 min |
| Fila fiscal (NF-e) | `python manage.py processar_fiscal` | 30 min |
| Avisos comerciais (recompra/pendências) | `python manage.py gerar_avisos_comerciais` | Diário 08:00 |
| Inventário de legado | `python manage.py inventariar_legado --json` | Semanal até conciliação |
| Backup lógico | `scripts/backup_db.sh` / `pg_dump` | Diário |

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
