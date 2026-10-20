"""R6: cache de produção deve ter incremento atômico real."""

import os
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from django.test import SimpleTestCase, override_settings

REDIS_URL = os.environ.get("REDIS_URL", "")


@pytest.mark.skipif(
    not REDIS_URL,
    reason="REDIS_URL não configurado; teste de cache real roda no CI.",
)
@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": REDIS_URL,
            "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
        }
    }
)
class CacheAtomicoTests(SimpleTestCase):
    def test_incrementos_concorrentes_nao_perdem_atualizacao(self):
        from django.core.cache import cache

        cache.clear()
        cache.add("contador-r6", 0, timeout=30)
        barreira = threading.Barrier(10)

        def incrementar(_):
            barreira.wait(timeout=10)
            return cache.incr("contador-r6")

        with ThreadPoolExecutor(max_workers=10) as executor:
            list(executor.map(incrementar, range(10)))

        self.assertEqual(cache.get("contador-r6"), 10)
        cache.delete("contador-r6")
