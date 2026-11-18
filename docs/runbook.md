# Runbook Operacional e de Emergência — Rei do Feno

> **Documentos relacionados:**
> [`docs/audit/fase-2b-conclusao.md`](audit/fase-2b-conclusao.md) ·
> [`docs/incidentes.md`](incidentes.md) ·
> [`ADR-019 (Estratégia de Backup)`](adrs/ADR-019-estrategia-backup.md) ·
> [`ADR-020 (2FA Perfis Internos)`](adrs/ADR-020-2fa-perfis-internos.md) ·
> [`Template DRILL`](runbook/templates/drill-report.md) ·
> [`Template Incidente`](runbook/templates/incident-report.md)
>
> **Nota de arquitetura:** PostgreSQL **local na VPS** (ADR-001) e stack
> `infra/docker-compose.yml` com Caddy. Em qualquer host, o contrato exige
> `DATABASE_URL` PostgreSQL com TLS e `REDIS_URL` com incremento atômico.
> O proxy reverso deve preservar o IP real em `REMOTE_ADDR` via PROXY protocol
> (SEC-03/rate limit), nunca confiando em `X-Forwarded-For` externo.

---

## 1. Visão geral

- **Aplicação:** Monólito Django (`config`), Gunicorn + WhiteNoise.
- **Banco:** PostgreSQL 15 local na VPS (ADR-001), TLS obrigatório em produção.
- **Cache:** Redis 7 local na VPS, obrigatório para rate limiting atômico.
- **Mídia:** Volume persistente `media` (`media:/app/media` e `media:/srv/media:ro`).
- **Autenticação interna:** Login em `/accounts/login/` com 2FA TOTP obrigatório
  para `Administrador`, `Gestor`, `Emissor Fiscal`, `Financeiro` e superusuários
  (`/accounts/2fa/setup/` e `/accounts/2fa/verify/`, ver [`ADR-020`](adrs/ADR-020-2fa-perfis-internos.md)).
- **Backup noturno e offsite:** [`infra/backup/backup.sh`](../infra/backup/backup.sh) +
  [`infra/backup/restore.sh`](../infra/backup/restore.sh) (ver [`ADR-019`](adrs/ADR-019-estrategia-backup.md)).
- **Observabilidade:** Sentry (`send_default_pii=False`, filtro LGPD, 10% traces/profiles)
  e UptimeRobot monitorando `/healthz/`.

---

## 2. Contatos de Emergência

> Preencher os telefones e e-mails reais no cofre de senhas do operador antes do
> go-live de **23/11/2026** (nunca versionar números pessoais ou segredos no Git).

| Papel | Responsável | Contato principal | Escalonamento |
|---|---|---|---|
| Dono / Aprovador | Nilton | `[DEFINIR NO COFRE]` | WhatsApp / Ligação |
| Operação / Estoque | Neto | `[DEFINIR NO COFRE]` | WhatsApp |
| Emissor Fiscal / Financeiro | Caio | `[DEFINIR NO COFRE]` | WhatsApp |
| Operador Técnico / DevOps | `[DEFINIR]` | `[DEFINIR NO COFRE]` | Sentry / UptimeRobot |
| Provedor VPS | InterServer | Painel cliente InterServer | Ticket 24x7 |
| DNS / Storage Offsite | Cloudflare (DNS + R2) / Backblaze B2 | Painel da conta | Chave `age` no cofre |
| Pagamentos / NF-e | Mercado Pago / Bling / IOB | Painel parceiro | Suporte comercial |

---

## 3. Árvore de Decisão Rápida

