"""Configurações de produção.

Requer variáveis de ambiente: DJANGO_SECRET_KEY, DJANGO_ALLOWED_HOSTS,
DATABASE_URL e, quando aplicável, CSRF_TRUSTED_ORIGINS e DJANGO_SECURE_SSL_REDIRECT.
"""
import os

from .base import *  # noqa: F401,F403
from .base import BASE_DIR

DEBUG = False

SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]

CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin.strip()
]

SECURE_SSL_REDIRECT = (
    os.environ.get("DJANGO_SECURE_SSL_REDIRECT", "True").lower() == "true"
)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
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

# Em produção o adapter real é obrigatório, salvo override explícito.
MERCADO_PAGO_FAKE = (
    os.environ.get("MERCADO_PAGO_FAKE", "False").lower() == "true"
)
BLING_FAKE = os.environ.get("BLING_FAKE", "False").lower() == "true"
