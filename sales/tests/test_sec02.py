"""SEC-02: checkout não pode reivindicar o cadastro de um cliente existente."""

from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from accounts.models import Usuario
from customers.factories import ClienteFactory
from customers.models import Cliente
from sales.factories import PedidoFactory
from sales.models import Pedido

from .helpers import DADOS_BASE, fluxo_checkout


class CheckoutNaoVinculaClienteTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_groups", verbosity=0)
        cls.senha = "senha-forte-123"
        cls.vendedor = Usuario.objects.create_user(
            username="vendedor-sec02", password=cls.senha
        )
        cls.vendedor.groups.add(Group.objects.get(name="Vendedor"))

    def test_checkout_nao_vincula_cliente_existente_por_documento(self):
        cliente = ClienteFactory(
            documento="52998224725",
            email=DADOS_BASE["email"],
        )

        pedido = fluxo_checkout(self.client, quantidade=1)

        cliente.refresh_from_db()
        self.assertIsNone(cliente.usuario)
        self.assertEqual(pedido.cliente, cliente)

    def test_checkout_cria_cliente_novo_sem_vincular_usuario(self):
        usuario = Usuario.objects.create_user(
            username="cliente-sec02",
            email="cliente-sec02@example.com",
            password=self.senha,
        )
        self.client.force_login(usuario)

        pedido = fluxo_checkout(self.client, quantidade=1)

        self.assertIsNone(pedido.cliente.usuario)

    def test_vendedor_cria_pedido_sem_ocupar_vinculo_do_cliente(self):
        cliente = ClienteFactory(
            documento="52998224725",
            email=DADOS_BASE["email"],
        )
        self.client.force_login(self.vendedor)

        pedido = fluxo_checkout(self.client, quantidade=2)

        self.assertEqual(pedido.usuario_criador, self.vendedor)
        self.assertEqual(pedido.canal, Pedido.Canal.VENDEDOR)
        cliente.refresh_from_db()
        self.assertIsNone(cliente.usuario)

    def test_meus_pedidos_so_mostra_pedidos_do_cliente_vinculado(self):
        usuario = Usuario.objects.create_user(
            username="titular-sec02", password=self.senha
        )
        meu_cliente = ClienteFactory(
            usuario=usuario, vinculo_verificado=True
        )
        outro_cliente = ClienteFactory()
        meu_pedido = PedidoFactory(
            cliente=meu_cliente, identidade_verificada=True
        )
        pedido_alheio = PedidoFactory(cliente=outro_cliente)

        self.client.force_login(usuario)
        resposta = self.client.get(reverse("sales:meus_pedidos"))

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(list(resposta.context["pedidos"]), [meu_pedido])
        self.assertNotContains(resposta, pedido_alheio.numero)

    def test_cliente_sem_usuario_nao_ve_pedidos(self):
        pedido = PedidoFactory()
        usuario = Usuario.objects.create_user(
            username="sem-vinculo-sec02", password=self.senha
        )

        self.client.force_login(usuario)
        resposta = self.client.get(reverse("sales:meus_pedidos"))

        self.assertNotContains(resposta, pedido.numero)
        self.assertEqual(list(resposta.context["pedidos"]), [])

    def test_segundo_checkout_nao_causa_integrity_error(self):
        usuario = Usuario.objects.create_user(
            username="com-vinculo-sec02", password=self.senha
        )
        ClienteFactory(usuario=usuario, documento="11144477735")
        self.client.force_login(usuario)

        pedido = fluxo_checkout(self.client, quantidade=1)

        self.assertIsNone(pedido.cliente.usuario)
        self.assertEqual(Cliente.objects.filter(usuario=usuario).count(), 1)
