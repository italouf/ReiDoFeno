from decimal import Decimal

from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from accounts.models import Usuario
from customers.factories import ClienteFactory
from customers.models import InteracaoVendedor
from sales.factories import ItemPedidoFactory, PedidoFactory
from sales.models import Pedido


class InteracaoVendedorTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_groups", verbosity=0)
        cls.senha = "senha-forte-123"
        cls.vendedor = Usuario.objects.create_user(
            username="vendedor", password=cls.senha
        )
        cls.vendedor.groups.add(Group.objects.get(name="Vendedor"))
        cls.cliente = ClienteFactory(nome="Cliente Alvo")

    def test_vendedor_registra_interacao(self):
        self.client.force_login(self.vendedor)
        resposta = self.client.post(
            reverse("customers:interacao_novo", args=[self.cliente.pk]),
            {"tipo": "ligacao", "observacao": "Reforçou pedido de sacas"},
        )
        self.assertEqual(resposta.status_code, 302)
        interacao = InteracaoVendedor.objects.get(cliente=self.cliente)
        self.assertEqual(interacao.vendedor, self.vendedor)
        self.assertEqual(interacao.tipo, "ligacao")

    def test_interacoes_aparecem_na_ficha_do_cliente(self):
        InteracaoVendedor.objects.create(
            vendedor=self.vendedor, cliente=self.cliente, tipo="visita"
        )
        self.client.force_login(self.vendedor)
        resposta = self.client.get(
            reverse("customers:cliente_detalhe", args=[self.cliente.pk])
        )
        self.assertContains(resposta, "Visita")


class MetricasVendedorTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_groups", verbosity=0)
        cls.senha = "senha-forte-123"
        cls.vendedores = {}
        for nome in ("vend_a", "vend_b"):
            usuario = Usuario.objects.create_user(username=nome, password=cls.senha)
            usuario.groups.add(Group.objects.get(name="Vendedor"))
            cls.vendedores[nome] = usuario

    @staticmethod
    def _criar_pedido(vendedor, status=Pedido.Status.PAGO, total="100.00"):
        pedido = PedidoFactory(usuario_criador=vendedor, status=status)
        ItemPedidoFactory(pedido=pedido, preco_unitario=Decimal(total),
                          quantidade=Decimal("1"))
        pedido.recalcular_totais()
        return pedido

    def test_metricas_isoladas_por_vendedor(self):
        self._criar_pedido(self.vendedores["vend_a"])
        self._criar_pedido(self.vendedores["vend_b"], total="999.00")

        self.client.force_login(self.vendedores["vend_a"])
        resposta = self.client.get(reverse("sales:minhas_metricas"))
        texto = resposta.content.decode()

        self.assertIn("R$ 100", texto)
        self.assertNotIn("999", texto)

    def test_cancelados_fora_das_vendas_totais(self):
        cancelado = self._criar_pedido(self.vendedores["vend_a"],
                                       status=Pedido.Status.PAGO)
        cancelado.transicionar(Pedido.Status.CANCELADO)
        self._criar_pedido(self.vendedores["vend_a"], total="50.00")

        self.client.force_login(self.vendedores["vend_a"])
        texto = self.client.get(reverse("sales:minhas_metricas")).content.decode()
        self.assertIn("R$ 50,00", texto)
