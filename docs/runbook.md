# Runbook Operacional — Rei do Feno

> **Encerramento da Fase 2B:** ver
> [`docs/audit/fase-2b-conclusao.md`](audit/fase-2b-conclusao.md).
>
> **Nota de fase:** o alvo da Fase 2A é PostgreSQL **local na VPS**
> (ADR-001). A partir da Fase 3, o caminho recomendado é a stack
> `infra/docker-compose.yml` com Caddy; as seções de Render abaixo permanecem
> como blueprint legado. Em qualquer host, o contrato é
> `DATABASE_URL` PostgreSQL com TLS e `REDIS_URL` com incremento atômico.
> O proxy reverso deve preservar o IP do cliente em `REMOTE_ADDR`; não
> confie em `X-Forwarded-For` de origem não controlada (SEC-03/rate limit).
> No compose, isso é feito com PROXY protocol entre Caddy e Gunicorn.

## 1. Visão geral

- **Aplicação**: monólito Django (`config`), Gunicorn + WhiteNoise.
- **Banco**: PostgreSQL local na VPS (ADR-001), TLS obrigatório.
- **Cache**: Redis local na VPS, obrigatório para rate limiting atômico.
- **Mídia**: Cloudflare R2 ou S3 (django-storages, `DJANGO_FILE_STORAGE`).
- **Monitoramento**: Sentry (erros) + UptimeRobot (uptime em `/healthz/`).

## 2. Deploy

### Docker Compose + Caddy (Fase 3, recomendado)

1. Provisionar a VPS com Docker Engine + Compose v2 e liberar 80/443.
2. Copiar `.env.docker.example` para `.env.docker` e preencher os segredos.
   Copiar `infra/.env.example` para `infra/.env` e ajustar `APP_DOMAIN`,
   `STAGING_DOMAIN`, `ACME_EMAIL`, `HSTS_MAX_AGE=31536000` e `DB_PASSWORD`.
