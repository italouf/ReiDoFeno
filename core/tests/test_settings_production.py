"""ADR-001: produção exige PostgreSQL e TLS, sem fallback SQLite."""

import json
import os
import subprocess
import sys

from django.test import SimpleTestCase


class ProducaoPostgresTests(SimpleTestCase):
    def _executar(self, *, database_url=None, extra_env=None):
        env = os.environ.copy()
        env["DJANGO_SETTINGS_MODULE"] = "config.settings.production"
        env["DJANGO_SECRET_KEY"] = "chave-de-teste-segura"
        env["DJANGO_ALLOWED_HOSTS"] = "testserver"
        env.pop("DATABASE_URL", None)
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
            "'sslmode': db.get('OPTIONS', {}).get('sslmode')"
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