```text
Alerta recebido (UptimeRobot / Sentry / WhatsApp interno)
  ├── /healthz/ não responde ou retorna 502/503?
  │     ├── database="error" ──→ Seção 4.2 (Banco fora / corrupção)
  │     ├── cache="error"    ──→ Reiniciar Redis (docker compose restart redis)
  │     └── Caddy / web fora ──→ Seção 4.1 (Site fora / 502)
  ├── Disco > 85% (df -h)?    ──→ Seção 4.3 (Disco cheio)
  ├── Alerta BACKUP_FAILED?   ──→ Seção 4.4 (Backup falhou)
  ├── Suspeita de invasão?    ──→ Seção 4.5 (Vazamento / Contenção SEV1)
  ├── Operador perdeu 2FA?    ──→ Seção 4.6 (Perda de acesso 2FA)
  └── Bug após deploy recente?──→ Seção 6.2 (Rollback de emergência)
```

---

## 4. Procedimentos de Emergência (SEV1–SEV3)

Ver classificação detalhada em [`docs/incidentes.md`](incidentes.md) e registrar
qualquer SEV1/SEV2 no [`template de incidente`](runbook/templates/incident-report.md).

### 4.1 Site fora / Erro 502

1. Conferir estado dos containers e healthchecks:
   ```bash
   docker compose -f infra/docker-compose.yml ps
   curl -i http://127.0.0.1:8000/healthz/
   ```
2. Inspecionar logs recentes de `caddy` e `web`:
   ```bash
   docker compose -f infra/docker-compose.yml logs --tail=150 caddy web
   ```
3. Se `web` travou ou OOM-killed (`free -m`), reiniciar o serviço:
   ```bash
   docker compose -f infra/docker-compose.yml restart web caddy
   ```
4. Se o erro começou logo após deploy, executar rollback imediato (Seção 6.2).
5. Se a VPS inteira estiver irrecuperável por mais de 30 minutos, acionar o
   Plano de Fuga Render + Neon (Seção 6.3).

### 4.2 Banco fora ou corrupção

1. Verificar saúde do PostgreSQL e espaço em disco:
   ```bash
   docker compose -f infra/docker-compose.yml exec db pg_isready -U reidofeno
   docker compose -f infra/docker-compose.yml logs --tail=100 db
   df -h
   ```
2. Tentar restart controlado do banco e `web`:
   ```bash
   docker compose -f infra/docker-compose.yml restart db web
   ```
3. Se houver corrupção ou perda de dados, **não sobrescrever** o volume sem
   snapshot de segurança; restaurar o último dump válido seguindo a Seção 5
   (`infra/backup/restore.sh`) e executar `python manage.py validar_restore`.

### 4.3 Disco cheio

1. Diagnosticar consumo de disco e volumes:
   ```bash
   df -h
   du -sh /var/backups/reidofeno /var/log/reidofeno /var/lib/docker/* 2>/dev/null
   ```
2. Limpar imagens/cache Docker antigos **sem remover volumes ativos** (`-v` é proibido):
   ```bash
   docker image prune -af --filter "until=168h"
   docker builder prune -af --filter "until=168h"
   ```
3. Aplicar retenção local de backups (`7` diários, `4` semanais, `3` mensais):
   ```bash
   bash infra/backup/apply-retention.sh /var/backups/reidofeno
   ```
4. Truncar logs grandes apenas se necessário (`truncate -s 0 ...` fora de `LogAuditoria`,
   pois a auditoria no banco é append-only).

### 4.4 Backup falhou

1. Inspecionar o log estruturado de backup e procurar `CRITICAL: BACKUP_FAILED`:
   ```bash
   tail -n 100 /var/log/reidofeno/backup.log
   ```
2. Causas comuns:
   - **`pg_dump failed` / `dump inválido`:** verificar `db` ativo e espaço em `/var/backups/reidofeno`.
   - **`rclone upload failed` / `checksum mismatch`:** testar conectividade com
     `rclone lsd "$BACKUP_REMOTE"` e credenciais R2/B2.
   - **`age encryption failed`:** validar `BACKUP_AGE_RECIPIENT` no ambiente do cron.
3. Reexecutar o backup manualmente e confirmar `SUCCESS:`:
   ```bash
   sudo bash /opt/reidofeno/infra/backup/backup.sh
   ```
