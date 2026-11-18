"""Testes de /healthz/ e /healthz/ip/."""
from unittest.mock import patch

from django.db import OperationalError
from django.test import SimpleTestCase, TestCase, override_settings


class HealthzIPTests(SimpleTestCase):
    @override_settings(SMOKE_DIAGNOSTICS=False)
    def test_rota_nao_existe_fora_do_smoke(self):
        resposta = self.client.get("/healthz/ip/")

        self.assertEqual(resposta.status_code, 404)

    @override_settings(SMOKE_DIAGNOSTICS=True)
    def test_retorna_remote_addr_e_ignora_x_forwarded_for(self):
        resposta = self.client.get(
            "/healthz/ip/",
            REMOTE_ADDR="198.51.100.10",
            HTTP_X_FORWARDED_FOR="203.0.113.99",
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(
            resposta.json(), {"remote_addr": "198.51.100.10"}
        )


class HealthzTests(TestCase):
    def test_healthz_ok(self):
        resposta = self.client.get("/healthz/")

        self.assertEqual(resposta.status_code, 200)
        dados = resposta.json()
        self.assertEqual(dados["status"], "ok")
        self.assertEqual(dados["database"], "ok")
        self.assertEqual(dados["cache"], "ok")
        self.assertTrue(dados["timestamp"])

    def test_healthz_db_down_retorna_503(self):
        with patch(
            "core.views.connection.cursor",
            side_effect=OperationalError("postgres://user:secret@10.0.0.5/db"),
        ):
            resposta = self.client.get("/healthz/")

        self.assertEqual(resposta.status_code, 503)
        dados = resposta.json()
        self.assertEqual(dados["status"], "error")
        self.assertEqual(dados["database"], "error")
        self.assertEqual(dados["cache"], "ok")

    def test_healthz_redis_down_retorna_503(self):
        with patch(
            "core.views.cache.set",
            side_effect=ConnectionError("redis://:secret@redis:6379/0"),
        ):
            resposta = self.client.get("/healthz/")

        self.assertEqual(resposta.status_code, 503)
        dados = resposta.json()
        self.assertEqual(dados["status"], "error")
        self.assertEqual(dados["database"], "ok")
        self.assertEqual(dados["cache"], "error")

    def test_healthz_nao_expoe_info_sensivel(self):
        with (
            patch(
                "core.views.connection.cursor",
                side_effect=OperationalError(
                    "postgres://reidofeno:supersecret@db:5432/reidofeno"
                ),
            ),
            patch(
                "core.views.cache.set",
                side_effect=ConnectionError("redis://:senhasecreta@redis:6379/0"),
            ),
        ):
            resposta = self.client.get("/healthz/")

        corpo = resposta.content.decode("utf-8").lower()
        for termo in ("postgres://", "redis://", "supersecret", "senhasecreta", "traceback"):
            self.assertNotIn(termo, corpo)
