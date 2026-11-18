# Observabilidade — Healthcheck completo, Sentry sem PII e UptimeRobot

**Fase:** 5
**Status:** Implementada
**Depende de:** `core/views.py` (`/healthz/`), `core/logging_filters.py` (`SanitizePIIFilter`), `config/settings/base.py`.

## Objetivo

Garantir detecção rápida de indisponibilidade e exceções em produção sem vazar
dados pessoais (LGPD) ou detalhes internos de infraestrutura.

## Especificação

1. **Endpoint `/healthz/` (`core.views.healthz`):**
   - Executa `SELECT 1` na conexão padrão do Django para validar PostgreSQL.
   - Executa `cache.set` + `cache.get` com chave efêmera (`healthz:ping`) para
     validar Redis/cache configurado.
   - Retorna JSON:
     ```json
     {
       "status": "ok",
       "timestamp": "2026-11-18T00:00:00+00:00",
       "database": "ok",
       "cache": "ok"
     }
     ```
   - Retorna HTTP `200` quando ambos estão saudáveis e HTTP `503` quando
     `database == "error"` ou `cache == "error"`.
   - Exceções são registradas apenas em log interno (`reidofeno.healthz`); a
     resposta HTTP nunca expõe tracebacks, URLs de conexão ou caminhos internos.
   - Permanece público e isento de `OTPRequiredMiddleware` e redirecionamento
     HTTPS interno (`SECURE_REDIRECT_EXEMPT`).

2. **Sentry SDK com filtro de PII (`core.logging_filters.filter_pii_event`):**
   - Inicializado quando `SENTRY_DSN` estiver definido (`config.settings.base` /
     `configurar_sentry`).
   - `integrations=[DjangoIntegration(), RedisIntegration()]`.
   - `traces_sample_rate=0.1` (`SENTRY_TRACES_RATE`, padrão `0.1`).
   - `profiles_sample_rate=0.1` (`SENTRY_PROFILES_RATE`, padrão `0.1`).
   - `send_default_pii=False`.
   - `environment=DJANGO_ENVIRONMENT` e `release=APP_RELEASE`.
   - `before_send=filter_pii_event` sanitiza recursivamente strings em
     `message`, `logentry`, `exception`, `breadcrumbs`, `request`, `extra`,
     `contexts` e `tags`, mascarando CPF, CNPJ (numérico e alfanumérico) e
     e-mails sem alterar `SanitizePIIFilter` (`[DOC-REMOVIDO]`).

3. **Monitoramento externo (UptimeRobot — execução operacional):**
   - Monitor HTTPS em `/healthz/` a cada 5 minutos, buscando status HTTP 200 e
     palavra-chave `"status": "ok"`.
   - Alerta por e-mail/Telegram/SMS após 2 falhas consecutivas.
