"""ADR-001: produção exige PostgreSQL e TLS, sem fallback SQLite."""

import json
import os
import subprocess
import sys
from unittest import mock

from django.test import SimpleTestCase

# Somente o necessário para o interpretador iniciar. Nenhuma variável de
# contrato do Django/Compose pode vazar do processo pai.
_AMBIENTE_SISTEMA = (
    "PATH",
    "SYSTEMROOT",
    "SYSTEMDRIVE",
    "WINDIR",
    "COMSPEC",
    "PATHEXT",
    "TEMP",
    "TMP",
    "HOME",
    "LANG",
    "LC_ALL",
)

_BASE_PRODUCAO = {
    "DJANGO_SETTINGS_MODULE": "config.settings.production",
    "DJANGO_ENVIRONMENT": "production",
    "DJANGO_SECRET_KEY": (
        "chave-de-teste-producao-com-mais-de-50-caracteres-1234567890"
    ),
    "DJANGO_ALLOWED_HOSTS": "testserver",
    "DATABASE_SSL_REQUIRE": "True",
    "MERCADOPAGO_COLLECTOR_ID": "collector-teste",
    "MERCADOPAGO_LIVE_MODE": "True",
    "MERCADO_PAGO_FAKE": "False",
    "BLING_FAKE": "False",
    "REDIS_URL": "redis://localhost:6379/1",
    "SMOKE_DIAGNOSTICS": "False",
}


