# ADR-019 — Estratégia de backup noturno e criptografia offsite

**Fase:** 5
**Status:** Aceita (substitui a numeração `ADR-018` citada no prompt da Fase 5,
pois `ADR-018-pagamento-manual.md` já foi atribuída na Fase 4).

## Contexto

O ReiDoFeno opera em VPS única (InterServer) com PostgreSQL 15 em container,
volume de mídia (comprovantes PIX e PDFs de NF-e com retenção de 5 anos) e
arquivos de configuração sensíveis (`.env.docker`, `infra/.env`, Caddy).
Um único script `scripts/backup_db.sh` existia como esboço legado sem validação
de dump, sem mídia, sem criptografia de segredos, sem envio offsite e sem
checagem de integridade.

## Decisão

1. **Formato de dump:** adotar `pg_dump -Fc` (formato custom comprimido),
   validado imediatamente após a geração com `pg_restore --list`, permitindo
   restore seletivo e verificação estrutural antes do upload.
2. **Mídia e documentos fiscais:** arquivar `/app/media` (ou bind-mount local)
   junto ao mesmo carimbo temporal do dump, preservando comprovantes da Fase 4
   e PDFs de NF-e (`retido_ate`).
3. **Criptografia de configurações com `age`:** `.env.docker`, `infra/.env`,
   `infra/docker-compose.yml` e `Caddyfile` são compactados e criptografados
   com chave pública `age` (`BACKUP_AGE_RECIPIENT`); o arquivo `.tar.gz` em
   claro é removido imediatamente após a criptografia e também em `trap` de
   saída. A chave privada fica exclusivamente no cofre do operador, nunca no
   repositório.
4. **Offsite via `rclone` (Cloudflare R2 ou Backblaze B2):** após upload, o
   script compara o SHA-256 local do `.dump` com o hash do objeto remoto via
   `rclone cat ... | sha256sum` antes de declarar sucesso.
5. **Retenção:** 7 dias locais no host; 30 dias diários e 12 meses mensais
   no bucket offsite (regra de lifecycle do provedor).
6. **Observabilidade de falhas:** erros em qualquer etapa gravam
   `CRITICAL: BACKUP_FAILED` no log local e acionam `reidofeno.backup` no
   Django (capturado pelo Sentry quando configurado).

## Consequências

- A restauração completa depende apenas do último dump `.dump`, do tarball de
  mídia, do pacote `.tar.gz.age` e da chave privada `age` do operador.
- Segredos de produção nunca trafegam nem repousam em claro no storage offsite.
- Sem chave `BACKUP_AGE_RECIPIENT` configurada em produção, o backup falha
  explicitamente (fail-closed) para evitar upload de `.env` sem criptografia.
