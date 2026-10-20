"""R3: transições operacionais decidem com estado atual sob lock."""

from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.http import Http404
from django.test import TestCase
from django.urls import reverse

from accounts.models import Usuario
from sales.factories import PedidoFactory
from sales.models import Pedido
from sales.services import alterar_status_operacional


class TransicaoOperacionalTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_groups", verbosity=0)
        cls.senha = "senha-forte-123"
        cls.vendedor = Usuario.objects.create_user(
            username="vendedor-r3", password=cls.senha
        )
        cls.vendedor.groups.add(Group.objects.get(name="Vendedor"))
        cls.outro = Usuario.objects.create_user(
            username="outro-r3", password=cls.senha
        )
        cls.outro.groups.add(Group.objects.get(name="Vendedor"))
        cls.gestor = Usuario.objects.create_user(
            username="gestor-r3", password=cls.senha
        )
        cls.gestor.groups.add(Group.objects.get(name="Gestor"))

    def test_transicao_valida_usa_estado_atual_e_audita(self):
        pedido = PedidoFactory(
            usuario_criador=self.vendedor,
            status=Pedido.Status.AGUARDANDO_PAGAMENTO,
            status_financeiro=Pedido.StatusFinanceiro.PAGO,
        )

        atualizado = alterar_status_operacional(
            pedido.pk,
            Pedido.Status.EM_SEPARACAO,
            usuario=self.vendedor,
        )

        self.assertEqual(atualizado.status, Pedido.Status.EM_SEPARACAO)

    def test_instancia_antiga_nao_reabre_pedido_cancelado(self):
        pedido = PedidoFactory(
            usuario_criador=self.vendedor,
            status=Pedido.Status.AGUARDANDO_PAGAMENTO,
            status_financeiro=Pedido.StatusFinanceiro.PAGO,
        )
        # Simula o webhook cancelando/estornando depois da leitura do POST.
        Pedido.objects.filter(pk=pedido.pk).update(
            status=Pedido.Status.CANCELADO,
            status_financeiro=Pedido.StatusFinanceiro.ESTORNADO,
        )

        with self.assertRaises(ValidationError):
            alterar_status_operacional(
                pedido.pk,
                Pedido.Status.CONCLUIDO,
                usuario=self.vendedor,
            )

        pedido.refresh_from_db()
        self.assertEqual(pedido.status, Pedido.Status.CANCELADO)
        self.assertEqual(
            pedido.status_financeiro, Pedido.StatusFinanceiro.ESTORNADO
        )

    def test_vendedor_nao_altera_pedido_de_outro(self):
        pedido = PedidoFactory(
            usuario_criador=self.outro,
            status=Pedido.Status.AGUARDANDO_PAGAMENTO,
            status_financeiro=Pedido.StatusFinanceiro.PAGO,
        )

        with self.assertRaises(Http404):
            alterar_status_operacional(
                pedido.pk,
                Pedido.Status.EM_SEPARACAO,
                usuario=self.vendedor,
            )

    def test_view_nao_reabre_pedido_cancelado_com_estado_antigo(self):
        pedido = PedidoFactory(
            usuario_criador=self.vendedor,
            status=Pedido.Status.AGUARDANDO_PAGAMENTO,
            status_financeiro=Pedido.StatusFinanceiro.PAGO,
        )
        self.client.force_login(self.vendedor)
        Pedido.objects.filter(pk=pedido.pk).update(
            status=Pedido.Status.CANCELADO,
            status_financeiro=Pedido.StatusFinanceiro.ESTORNADO,
        )

        resposta = self.client.post(
            reverse("sales:pedido_atualizar_status", args=[pedido.pk]),
            {"status": Pedido.Status.CONCLUIDO},
        )

        self.assertEqual(resposta.status_code, 302)
        pedido.refresh_from_db()
        self.assertEqual(pedido.status, Pedido.Status.CANCELADO)
        self.assertEqual(
            pedido.status_financeiro, Pedido.StatusFinanceiro.ESTORNADO
        )