3. Apontar o DNS de `APP_DOMAIN` e `STAGING_DOMAIN` para a VPS **antes** de
   subir o Caddy (a emissão Let's Encrypt depende disso).
4. Subir a stack com migrations automáticas e cron:
   `docker compose -f infra/docker-compose.yml --profile cron up -d --build`.
5. Conferir `docker compose -f infra/docker-compose.yml ps` (todos
   `healthy`), `docker compose -f infra/docker-compose.yml logs caddy` e
   `curl -I https://SEU-DOMINIO/healthz/`.
6. Executar
   `docker compose -f infra/docker-compose.yml exec web python manage.py seed_groups`
   e criar o superusuário. Em seguida, seguir o inventário/backfill da seção 3.
7. Preservar os volumes `pgdata`, `caddy_data` e `caddy_config` em backup. A
   recriação de `caddy_data` força nova emissão de certificados.

O Caddy preserva `REMOTE_ADDR` via PROXY protocol; não publique a porta 8000
do serviço `web` em produção. O acesso HTTP é redirecionado para HTTPS e o
CSP/HSTS ficam no proxy, com defesa em profundidade no Django.

### VPS (procedimento manual legado)

1. Provisionar PostgreSQL 15 com TLS e Redis 7 com persistência adequada.
2. Definir `DATABASE_URL`, `REDIS_URL`, `DJANGO_SECRET_KEY`, domínios,
   `MERCADOPAGO_COLLECTOR_ID`, `MERCADOPAGO_LIVE_MODE=True` e demais
   segredos do quadro da seção 3.
3. Executar `python manage.py migrate --noinput`,
   `python manage.py collectstatic --noinput` e `python manage.py seed_groups`.
   Depois, rodar `python manage.py reconstruir_obrigacoes_estoque` em dry-run;
   usar `--aplicar` somente após revisar o relatório. Pendências `ambigua` ou
   `excesso` não podem ser resolvidas pelo serviço de faltante: usar
   `python manage.py conciliar_obrigacao_historica <id> --decisao ... --movimento <id>
   --usuario <username> --justificativa "..."` (primeiro sem `--confirmar`) com ator
   Administrador/Gestor. A conciliação registra antes/depois, cria no máximo uma
   alocação global por movimento e não cria movimento. Movimento já alocado a outro
   pedido é recusado; conflitos históricos aparecem em `conflitos_alocacao` e
   permanecem pendentes. O comando de reconstrução relê e trava cada obrigação antes
   de gravar.
   Bases **povoadas exatamente na `sales/0001`** não são suportadas para
   atualização automática (limitação pré-existente da `sales/0002`); usar backup
   e importação para um ponto suportado ou intervenção DBA autorizada, com
   validação específica do procedimento.
4. Subir Gunicorn atrás de Nginx/HTTPS, garantindo que o proxy preserve o
   IP real em `REMOTE_ADDR` e bloqueie acesso direto ao backend.
5. Configurar os jobs da seção 6 em systemd timers (ou cron) e o webhook do
   Mercado Pago em `https://SEU-DOMINIO/webhook/pagamentos/`.
6. Executar `python manage.py inventariar_legado --json` e conciliar os
   vínculos/pagamentos apontados antes de liberar histórico/fiscal. Pedidos
   legados só avançam após
   `python manage.py reconciliar_pedido_financeiro <numero> --justificativa "..."`.

### Atualização de estoque/obrigações

Ordem relevante: `sales/0009` → `sales/0010` → `stock/0009` → `sales/0011` →
`sales/0012` → `stock/0010` → `stock/0011`. O `migrate --noinput` aplica a ordem
do grafo; não execute migrations isoladas fora das dependências.

Pontos de partida suportados: banco vazio, banco em `817d1e8` (com `sales/0002`
aplicada) e banco já em `sales/0009`/`0011`. **U04:** base povoada exatamente na
`sales/0001`, com pedido em separação e pagamento aprovado, não tem atualização
automática garantida; ver a limitação e o caminho DBA/importação em
`docs/specs/fase-2b-remediation.md`.

Antes de aplicar, fazer backup/inventário e conferir `showmigrations`; depois:

```bash
python manage.py reconstruir_obrigacoes_estoque
python manage.py reconstruir_obrigacoes_estoque --aplicar
python manage.py conciliar_obrigacao_historica <id> --decisao atribuir \
  --movimento <id> --usuario <username> --justificativa "conferência" --confirmar
```

O primeiro comando é dry-run; o segundo relê/trava cada obrigação e registra
antes/depois. Conflitos `conflitos_alocacao` não devem ser resolvidos por SQL ou
editando JSON; use a conciliação explícita ou nova evidência física legítima.
Uma nova baixa só é válida quando há movimento/estoque físico correspondente.

**Neon QA:** o projeto `twilight-silence-34012623` permanece como QA temporário,
com dados sintéticos e sem dependência de produção. Finalidade: QA; responsável e
retenção não informados nesta documentação. Não excluir nem alterar credenciais
sem autorização operacional específica. Roles de migration/runtime, ownership e
restore de produção não foram verificados nesta fase.

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

**VPS (alvo):** `pg_dump` diário + retenção externa (S3/R2). Redis é cache
efêmero; a fonte da verdade continua no PostgreSQL.

**Render (legado):** backups diários gerenciados + cron semanal do script
`scripts/backup_db.sh "$DATABASE_URL"` exportando `.sql.gz` ao storage
externo.

**Procedimento de restore — não executado nesta consolidação:** o estado de
restore é **não verificado** nesta rodada. Antes do go-live, executar em ambiente
descartável, com autorização e janela próprias:
```bash
createdb reidofeno_restore
gunzip -c backups/reidofeno-YYYYMMDD-HHMMSS.sql.gz | psql "$DATABASE_URL_RESTORE"
# Apontar um serviço temporário para a URL de restore e validar:
#   /healthz/, login admin, contagem de pedidos/notas, emissão de teste no Bling sandbox.
```
Registrar data, tamanho, contagens e responsável em
`docs/relatorios/backup-restore.md`. A ausência desse registro significa restore
não comprovado; não trate o procedimento acima como ensaio concluído.

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