class ProducaoPostgresTests(SimpleTestCase):
    def _ambiente_base(self):
        env = {
            chave: os.environ[chave]
            for chave in _AMBIENTE_SISTEMA
            if chave in os.environ
        }
        env.update(_BASE_PRODUCAO)
        return env

    def _executar(self, *, database_url=None, extra_env=None):
        env = self._ambiente_base()
        if database_url is not None:
            env["DATABASE_URL"] = database_url
        if extra_env:
            env.update(extra_env)

        codigo = (
            "import django, json; django.setup(); "
            "from django.conf import settings; "
            "db = settings.DATABASES['default']; "
            "print('RESULT:' + json.dumps({"
            "'engine': db['ENGINE'], "
            "'sslmode': db.get('OPTIONS', {}).get('sslmode'), "
            "'staging': settings.STAGING, "
            "'smoke_diagnostics': settings.SMOKE_DIAGNOSTICS"
            "}))"
        )
        return subprocess.run(
            [sys.executable, "-c", codigo],
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )

    def _dados(self, resultado):
        linha = next(
            linha
            for linha in resultado.stdout.splitlines()
            if linha.startswith("RESULT:")
        )
        return json.loads(linha.removeprefix("RESULT:"))

    def test_sem_database_url_falha(self):
        resultado = self._executar()

        self.assertNotEqual(resultado.returncode, 0)
        self.assertIn("DATABASE_URL", resultado.stderr + resultado.stdout)

    def test_sqlite_e_rejeitado_em_producao(self):
        resultado = self._executar(database_url="sqlite:///tmp/proibido.sqlite3")

        self.assertNotEqual(resultado.returncode, 0)
        self.assertIn("PostgreSQL", resultado.stderr + resultado.stdout)

    def test_postgres_exige_ssl(self):
        resultado = self._executar(
            database_url="postgres://usuario:senha@localhost:5432/reidofeno"
        )

        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        linha = next(
            linha
            for linha in resultado.stdout.splitlines()
            if linha.startswith("RESULT:")
        )
        dados = json.loads(linha.removeprefix("RESULT:"))
        self.assertEqual(dados["engine"], "django.db.backends.postgresql")
        self.assertEqual(dados["sslmode"], "require")

    def test_sslmode_disable_na_url_e_sobrescrito(self):
        resultado = self._executar(
            database_url=(
                "postgres://usuario:senha@localhost:5432/reidofeno"
                "?sslmode=disable"
            )
        )

        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        linha = next(
            linha
            for linha in resultado.stdout.splitlines()
            if linha.startswith("RESULT:")
        )
        dados = json.loads(linha.removeprefix("RESULT:"))
        self.assertEqual(dados["sslmode"], "require")

    def test_fake_pagamento_falha_em_producao(self):
        resultado = self._executar(
            database_url="postgres://usuario:senha@localhost:5432/reidofeno",
            extra_env={"MERCADO_PAGO_FAKE": "True"},
        )

        self.assertNotEqual(resultado.returncode, 0)
        self.assertIn(
            "MERCADO_PAGO_FAKE", resultado.stderr + resultado.stdout
        )

    def test_fake_fiscal_falha_em_producao(self):
        resultado = self._executar(
            database_url="postgres://usuario:senha@localhost:5432/reidofeno",
            extra_env={"BLING_FAKE": "True"},
        )

        self.assertNotEqual(resultado.returncode, 0)
        self.assertIn("BLING_FAKE", resultado.stderr + resultado.stdout)

    def test_sem_redis_url_falha_em_producao(self):
        resultado = self._executar(
            database_url="postgres://usuario:senha@localhost:5432/reidofeno",
            extra_env={"REDIS_URL": ""},
        )

        self.assertNotEqual(resultado.returncode, 0)
        self.assertIn("REDIS_URL", resultado.stderr + resultado.stdout)

    def test_sem_collector_falha_em_producao(self):
        resultado = self._executar(
            database_url="postgres://usuario:senha@localhost:5432/reidofeno",
            extra_env={"MERCADOPAGO_COLLECTOR_ID": ""},
        )

        self.assertNotEqual(resultado.returncode, 0)
        self.assertIn(
            "MERCADOPAGO_COLLECTOR_ID", resultado.stderr + resultado.stdout
        )

    def test_live_mode_falso_falha_em_producao(self):
        resultado = self._executar(
            database_url="postgres://usuario:senha@localhost:5432/reidofeno",
            extra_env={"MERCADOPAGO_LIVE_MODE": "False"},
        )

        self.assertNotEqual(resultado.returncode, 0)
        self.assertIn(
            "MERCADOPAGO_LIVE_MODE", resultado.stderr + resultado.stdout
        )

    def test_producao_rejeita_database_sem_tls(self):
        resultado = self._executar(
            database_url="postgres://usuario:senha@localhost:5432/reidofeno",
            extra_env={"DATABASE_SSL_REQUIRE": "False"},
        )

        self.assertNotEqual(resultado.returncode, 0)
        self.assertIn(
            "DATABASE_SSL_REQUIRE", resultado.stderr + resultado.stdout
        )

    def test_staging_permite_postgres_interno_sem_tls_e_fake(self):
        resultado = self._executar(
            database_url="postgres://usuario:senha@db:5432/reidofeno",
            extra_env={
                "DJANGO_ENVIRONMENT": "staging",
                "DATABASE_SSL_REQUIRE": "False",
                "MERCADO_PAGO_FAKE": "True",
                "BLING_FAKE": "True",
                "MERCADOPAGO_COLLECTOR_ID": "",
                "MERCADOPAGO_LIVE_MODE": "False",
            },
        )

        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        dados = self._dados(resultado)
        self.assertIsNone(dados["sslmode"])
        self.assertTrue(dados["staging"])

    def test_baseline_producao_ignora_staging_do_ambiente_pai(self):
        contaminado = {
            "DJANGO_SETTINGS_MODULE": "config.settings.development",
            "DJANGO_ENVIRONMENT": "staging",
            "DATABASE_SSL_REQUIRE": "False",
            "MERCADO_PAGO_FAKE": "True",
            "BLING_FAKE": "True",
            "MERCADOPAGO_COLLECTOR_ID": "",
            "MERCADOPAGO_LIVE_MODE": "False",
        }

        with mock.patch.dict(os.environ, contaminado, clear=False):
            resultado = self._executar(
                database_url=(
                    "postgres://usuario:senha@localhost:5432/reidofeno"
                )
            )

        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        dados = self._dados(resultado)
        self.assertEqual(dados["sslmode"], "require")
        self.assertFalse(dados["staging"])

    def test_baseline_producao_ignora_database_url_do_ambiente_pai(self):
        with mock.patch.dict(
            os.environ,
            {"DATABASE_URL": "sqlite:///tmp/herdado.sqlite3"},
            clear=False,
        ):
            resultado = self._executar()

        self.assertNotEqual(resultado.returncode, 0)
        self.assertIn("DATABASE_URL", resultado.stderr + resultado.stdout)

    def test_baseline_producao_ignora_fakes_do_ambiente_pai(self):
        with mock.patch.dict(
            os.environ,
            {"MERCADO_PAGO_FAKE": "True", "BLING_FAKE": "True"},
            clear=False,
        ):
            resultado = self._executar(
                database_url=(
                    "postgres://usuario:senha@localhost:5432/reidofeno"
                )
            )

        self.assertEqual(resultado.returncode, 0, resultado.stderr)

    def test_smoke_diagnostics_nao_e_habilitado_em_producao(self):
        resultado = self._executar(
            database_url="postgres://usuario:senha@localhost:5432/reidofeno",
            extra_env={"SMOKE_DIAGNOSTICS": "True"},
        )

        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.assertFalse(self._dados(resultado)["smoke_diagnostics"])

    def test_smoke_diagnostics_exige_staging_explicito(self):
        resultado = self._executar(
            database_url="postgres://usuario:senha@db:5432/reidofeno",
            extra_env={
                "DJANGO_ENVIRONMENT": "staging",
                "DATABASE_SSL_REQUIRE": "False",
                "SMOKE_DIAGNOSTICS": "True",
            },
        )

        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.assertTrue(self._dados(resultado)["smoke_diagnostics"])
