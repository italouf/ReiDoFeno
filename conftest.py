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


@pytest.fixture(scope="session", autouse=True)
def _force_login_com_otp():
    """Preserva testes unitários que usam force_login para perfis com 2FA."""
    from django.test import Client
    from django_otp import DEVICE_ID_SESSION_KEY
    from django_otp.plugins.otp_totp.models import TOTPDevice

    from accounts.services import usuario_exige_2fa

    original_force_login = Client.force_login

    def _wrapped_force_login(self, user, backend=None, otp_verified=True):
        original_force_login(self, user, backend=backend)
        if otp_verified and getattr(user, "pk", None) and usuario_exige_2fa(user):
            device, _ = TOTPDevice.objects.get_or_create(
                user=user,
                name="test-auto",
                defaults={"confirmed": True},
            )
            if not device.confirmed:
                device.confirmed = True
                device.save(update_fields=["confirmed"])
            sessao = self.session
            sessao[DEVICE_ID_SESSION_KEY] = device.persistent_id
            sessao.save()

    Client.force_login = _wrapped_force_login
    yield
    Client.force_login = original_force_login


@pytest.fixture(autouse=True)
def limpar_cache_entre_testes():
    """Evita que contadores de rate limit vazem entre testes."""
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()
