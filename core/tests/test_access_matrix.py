from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from accounts.models import Usuario


class MatrizAcessoPainelTests(TestCase):
    """Matriz de acesso à área interna (espec access-control)."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_groups", verbosity=0)
        cls.senha = "senha-forte-123"
        cls.usuarios = {}
        for perfil in ("administrador", "gestor", "vendedor", "cliente"):
            usuario = Usuario.objects.create_user(
                username=perfil, password=cls.senha
            )
            grupo = Group.objects.get(name=perfil.capitalize())
            usuario.groups.add(grupo)
            cls.usuarios[perfil] = usuario

    def test_anonimo_e_redirecionado_para_login(self):
        resposta = self.client.get(reverse("core:painel"))
        self.assertEqual(resposta.status_code, 302)
        self.assertIn("/accounts/login/", resposta["Location"])

    def test_perfis_internos_acessam_painel(self):
        for perfil in ("administrador", "gestor", "vendedor"):
            with self.subTest(perfil=perfil):
                self.client.force_login(self.usuarios[perfil])
                resposta = self.client.get(reverse("core:painel"))
                self.assertEqual(resposta.status_code, 200)
                self.client.logout()

    def test_cliente_nao_acessa_painel_interno(self):
        self.client.force_login(self.usuarios["cliente"])
        resposta = self.client.get(reverse("core:painel"))
        self.assertEqual(resposta.status_code, 403)

    def test_gestor_nao_acessa_administracao_de_usuarios(self):
        self.client.force_login(self.usuarios["gestor"])
        resposta = self.client.get("/admin/")
        # Sem is_staff o gestor é levado ao login do admin, sem ver nada.
        self.assertEqual(resposta.status_code, 302)
        self.assertIn("/admin/login/", resposta["Location"])

    def test_healthz_publico_sem_autenticacao(self):
        resposta = self.client.get("/healthz/")
        self.assertEqual(resposta.status_code, 200)