4. Caso o runner precise emitir alerta direto ao Sentry em falha manual:
   ```bash
   docker compose -f infra/docker-compose.yml exec -T web \
     python manage.py reportar_backup_falha --motivo "rclone_failed"
   ```

### 4.5 Vazamento ou suspeita de invasão (SEV1)

1. **Contenção imediata:**
   - Rotacionar `DJANGO_SECRET_KEY`, `DB_PASSWORD`, tokens Mercado Pago/Bling,
     credenciais R2/B2 e senhas de administradores.
   - Revogar sessões ativas e forçar novo login + 2FA.
2. **Preservação de evidências:**
   - Exportar logs do Caddy/web e preservar registros de `LogAuditoria` e
     `PagamentoWebhookEvento` (nunca editar ou apagar auditoria).
3. **Recuperação:**
   - Restaurar dump limpo anterior à janela de comprometimento, se aplicável.
4. **Conformidade LGPD:**
   - Avaliar impacto aos titulares e acionar o plano de notificação da ANPD/titulares
     previsto em [`docs/incidentes.md`](incidentes.md).

### 4.6 Perda de acesso 2FA

1. Usuários dos grupos `Administrador`, `Gestor`, `Emissor Fiscal`, `Financeiro`
   e superusuários não acessam o sistema sem TOTP após o login em `/accounts/login/`.
2. **Primeira opção (usuário):** utilizar um dos **10 códigos de backup** de uso
   único gerados na ativação em `/accounts/2fa/verify/` (marcando uso de código
   de backup).
3. **Segunda opção (outro Administrador):** outro usuário do grupo `Administrador`
   (auto-reset é bloqueado) acessa `/admin/accounts/usuario/`, seleciona o
   usuário e executa a ação **Resetar 2FA (exige outro Administrador)**, ou via
   endpoint `/accounts/2fa/reset/<user_id>/` com justificativa obrigatória.
   A ação grava `accounts.2fa_resetado` em `LogAuditoria`.
4. **Emergência total (único Administrador sem códigos de backup):** somente com
   acesso SSH ao servidor e justificativa registrada em incidente:
   ```bash
   docker compose -f infra/docker-compose.yml exec web python manage.py shell -c "
   from accounts.models import Usuario
   from django_otp.plugins.otp_totp.models import TOTPDevice
   from django_otp.plugins.otp_static.models import StaticDevice
   u = Usuario.objects.get(username='ADMIN_USERNAME')
   TOTPDevice.objects.filter(user=u).delete()
   StaticDevice.objects.filter(user=u).delete()
   "
   ```
   No próximo login, o usuário será redirecionado automaticamente para `/accounts/2fa/setup/`.

---

## 5. Backup Noturno e DRILL de Restauração

### 5.1 Backup noturno (`ADR-019`)

- **Script principal:** [`infra/backup/backup.sh`](../infra/backup/backup.sh)
- **Retenção local:** [`infra/backup/apply-retention.sh`](../infra/backup/apply-retention.sh)
  (7 diários, 4 semanais de domingo, 3 mensais do dia 1).
- **Agendamento cron (VPS):** [`infra/backup/cron.d/reidofeno-backup`](../infra/backup/cron.d/reidofeno-backup)
  executa diariamente às **02:30**.
- **Artefatos gerados por execução:**
  - `db-<STAMP>.dump` (`pg_dump -Fc`, validado com `pg_restore --list`).
  - `media-<STAMP>.tar.gz` (volume `media`).
  - `config-<STAMP>.tar.gz.age` (`.env*`, `infra/docker-compose.yml`, `infra/Caddyfile`,
    criptografado com `age` usando chave pública do operador).
- **Integridade offsite:** cálculo e comparação SHA-256 local vs remoto via `rclone`.

### 5.2 DRILL de Restauração

Executar mensalmente (e obrigatoriamente antes do go-live de 23/11/2026) em
ambiente descartável, **nunca** sobrescrevendo o banco de produção sem aprovação:

1. Baixar o último backup offsite (ou usar snapshot local):
   ```bash
   rclone copy "$BACKUP_REMOTE/<STAMP>" /tmp/drill-restore/
   ```
