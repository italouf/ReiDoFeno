"""Landing pós-login por papel (ADR-010 e Emissor Fiscal)."""

from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from accounts.models import Usuario


class PosLoginTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_groups", verbosity=0)

    def _usuario(self, username, grupo):
        usuario = Usuario.objects.create_user(
            username=username, password="senha-forte-123"
        )
        usuario.groups.add(Group.objects.get(name=grupo))
        return usuario

    def test_gestor_vai_para_painel(self):
        self.client.force_login(self._usuario("gestor_pos", "Gestor"))
        resposta = self.client.get(reverse("accounts:pos_login"))
        self.assertRedirects(
            resposta, reverse("core:painel"), fetch_redirect_response=False
        )

    def test_vendedor_vai_para_minhas_metricas(self):
        self.client.force_login(self._usuario("vend_pos", "Vendedor"))
        resposta = self.client.get(reverse("accounts:pos_login"))
        self.assertRedirects(
            resposta,
            reverse("sales:minhas_metricas"),
            fetch_redirect_response=False,
        )

    def test_emissor_vai_para_relatorio_fiscal(self):
        self.client.force_login(
            self._usuario("emissor_pos", "Emissor Fiscal")
        )
        resposta = self.client.get(reverse("accounts:pos_login"))
        self.assertRedirects(
            resposta,
            reverse("fiscal:relatorio_fiscal"),
            fetch_redirect_response=False,
        )

    def test_cliente_vai_para_loja(self):
        self.client.force_login(self._usuario("cliente_pos", "Cliente"))
        resposta = self.client.get(reverse("accounts:pos_login"))
        self.assertRedirects(
            resposta, "/", fetch_redirect_response=False
        )
