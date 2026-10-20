"""Rate limiting dos endpoints críticos (SEC-04)."""

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse


class LoginRateLimitTests(TestCase):
    def setUp(self):
        cache.clear()
        self.url = reverse("accounts:login")

    def _post_invalido(self):
        return self.client.post(
            self.url,
            {"username": "usuario_invalido", "password": "senha_invalida"},
        )

    def test_sexta_tentativa_em_um_minuto_retorna_429(self):
        for tentativa in range(1, 6):
            with self.subTest(tentativa=tentativa):
                resposta = self._post_invalido()
                self.assertEqual(resposta.status_code, 200)

        resposta = self._post_invalido()

        self.assertEqual(resposta.status_code, 429)
        self.assertIn("Retry-After", resposta.headers)
        self.assertGreaterEqual(int(resposta.headers["Retry-After"]), 1)

    def test_get_nao_consome_o_limite(self):
        for _ in range(10):
            self.assertEqual(self.client.get(self.url).status_code, 200)

        self.assertEqual(self._post_invalido().status_code, 200)


class CheckoutRateLimitTests(TestCase):
    def setUp(self):
        cache.clear()
        self.url = reverse("sales:checkout")

    def test_decima_primeira_submissao_em_uma_hora_retorna_429(self):
        for submissao in range(1, 11):
            with self.subTest(submissao=submissao):
                resposta = self.client.post(self.url, {})
                self.assertEqual(resposta.status_code, 200)

        resposta = self.client.post(self.url, {})

        self.assertEqual(resposta.status_code, 429)
        self.assertIn("Retry-After", resposta.headers)
        self.assertGreaterEqual(int(resposta.headers["Retry-After"]), 1)

    def test_limite_e_por_sessao(self):
        from django.test import Client

        for _ in range(10):
            self.client.post(self.url, {})
        self.assertEqual(self.client.post(self.url, {}).status_code, 429)

        outra_sessao = Client()
        self.assertEqual(outra_sessao.post(self.url, {}).status_code, 200)

    def test_limite_por_ip_entre_sessoes(self):
        from django.test import Client

        for _ in range(3):
            sessao = Client()
            for _ in range(10):
                self.assertEqual(sessao.post(self.url, {}).status_code, 200)

        nova_sessao = Client()
        self.assertEqual(nova_sessao.post(self.url, {}).status_code, 429)


class WebhookRateLimitTests(TestCase):
    def setUp(self):
        cache.clear()
        self.url = reverse("sales:webhook")

    @override_settings(MERCADO_PAGO_WEBHOOK_SECRET="segredo-teste")
    def test_sexagesima_primeira_requisicao_em_um_minuto_retorna_429(self):
        for requisicao in range(1, 61):
            with self.subTest(requisicao=requisicao):
                resposta = self.client.post(
                    self.url,
                    data="{}",
                    content_type="application/json",
                )
                self.assertEqual(resposta.status_code, 403)

        resposta = self.client.post(
            self.url,
            data="{}",
            content_type="application/json",
        )

        self.assertEqual(resposta.status_code, 429)
        self.assertIn("Retry-After", resposta.headers)
        self.assertGreaterEqual(int(resposta.headers["Retry-After"]), 1)
