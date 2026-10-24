"""Settings de CI/testes de integração.

Exigem PostgreSQL real (e, quando ``REDIS_URL`` estiver definido, Redis real)
para reproduzir row-locks, constraints e contadores atômicos. O
desenvolvimento local continua usando ``config.settings.development`` (SQLite)
via ``pyproject.toml``.
"""
import os

import dj_database_url

from .base import *  # noqa: F401,F403

DEBUG = False

SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY", "test-secret-key-only-for-ci"
)

ALLOWED_HOSTS = ["localhost", "127.0.0.1", "testserver"]

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgres://reidofeno:reidofeno@localhost:5432/test_reidofeno",
).strip()
DATABASES = {
    "default": dj_database_url.parse(DATABASE_URL, conn_max_age=0)
}

REDIS_URL = os.environ.get("REDIS_URL", "").strip()
if REDIS_URL:
    CACHES = {
        "default": {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": REDIS_URL,
            "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        }
    }

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# Testes não precisam de hashing caro.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

SILENCED_SYSTEM_CHECKS = [
    "django_ratelimit.E003",
    "django_ratelimit.W001",
]

LOGGING = {
    "version": 1,
    "disable_existing_loggers": True,
}
