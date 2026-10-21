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


def _permitir_truncate_em_testes(sender, connection, **kwargs):
    """Testes precisam truncar tabelas; produção não define este GUC."""
    if connection.vendor == "postgresql":
        with connection.cursor() as cursor:
            cursor.execute("SET stock.permitir_truncate = 'on'")


def pytest_configure(config):
    from django.db.backends.signals import connection_created

    connection_created.connect(
        _permitir_truncate_em_testes,
        dispatch_uid="permitir_truncate_em_testes",
    )


@pytest.fixture(autouse=True)
def limpar_cache_entre_testes():
    """Evita que contadores de rate limit vazem entre testes."""
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()
