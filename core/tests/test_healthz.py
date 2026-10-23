"""Diagnóstico de IP usado exclusivamente pelo smoke de staging."""
from django.test import SimpleTestCase, override_settings


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

    def test_healthz_continua_publico_e_estavel(self):
        resposta = self.client.get("/healthz/")

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json(), {"status": "ok"})
