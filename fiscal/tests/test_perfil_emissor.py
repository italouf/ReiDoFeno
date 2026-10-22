"""Perfil Emissor Fiscal: acesso fiscal sem acesso à gestão."""

from django.contrib.auth.models import Group, Permission
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from accounts.models import Usuario
from fiscal.models import NotaFiscal
from sales.factories import PedidoFactory
from sales.models import Pedido


class PerfilEmissorFiscalTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_groups", verbosity=0)
        cls.emissor = Usuario.objects.create_user(
            username="caio_teste", password="senha-forte-123"
        )
        cls.emissor.groups.add(Group.objects.get(name="Emissor Fiscal"))
        cls.pedido = PedidoFactory(
            status=Pedido.Status.PAGO, subtotal="100.00", total="100.00"
        )

    def test_emissor_pode_acessar_nota_manual(self):
        self.client.force_login(self.emissor)
        resposta = self.client.get(
            reverse("fiscal:nota_manual", args=[self.pedido.pk])
        )
        self.assertEqual(resposta.status_code, 200)

    def test_emissor_pode_registrar_nota_manual(self):
        self.client.force_login(self.emissor)
        resposta = self.client.post(
            reverse("fiscal:nota_manual", args=[self.pedido.pk]),
            {
                "numero": "9001",
                "chave_acesso": "29260812345678901234567890123456789012345678",
            },
            follow=True,
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertTrue(
            NotaFiscal.objects.filter(
                pedido=self.pedido, tipo=NotaFiscal.Tipo.SAIDA
            ).exists()
        )

    def test_emissor_nao_pode_editar_status_do_pedido(self):
        self.client.force_login(self.emissor)
        resposta = self.client.get(
            reverse("sales:pedido_atualizar_status", args=[self.pedido.pk])
        )
        self.assertEqual(resposta.status_code, 403)

    def test_emissor_nao_acessa_painel_global(self):
        self.client.force_login(self.emissor)
        resposta = self.client.get(reverse("core:painel"))
        self.assertEqual(resposta.status_code, 403)

    def test_emissor_pode_exportar_relatorio_fiscal(self):
        self.client.force_login(self.emissor)
        resposta = self.client.get(
            reverse("fiscal:relatorio_fiscal"), {"formato": "csv"}
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta["Content-Type"], "text/csv")

    def test_grupo_tem_permissoes_fiscais_sem_edicao_de_pedido(self):
        grupo = Group.objects.get(name="Emissor Fiscal")
        codenames = set(
            Permission.objects.filter(group=grupo).values_list(
                "codename", flat=True
            )
        )

        self.assertIn("view_notafiscal", codenames)
        self.assertIn("add_notafiscal", codenames)
        self.assertIn("change_notafiscal", codenames)
        self.assertIn("view_pedido", codenames)
        self.assertNotIn("change_pedido", codenames)
        self.assertNotIn("add_pedido", codenames)
        self.assertNotIn("change_produto", codenames)
        self.assertNotIn("change_cliente", codenames)
        self.assertNotIn("change_estoque", codenames)