2. Executar o script automatizado [`infra/backup/restore.sh`](../infra/backup/restore.sh):
   ```bash
   bash infra/backup/restore.sh \
     --dump /tmp/drill-restore/db-<STAMP>.dump \
     --media /tmp/drill-restore/media-<STAMP>.tar.gz \
     --config /tmp/drill-restore/config-<STAMP>.tar.gz.age
   ```
3. Executar validação de integridade de domínio dentro do ambiente restaurado:
   ```bash
   docker compose -f infra/docker-compose.yml exec -T web \
     python manage.py validar_restore --json
   ```
   O comando verifica reconciliação do ledger (`MovimentoEstoque.delta`),
   reservas ativas vs `quantidade_bloqueada`, snapshot de CMV (`ItemPedido.custo_unitario`)
   e contagens mínimas de pedidos, produtos, estoques e notas fiscais.
4. Validar `/healthz/` retornando HTTP `200` com `database="ok"` e `cache="ok"`,
   login com 2FA em `/accounts/login/`, `/gestao/pedidos/`, `/gestao/conciliacao/`
   e `/fiscal/notas/`.
5. Registrar evidência, RTO observado e responsável no template
   [`docs/runbook/templates/drill-report.md`](runbook/templates/drill-report.md).

---

## 6. Deploy, Rollback e Plano de Fuga

### 6.1 Deploy Docker Compose + Caddy (VPS)

> **Escopo atual:** scripts e compose validados em CI/local; publicação real na
> VPS e DNS público permanecem pendentes de execução operacional.

1. Provisionar VPS (InterServer) com Docker Engine + Compose v2 e portas `80`/`443`.
2. Copiar `.env.docker.example` para `.env.docker` e `infra/.env.example` para
   `infra/.env`, preenchendo segredos reais (`DJANGO_ENVIRONMENT=production`,
   `DATABASE_SSL_REQUIRE=True`, `DJANGO_HSTS_SECONDS=31536000`, `SENTRY_DSN`,
   credenciais MP/Bling/PostgreSQL).
