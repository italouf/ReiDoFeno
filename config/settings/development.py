"""Configurações de desenvolvimento."""
from .base import *  # noqa: F401,F403

DEBUG = True

ALLOWED_HOSTS = ["localhost", "127.0.0.1", "testserver"]

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# Em desenvolvimento o storage de estáticos não exige hash no nome do arquivo.
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

INTERNAL_IPS = ["127.0.0.1"]

# Estáticos ao vivo no runserver (WhiteNoise lê dos finders e reindexa).
WHITENOISE_USE_FINDERS = True
WHITENOISE_AUTOREFRESH = True
