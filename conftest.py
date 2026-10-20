import pytest


@pytest.fixture(autouse=True)
def limpar_cache_entre_testes():
    """Evita que contadores de rate limit vazem entre testes."""
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()
