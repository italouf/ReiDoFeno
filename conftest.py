import pytest


def pytest_collection_modifyitems(config, items):
    """Testes marcados como ``postgres`` só rodam contra PostgreSQL real."""
    from django.db import connection

    if connection.vendor == "postgresql":
        return
    marcador = pytest.mark.skip(reason="Requer PostgreSQL real (CI).")
    for item in items:
        if "postgres" in item.keywords:
            item.add_marker(marcador)


@pytest.fixture(autouse=True)
def limpar_cache_entre_testes():
    """Evita que contadores de rate limit vazem entre testes."""
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()
