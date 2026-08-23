"""
Configurações base compartilhadas por todos os ambientes.
Segredos e parâmetros sensíveis vêm exclusivamente de variáveis de ambiente.
"""
import os
from datetime import timedelta
from pathlib import Path

import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-insecure-key")

DEBUG = False

ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get(
        "DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1"
    ).split(",")
    if host.strip()
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "whitenoise.runserver_nostatic",
    "django.contrib.staticfiles",
    # Apps locais
    "accounts.apps.AccountsConfig",
    "core.apps.CoreConfig",
    "catalog.apps.CatalogConfig",
    "customers.apps.CustomersConfig",
    "stock.apps.StockConfig",
    "sales.apps.SalesConfig",
    "costs.apps.CostsConfig",
    "fiscal.apps.FiscalConfig",
    "privacy.apps.PrivacyConfig",
    "analytics.apps.AnalyticsConfig",
    # Terceiros
    "axes",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "axes.middleware.AxesMiddleware",
    "core.middleware.SecurityHeadersMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

_database_url = os.environ.get("DATABASE_URL", "")

if _database_url:
    DATABASES = {
        "default": dj_database_url.config(
            default=_database_url,
            conn_max_age=600,
        )
    }
else:
    # SQLite local/dev: modo transacional imediato evita contenção de escrita
    # entre conexões (equivalente prático ao row-lock do PostgreSQL).
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
            "OPTIONS": {
                "transaction_mode": "IMMEDIATE",
                "init_command": (
                    "PRAGMA journal_mode=WAL;"
                    "PRAGMA busy_timeout=15000;"
                    "PRAGMA foreign_keys=ON;"
                ),
            },
        }
    }

AUTH_USER_MODEL = "accounts.Usuario"

AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
]

# Limitador de tentativas de login (django-axes)
AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = timedelta(minutes=15)
AXES_LOCKOUT_PARAMETERS = [["username", "ip_address"]]
AXES_RESET_ON_SUCCESS = True
AXES_VERBOSE = 0

LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/painel/painel/"
LOGOUT_REDIRECT_URL = "/accounts/login/"

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.ScryptPasswordHasher",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Bahia"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --------------------------------------------------------------------------- #
# Integrações externas
# --------------------------------------------------------------------------- #
MERCADO_PAGO_ACCESS_TOKEN = os.environ.get("MERCADOPAGO_ACCESS_TOKEN", "")
MERCADO_PAGO_WEBHOOK_SECRET = os.environ.get("MERCADOPAGO_WEBHOOK_SECRET", "")
MERCADO_PAGO_FAKE = (
    os.environ.get("MERCADO_PAGO_FAKE", "True").lower() == "true"
)
SITE_URL = os.environ.get("SITE_URL", "http://localhost:8000")

BLING_API_KEY = os.environ.get("BLING_API_KEY", "")
BLING_FAKE = os.environ.get("BLING_FAKE", "True").lower() == "true"
FISCAL_ALERTA_HORAS_SEM_NFE = int(
    os.environ.get("FISCAL_ALERTA_HORAS_SEM_NFE", "24")
)

# Cancelamento automático de pedidos aguardando pagamento (em minutos).
PEDIDO_TIMEOUT_MINUTOS = int(os.environ.get("PEDIDO_TIMEOUT_MINUTOS", "240"))

SENTRY_DSN = os.environ.get("SENTRY_DSN", "")
if SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[DjangoIntegration()],
        traces_sample_rate=float(
            os.environ.get("SENTRY_TRACES_RATE", "0.1")
        ),
        send_default_pii=False,
    )

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "sanitizar_pii": {
            "()": "core.logging_filters.SanitizePIIFilter",
        },
    },
    "formatters": {
        "json": {
            "()": "pythonjsonlogger.json.JsonFormatter",
            "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
            "filters": ["sanitizar_pii"],
        },
    },
    "root": {
        "handlers": ["console"],
        "level": os.environ.get("DJANGO_LOG_LEVEL", "INFO"),
    },
    "loggers": {
        "django": {"level": "INFO"},
        "axes": {"level": "WARNING"},
    },
}

RECOMPRA_DIAS = int(os.environ.get("RECOMPRA_DIAS", "30"))

CONTENT_SECURITY_POLICY = os.environ.get(
    "CONTENT_SECURITY_POLICY",
    "default-src 'self'; style-src 'self' 'unsafe-inline';"
    " img-src 'self' data:; frame-ancestors 'none'",
)
