from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from accounts.models import Usuario


class LoginTests(TestCase):
    def setUp(self):
        self.url_login = reverse("accounts:login")
        self.usuario = Usuario.objects.create_user(
            username="gestor", password="senha-forte-123"
        )

    def test_login_valido_redireciona(self):
        resposta = self.client.post(
            self.url_login,
            {"username": "gestor", "password": "senha-forte-123"},
        )
        self.assertEqual(resposta.status_code, 302)

    def test_login_invalido_usa_mensagem_generica(self):
        resposta = self.client.post(
            self.url_login,
            {"username": "gestor", "password": "senha-errada"},
        )
        self.assertEqual(resposta.status_code, 200)
        texto = resposta.content.decode()
        self.assertIn("Usuário ou senha incorretos", texto)
        self.assertNotIn("não existe", texto.lower())

    def test_mensagem_igual_para_usuario_inexistente(self):
        resposta_existente = self.client.post(
            self.url_login, {"username": "gestor", "password": "errada"}
        )
        resposta_inexistente = self.client.post(
            self.url_login, {"username": "fantasma", "password": "errada"}
        )
        self.assertEqual(resposta_existente.status_code, resposta_inexistente.status_code)
        self.assertIn("Usuário ou senha incorretos", resposta_inexistente.content.decode())

    def test_bloqueio_temporario_apos_limite_tentativas(self):
        from django.conf import settings

        limite = settings.AXES_FAILURE_LIMIT
        ultima_resposta = None
        for _ in range(limite):
            ultima_resposta = self.client.post(
                self.url_login, {"username": "gestor", "password": "errada"}
            )
        self.assertEqual(ultima_resposta.status_code, 429)

        nova_tentativa_bloqueada = self.client.post(
            self.url_login, {"username": "gestor", "password": "errada"}
        )
        self.assertEqual(nova_tentativa_bloqueada.status_code, 429)

    def test_logout_por_post_redireciona_para_login(self):
        self.client.force_login(self.usuario)
        resposta = self.client.post(reverse("accounts:logout"))
        self.assertEqual(resposta.status_code, 302)
        self.assertIn("/accounts/login/", resposta["Location"])


class RecuperacaoSenhaTests(TestCase):
    def setUp(self):
        self.usuario = Usuario.objects.create_user(
            username="vendedor",
            email="vendedor@reidofeno.com.br",
            password="senha-forte-123",
        )

    def test_envia_email_para_usuario_existente(self):
        resposta = self.client.post(
            reverse("accounts:password_reset"), {"email": self.usuario.email}
        )
        self.assertRedirects(resposta, reverse("accounts:password_reset_done"))
        self.assertEqual(len(mail.outbox), 1)

    def test_nao_revela_usuario_inexistente(self):
        resposta = self.client.post(
            reverse("accounts:password_reset"), {"email": "ninguem@example.com"}
        )
        self.assertRedirects(resposta, reverse("accounts:password_reset_done"))
        self.assertEqual(len(mail.outbox), 0)

    def test_fluxo_completo_de_redefinicao(self):
        uidb64 = urlsafe_base64_encode(force_bytes(self.usuario.pk))
        token = default_token_generator.make_token(self.usuario)
        url_confirmacao = reverse(
            "accounts:password_reset_confirm", args=[uidb64, token]
        )

        # O Django faz um redirect interno para .../set-password/ quando o link é válido.
        pagina = self.client.get(url_confirmacao, follow=True)
        self.assertEqual(pagina.status_code, 200)

        nova_senha = "nova-senha-muito-forte-456"
        url_definicao = reverse(
            "accounts:password_reset_confirm", args=[uidb64, "set-password"]
        )
        conclusao = self.client.post(
            url_definicao,
            {"new_password1": nova_senha, "new_password2": nova_senha},
            follow=True,
        )
        self.assertEqual(conclusao.status_code, 200)
        self.assertTemplateUsed(
            conclusao, "registration/password_reset_complete.html"
        )

        login_ok = self.client.post(
            reverse("accounts:login"),
            {"username": "vendedor", "password": nova_senha},
        )
        self.assertEqual(login_ok.status_code, 302)
