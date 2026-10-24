# syntax=docker/dockerfile:1.6

# ─────────────────────────────────────────────────────────────
# Base compartilhada: Python slim + usuário não-privilegiado
# ─────────────────────────────────────────────────────────────
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TZ=America/Bahia

WORKDIR /app

RUN groupadd --gid 1000 app \
    && useradd --uid 1000 --gid app --create-home --shell /usr/sbin/nologin app

# ─────────────────────────────────────────────────────────────
# supercronic: cron não-root, binário estático verificado
# ─────────────────────────────────────────────────────────────
FROM alpine:3.20 AS supercronic

SHELL ["/bin/ash", "-eo", "pipefail", "-c"]

ARG SUPERCRONIC_VERSION=v0.2.51
ARG TARGETARCH

# hadolint ignore=DL3018
RUN apk add --no-cache curl \
    && case "${TARGETARCH:-amd64}" in \
        amd64) SHA256="cc232108374e8e2b537045f2d5eaa1229f619db314c3ba6a14d38b35dc0aa123" ;; \
        arm64) SHA256="4ae22576a78223d8ccdf5f3b3660a5cbb5288416bf0ca96afc4a36d195932b94" ;; \
        *) echo "TARGETARCH não suportado: ${TARGETARCH}" >&2; exit 1 ;; \
    esac \
    && curl -fsSLo /usr/local/bin/supercronic \
        "https://github.com/aptible/supercronic/releases/download/${SUPERCRONIC_VERSION}/supercronic-linux-${TARGETARCH:-amd64}" \
    && echo "${SHA256}  /usr/local/bin/supercronic" | sha256sum -c - \
    && chmod 0755 /usr/local/bin/supercronic

# ─────────────────────────────────────────────────────────────
# Builder: dependências de produção + collectstatic
# ─────────────────────────────────────────────────────────────
FROM base AS builder

# O --prefix=/install exige esse caminho no sys.path para o collectstatic.
ENV PYTHONPATH=/install/lib/python3.12/site-packages:/app \
    PATH="/install/bin:${PATH}"

# hadolint ignore=DL3008
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Layer cache: requirements mudam menos que o código.
COPY requirements.txt ./
RUN pip install --prefix=/install -r requirements.txt

COPY . .

# Usa o mesmo storage de estáticos da produção (manifest + compressão).
RUN DJANGO_SETTINGS_MODULE=config.settings.build \
    python manage.py collectstatic --noinput

# ─────────────────────────────────────────────────────────────
# Dev: builder + ferramentas de teste (usado pelo compose override)
# ─────────────────────────────────────────────────────────────
FROM builder AS dev

# Não enxergar /install: garante que requirements-dev seja instalado em
# /usr/local (o /install some ao montar o código no compose).
ENV PYTHONPATH=/app \
    PATH="/usr/local/bin:/usr/local/sbin:/usr/sbin:/usr/bin:/sbin:/bin"

COPY requirements-dev.txt ./
RUN pip install --prefix=/usr/local -r requirements-dev.txt

COPY --from=supercronic /usr/local/bin/supercronic /usr/local/bin/supercronic
COPY infra/crontab /etc/reidofeno/crontab
COPY --chmod=0755 infra/scripts/ /app/infra/scripts/

USER 1000:1000

EXPOSE 8000

# O override do compose substitui este healthcheck por HTTP direto
# (runserver não fala PROXY protocol).
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]

# ─────────────────────────────────────────────────────────────
# Runtime: imagem final mínima, somente dependências de execução
# ─────────────────────────────────────────────────────────────
FROM base AS runtime

ENV PATH="/usr/local/bin:${PATH}" \
    PYTHONPATH=/app \
    DJANGO_SETTINGS_MODULE=config.settings.production

# hadolint ignore=DL3008
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libpq5 \
        curl \
        tzdata \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /install /usr/local
COPY --from=supercronic /usr/local/bin/supercronic /usr/local/bin/supercronic

COPY --from=builder --chown=app:app /app /app
COPY --chown=app:app infra/scripts/ /app/infra/scripts/
COPY infra/crontab /etc/reidofeno/crontab

RUN chmod 0755 /app/infra/scripts/*.sh \
    && mkdir -p /app/media \
    && chown -R app:app /app/media

USER 1000:1000

EXPOSE 8000

# Gunicorn exige PROXY protocol; curl envia o cabeçalho v1.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["curl", "-fsS", "--haproxy-protocol", "-H", "Host: localhost", \
        "http://127.0.0.1:8000/healthz/"]

ENTRYPOINT ["/app/infra/scripts/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--threads", "2", "--timeout", "60", "--graceful-timeout", "30", "--keep-alive", "5", "--proxy-protocol=v1", "--proxy-allow-from=*", "--forwarded-allow-ips=*", "--access-logfile", "-", "--error-logfile", "-"]
