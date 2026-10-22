"""ADR-010: métricas e dados recortados por vendedor."""

from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Usuario
from analytics.services import clientes_para_recompra, metricas_do_periodo
from costs.factories import DespesaFactory
from customers.factories import ClienteFactory
from sales.factories import PagamentoFactory, PedidoFactory
from sales.models import Pagamento, Pedido


def _usuario(username: str, grupo: str) -> Usuario:
    usuario = Usuario.objects.create_user(
        username=username, password="senha-forte-123"
    )
    usuario.groups.add(Group.objects.get(name=grupo))
    return usuario


def _pedido_pago(
    vendedor: Usuario,
    valor: Decimal,
    *,
    cliente=None,
    quando=None,
) -> Pedido:
    pedido = PedidoFactory(
        status=Pedido.Status.PAGO,
        usuario_criador=vendedor,
        cliente=cliente or ClienteFactory(),
        subtotal=valor,
        total=valor,
    )
    PagamentoFactory(
        pedido=pedido,
        valor=valor,
        status=Pagamento.Status.APROVADO,
        aprovado_em=quando or timezone.now(),
    )
    return pedido


class RecortePorVendedorTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_groups", verbosity=0)
        cls.vendedor1 = _usuario("vend1", "Vendedor")
        cls.vendedor2 = _usuario("vend2", "Vendedor")
        cls.admin = _usuario("admin", "Administrador")

    def test_vendedor_ve_apenas_seus_pedidos(self):
        _pedido_pago(self.vendedor1, Decimal("100.00"))
        _pedido_pago(self.vendedor2, Decimal("200.00"))

        self.client.force_login(self.vendedor1)
        resposta = self.client.get(reverse("sales:minhas_metricas"))

        self.assertEqual(resposta.context["receita"], Decimal("100.00"))
        self.assertEqual(resposta.context["num_pedidos"], 1)

    def test_admin_ve_todas_metricas(self):
        _pedido_pago(self.vendedor1, Decimal("100.00"))
        _pedido_pago(self.vendedor2, Decimal("200.00"))

        self.client.force_login(self.admin)
        resposta = self.client.get(reverse("core:painel"))

        self.assertEqual(resposta.context["receita"], Decimal("300.00"))
        self.assertEqual(resposta.context["num_pedidos"], 2)

    def test_vendedor_nao_ve_metricas_globais(self):
        self.client.force_login(self.vendedor1)
        resposta = self.client.get(reverse("core:painel"))
        self.assertEqual(resposta.status_code, 403)

    def test_clientes_para_recompra_recorte_por_vendedor(self):
        cliente1 = ClienteFactory(nome="Cliente do Vendedor 1")
        cliente2 = ClienteFactory(nome="Cliente do Vendedor 2")
        antigo = timezone.now() - timedelta(days=45)
        pedido1 = _pedido_pago(
            self.vendedor1, Decimal("100.00"), cliente=cliente1,
            quando=antigo,
        )
        pedido2 = _pedido_pago(
            self.vendedor2, Decimal("200.00"), cliente=cliente2,
            quando=antigo,
        )
        Pedido.objects.filter(pk__in=[pedido1.pk, pedido2.pk]).update(
            criado_em=antigo
        )

        clientes = clientes_para_recompra(30, vendedor=self.vendedor1)

        self.assertIn(cliente1, clientes)
        self.assertNotIn(cliente2, clientes)

    def test_despesas_recortadas_por_responsavel(self):
        _pedido_pago(self.vendedor1, Decimal("100.00"))
        DespesaFactory(
            valor=Decimal("30.00"),
            recorrencia="unica",
            data=date.today(),
            usuario_responsavel=self.vendedor1,
        )
        DespesaFactory(
            valor=Decimal("50.00"),
            recorrencia="unica",
            data=date.today(),
            usuario_responsavel=self.vendedor2,
        )

        hoje = timezone.localdate()
        metricas = metricas_do_periodo(
            hoje.replace(day=1), hoje, vendedor=self.vendedor1
        )

        self.assertEqual(metricas["despesas_total"], Decimal("30.00"))
