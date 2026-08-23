from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from accounts.models import Usuario
from catalog.factories import ProdutoFactory
from costs.factories import DespesaFactory
from sales.factories import ItemPedidoFactory, PedidoFactory
from sales.models import Pedido


class PainelMetricasTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_groups", verbosity=0)
        cls.gestor = Usuario.objects.create_user(
            username="gestor", password="senha-forte-123"
        )
        cls.gestor.groups.add(Group.objects.get(name="Gestor"))

    def test_vendas_lucro_e_cancelados_fora_das_metricas(self):
        produto = ProdutoFactory(preco_online="100.00")
        pedido_bom = PedidoFactory(status=Pedido.Status.PAGO)
        ItemPedidoFactory(pedido=pedido_bom, produto=produto,
                          quantidade=2, preco_unitario=Decimal("100.00"))
        pedido_bom.recalcular_totais()

        cancelado = PedidoFactory(status=Pedido.Status.PAGO)
        ItemPedidoFactory(pedido=cancelado, produto=produto,
                          quantidade=9, preco_unitario=Decimal("100.00"))
        cancelado.transicionar(Pedido.Status.CANCELADO)

        DespesaFactory(valor=Decimal("150.00"), recorrencia="unica",
                       data=date.today())

        self.client.force_login(self.gestor)
        resposta = self.client.get(reverse("core:painel"))
        texto = resposta.content.decode()
        # Venda: 2 × 100 = 200; despesa 150 → lucro 50. Cancelado (900) fora.
        self.assertIn("R$ 200,00", texto)
        self.assertIn("R$ 150,00", texto)
        self.assertIn("R$ 50,00", texto)
        self.assertNotIn("900", texto.replace("9000", ""))  # heurística simples

    def test_aguardando_pagamento_aparece_no_painel(self):
        PedidoFactory(status=Pedido.Status.AGUARDANDO_PAGAMENTO)
        self.client.force_login(self.gestor)
        resposta = self.client.get(reverse("core:painel"))
        texto = resposta.content.decode()
        self.assertIn("Aguardando pagamento</th>", texto) or None
        self.assertIn("1 pedido(s)", texto)

    def test_filtro_por_periodo(self):
        produto = ProdutoFactory(preco_online="10.00")
        pedido = PedidoFactory(status=Pedido.Status.PAGO)
        ItemPedidoFactory(pedido=pedido, produto=produto, quantidade=1,
                          preco_unitario=Decimal("10.00"))
        passado = date.today() - timedelta(days=90)
        Pedido.objects.filter(pk=pedido.pk).update(criado_em=passado)

        self.client.force_login(self.gestor)
        hoje_iso = date.today().isoformat()
        resposta = self.client.get(
            reverse("core:painel"),
            {"inicio": hoje_iso, "fim": hoje_iso},
        )
        texto = resposta.content.decode()
        self.assertIn("R$ 0,00", texto)  # venda de 90 dias atrás fora do filtro
