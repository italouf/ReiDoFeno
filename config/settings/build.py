"""Settings usados apenas durante o build da imagem.

Não exigem banco, Redis ou integrações: servem para `collectstatic` gerar o
mesmo manifesto (hash + compressão) que `config.settings.production` espera.
"""

from .base import *  # noqa: F401,F403

DEBUG = False

# Build não tem Redis; o backend compartilhado é exigido apenas em runtime.
SILENCED_SYSTEM_CHECKS = [
    "django_ratelimit.E003",
    "django_ratelimit.W001",
]

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}