3. Apontar DNS para a VPS **antes** de subir Caddy (Let's Encrypt).
4. Subir a stack:
   ```bash
   docker compose -f infra/docker-compose.yml --profile cron up -d --build
   ```
5. Verificar saúde e logs:
   ```bash
   docker compose -f infra/docker-compose.yml ps
   curl -fsS https://SEU-DOMINIO/healthz/
   ```
6. Na primeira instalação, executar `seed_groups` e criar usuário administrador:
   ```bash
   docker compose -f infra/docker-compose.yml exec web python manage.py seed_groups
   docker compose -f infra/docker-compose.yml exec web python manage.py createsuperuser
   ```
7. Instalar o cron de backup em `/etc/cron.d/reidofeno-backup` e configurar
   `BACKUP_AGE_RECIPIENT` e `BACKUP_REMOTE` no host.

**Limites conhecidos antes de produção:**

- O PostgreSQL interno do Compose não possui TLS configurado por padrão; produção
  estrita exige `DATABASE_SSL_REQUIRE=True` com TLS ativo no banco.
- `APP_DOMAIN` e `STAGING_DOMAIN` compartilham a mesma instância quando no mesmo Compose.
- Push em `main` executa CI (não há CD automático).
- Não publicar a porta `8000` diretamente; todo tráfego passa pelo Caddy com PROXY protocol.

### 6.2 Rollback de emergência (VPS)

1. Identificar o commit estável anterior (`git log -n 5 --oneline`).
2. Reverter o código para a tag/SHA anterior e reconstruir `web` e `cron`:
   ```bash
   git checkout <SHA_ESTAVEL>
   docker compose -f infra/docker-compose.yml --profile cron up -d --build web cron
   ```
3. Se o deploy falho aplicou migration destrutiva (incompatível com o código anterior),
   restaurar o dump pré-deploy usando `infra/backup/restore.sh` (Seção 5.2).
4. Confirmar `/healthz/` HTTP `200` e ausência de novos erros no Sentry.

### 6.3 Plano de Fuga (Render + Neon)

Caso a VPS InterServer fique indisponível por falha de infraestrutura prolongada:

1. Provisionar banco PostgreSQL no **Neon** (`twilight-silence-34012623` permanece
   apenas como QA temporário; criar projeto/branch dedicado para produção).
2. Restaurar o último dump offsite `db-<STAMP>.dump` no Neon:
   ```bash
   pg_restore --no-owner --no-acl -d "$NEON_DATABASE_URL" db-<STAMP>.dump
   ```
3. Subir o serviço web no **Render** usando [`render.yaml`](../render.yaml)
   ("New Blueprint"), configurando `DATABASE_URL`, `REDIS_URL`, `DJANGO_SECRET_KEY`,
   `MERCADOPAGO_*`, `SENTRY_DSN` e `DJANGO_SETTINGS_MODULE=config.settings.production`.
4. Validar `/healthz/` no domínio temporário do Render, atualizar o webhook do
   Mercado Pago e apontar o DNS na Cloudflare para o Render até a VPS voltar.

### 6.4 Smoke descartável de homologação

```bash
cp .env.docker.smoke.example .env.docker.smoke
cp infra/.env.smoke.example infra/.env.smoke
IMAGE_TAG=local docker compose --project-name reidofeno -f infra/docker-compose.yml build web
IMAGE_TAG=local bash infra/scripts/smoke-stack.sh
IMAGE_TAG=local bash infra/scripts/test-smoke-isolation.sh
```

O harness usa locks (`/tmp/reidofeno_smoke.lock` e `/tmp/reidofeno-smoke-isolation.lock`)
e nunca remove volumes/containers de desenvolvimento.

---

## 7. Variáveis de ambiente e Observabilidade

| Variável | Uso |
|---|---|
| `DJANGO_SECRET_KEY` | Chave secreta do Django |
| `DATABASE_URL` | PostgreSQL (TLS obrigatório em produção) |
| `REDIS_URL` | Redis para cache e rate limiting atômico |
| `DJANGO_ALLOWED_HOSTS` / `CSRF_TRUSTED_ORIGINS` / `SITE_URL` | Domínios autorizados |
| `MERCADOPAGO_ACCESS_TOKEN` / `MERCADOPAGO_WEBHOOK_SECRET` | Pagamento online |
| `MERCADOPAGO_COLLECTOR_ID` / `MERCADOPAGO_LIVE_MODE` | Validação de recebedor |
| `BLING_API_KEY` | Integração fiscal legada |
| `SENTRY_DSN` / `SENTRY_TRACES_RATE` / `SENTRY_PROFILES_RATE` / `APP_RELEASE` | Sentry (`before_send` remove CPF/CNPJ/e-mail) |
| `EMAIL_*` / `DEFAULT_FROM_EMAIL` | SMTP transacional e alertas |
| `BACKUP_REMOTE` / `BACKUP_AGE_RECIPIENT` | Destino `rclone` e chave pública `age` |

### Monitoramento e alertas

| Fonte | Regra recomendada | Ação |
|---|---|---|
| UptimeRobot | `GET https://SEU-DOMINIO/healthz/` a cada 5 min (`"status": "ok"`) | Alerta após 2 checagens falhas |
| Sentry | `send_default_pii=False`, 10% traces/profiles, filtro LGPD | Alerta em novo issue `error`/`fatal` |
| Backup log | `grep -q "CRITICAL: BACKUP_FAILED" /var/log/reidofeno/backup.log` | Acionar Seção 4.4 |

---

## 8. Rotinas agendadas e legadas

| Rotina | Comando | Frequência |
|---|---|---|
| Expirar pedidos pendentes | `python manage.py expirar_pedidos` | 15 min (`supercronic`) |
| Fila fiscal (NF-e) | `python manage.py processar_fiscal` | 30 min (`supercronic`) |
| Avisos comerciais | `python manage.py gerar_avisos_comerciais` | Diário 08:00 (`supercronic`) |
| Limpeza retenção fiscal (5 anos) | `python manage.py limpar_notas_expiradas` | Mensal/sob demanda (`--dry-run` antes) |
| Backup noturno + offsite | `infra/backup/backup.sh` | Diário 02:30 (cron host) |

**Atualização de estoque/obrigações legadas:** nunca aplicar migrations fora da
ordem do grafo (`migrate --noinput`). Bases povoadas exatamente na `sales/0001`
não possuem atualização automática suportada (ver `docs/specs/fase-2b-remediation.md`).
Quando aplicável, executar `reconstruir_obrigacoes_estoque` em dry-run antes de
`--aplicar` e `conciliar_obrigacao_historica` com `--usuario` e `--justificativa`.

---

## 9. Fluxos Operacionais da Fase 4 (Pagamento Manual e NF-e Assistida)

1. **Pagamento manual:** vendedor abre `/gestao/pedidos/<pk>/`, registra PIX/dinheiro/cartão
   com comprovante (JPG/PNG/PDF até 5 MB). Ao fechar saldo, pedido fica `pago` com
   `financeiro_conciliado=False`.
2. **Conciliação financeira:** perfil `Financeiro` (com 2FA) acessa `/gestao/conciliacao/`.
   **Conciliar** libera separação; **Rejeitar** exige justificativa e preserva estoque
   (rejeição financeira não é devolução física).
3. **NF-e assistida (IOB):** perfil `Emissor Fiscal` (com 2FA) exporta dados em
   `/fiscal/notas/`, emite no IOB, anexa PDF em `/fiscal/pedidos/<pk>/nota-anexar/`
   e confirma número/chave em `/fiscal/notas/` com **Autorizar**.

---

## 10. Checklists Pré-Deploy, Pós-Deploy e Go-Live (23/11/2026)

### Checklist Pré-Deploy

- [ ] CI verde no commit alvo (`ruff`, `pytest` + PostgreSQL/Redis, `bandit`, `pip-audit`, `docker`).
- [ ] Backup manual realizado antes de qualquer migration de produção (`infra/backup/backup.sh`).
- [ ] Revisar `makemigrations --check --dry-run` e compatibilidade reversa de migrations.
- [ ] Conferir `.env.docker` e `infra/.env` sem valores de staging (`DEBUG=False`, `DATABASE_SSL_REQUIRE=True`).

### Checklist Pós-Deploy

- [ ] `GET /healthz/` retornando `200` com `status=ok`, `database=ok`, `cache=ok`.
- [ ] Login com 2FA TOTP validado em `/accounts/login/` e `/accounts/2fa/verify/`.
- [ ] Teste de fumaça em `/gestao/pedidos/`, `/gestao/conciliacao/` e `/fiscal/notas/`.
- [ ] Evento de teste capturado no Sentry sem PII (CPF/CNPJ/e-mail mascarados).

### Checklist Go-Live (23/11/2026)

- [ ] Contatos reais da Seção 2 preenchidos no cofre da equipe.
- [ ] `DEBUG=False`, `SECRET_KEY` forte e `DATABASE_SSL_REQUIRE=True` ativos.
- [ ] HTTPS público com Caddy + Let's Encrypt validado.
- [ ] UptimeRobot monitorando `/healthz/` (5 min, alerta ativo).
- [ ] Sentry recebendo eventos com `send_default_pii=False`.
- [ ] Backup noturno ativo às 02:30 + envio offsite R2/B2 validado com SHA-256.
- [ ] Chave `age` de descriptografia guardada fora da VPS no cofre do operador.
- [ ] **DRILL de restauração executado** e registrado em `docs/runbook/templates/drill-report.md`.
- [ ] Todos os usuários `Administrador`, `Gestor`, `Emissor Fiscal` e `Financeiro` com 2FA TOTP ativado e códigos de backup guardados.
- [ ] Aceite humano dos fluxos pelo cliente (Nilton, Neto e Caio).
