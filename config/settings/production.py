"""Configurações de produção.

Requer variáveis de ambiente: DJANGO_SECRET_KEY, DJANGO_ALLOWED_HOSTS,
DATABASE_URL e, quando aplicável, CSRF_TRUSTED_ORIGINS e DJANGO_SECURE_SSL_REDIRECT.
"""
import os

import dj_database_url
from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401,F403
from .base import BASE_DIR

DEBUG = False

# Staging roda a mesma imagem/settings, mas permite integrações simuladas e
# PostgreSQL interno sem TLS. O default continua sendo produção estrita.
STAGING = os.environ.get("DJANGO_ENVIRONMENT", "production") == "staging"
SMOKE_DIAGNOSTICS = (
    STAGING
    and os.environ.get("SMOKE_DIAGNOSTICS", "False").lower() == "true"
)

SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]

# ADR-001: produção usa exclusivamente PostgreSQL, sem fallback SQLite.
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
if not DATABASE_URL:
    raise ImproperlyConfigured(
        "DATABASE_URL é obrigatório em produção (PostgreSQL)."
    )

DATABASE_SSL_REQUIRE = (
    os.environ.get("DATABASE_SSL_REQUIRE", "True").lower() == "true"
)
if not DATABASE_SSL_REQUIRE and not STAGING:
    raise ImproperlyConfigured(
        "DATABASE_SSL_REQUIRE=False só é permitido em staging "
        "(DJANGO_ENVIRONMENT=staging)."
    )

DATABASES = {
    "default": dj_database_url.parse(
        DATABASE_URL,
        conn_max_age=600,
        conn_health_checks=True,
        ssl_require=DATABASE_SSL_REQUIRE,
    )
}
if "postgresql" not in DATABASES["default"]["ENGINE"]:
    raise ImproperlyConfigured(
        "Produção exige PostgreSQL; DATABASE_URL aponta para outro banco."
    )
if DATABASE_SSL_REQUIRE:
    # Garante TLS mesmo se a URL trouxer sslmode=disable.
    DATABASES["default"].setdefault("OPTIONS", {})["sslmode"] = "require"

CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin.strip()
]

SECURE_SSL_REDIRECT = (
    os.environ.get("DJANGO_SECURE_SSL_REDIRECT", "True").lower() == "true"
)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True
USE_X_FORWARDED_PORT = True
# O healthcheck do container fala HTTP direto; o proxy redireciona o resto.
SECURE_REDIRECT_EXEMPT = [r"^healthz/$"]
SECURE_HSTS_SECONDS = int(
    os.environ.get("DJANGO_HSTS_SECONDS", str(60 * 60 * 24 * 365))
)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = SECURE_HSTS_SECONDS > 0
SECURE_REFERRER_POLICY = "same-origin"

SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_SECURE = True
X_FRAME_OPTIONS = "DENY"

STORAGES = {
    "default": {
        "BACKEND": os.environ.get(
            "DJANGO_FILE_STORAGE", "django.core.files.storage.FileSystemStorage"
        )
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
    },
}

EMAIL_BACKEND = os.environ.get(
    "EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend"
)
EMAIL_HOST = os.environ.get("EMAIL_HOST", "")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "True").lower() == "true"
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "")

STATIC_ROOT = BASE_DIR / "staticfiles"

# Rate limiting compartilhado e com incremento atômico (R6).
REDIS_URL = os.environ.get("REDIS_URL", "").strip()
if not REDIS_URL:
    raise ImproperlyConfigured(
        "REDIS_URL é obrigatório em produção para rate limiting atômico."
    )
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": REDIS_URL,
        "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
    }
}

# Em produção o adapter real é obrigatório, salvo override explícito.
MERCADO_PAGO_FAKE = (
    os.environ.get("MERCADO_PAGO_FAKE", "False").lower() == "true"
)
BLING_FAKE = os.environ.get("BLING_FAKE", "False").lower() == "true"

if MERCADO_PAGO_FAKE and not STAGING:
    raise ImproperlyConfigured(
        "MERCADO_PAGO_FAKE=True não é permitido em produção; "
        "o simulador aprova pagamentos sem provedor."
    )
if BLING_FAKE and not STAGING:
    raise ImproperlyConfigured(
        "BLING_FAKE=True não é permitido em produção."
    )

MERCADO_PAGO_COLLECTOR_ID = os.environ.get(
    "MERCADOPAGO_COLLECTOR_ID", ""
).strip()
if not MERCADO_PAGO_COLLECTOR_ID and not STAGING:
    raise ImproperlyConfigured(
        "MERCADOPAGO_COLLECTOR_ID é obrigatório em produção para "
        "validar o recebedor do pagamento."
    )
MERCADO_PAGO_LIVE_MODE = (
    os.environ.get("MERCADOPAGO_LIVE_MODE", "True").lower() == "true"
)
if not MERCADO_PAGO_LIVE_MODE and not STAGING:
    raise ImproperlyConfigured(
        "MERCADOPAGO_LIVE_MODE deve ser True em produção."
    )
