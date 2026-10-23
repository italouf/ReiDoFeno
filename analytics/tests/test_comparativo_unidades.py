"""Comparativo de métricas entre as unidades."""

from datetime import date, datetime, time
from decimal import Decimal

from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Usuario
from analytics.services import comparativo_unidades
from catalog.factories import ProdutoFactory
from core.factories import UnidadeFactory, UnidadeIacuFactory
from sales.factories import ItemPedidoFactory, PagamentoFactory, PedidoFactory
from sales.models import Pagamento, Pedido

DIA = date(2026, 10, 1)


def _pedido_pago(*, produto, unidade, quantidade, preco, custo, dia=DIA):
    pedido = PedidoFactory(
        status=Pedido.Status.PAGO,
        unidade=unidade,
        subtotal=preco * quantidade,
        total=preco * quantidade,
    )
    ItemPedidoFactory(
        pedido=pedido,
        produto=produto,
        quantidade=quantidade,
        preco_unitario=preco,
        custo_unitario=custo,
    )
    PagamentoFactory(
        pedido=pedido,
        valor=preco * quantidade,
        status=Pagamento.Status.APROVADO,
        aprovado_em=timezone.make_aware(datetime.combine(dia, time.min)),
    )
    return pedido


class ComparativoUnidadesTests(TestCase):
    def test_metricas_por_unidade(self):
        fs = UnidadeFactory(nome="Feira de Santana")
        iacu = UnidadeIacuFactory()
        produto = ProdutoFactory()

        _pedido_pago(
            produto=produto, unidade=fs, quantidade=2,
            preco=Decimal("50.00"), custo=Decimal("30.00"),
        )
        _pedido_pago(
            produto=produto, unidade=iacu, quantidade=1,
            preco=Decimal("200.00"), custo=Decimal("80.00"),
        )

        linhas = {
            linha["unidade"]: linha
            for linha in comparativo_unidades(DIA, DIA)
        }

        self.assertEqual(linhas["Feira de Santana"]["receita"], Decimal("100.00"))
        self.assertEqual(linhas["Feira de Santana"]["cmv"], Decimal("60.00"))
        self.assertEqual(linhas["Feira de Santana"]["lucro_bruto"], Decimal("40.00"))
        self.assertEqual(linhas["Feira de Santana"]["num_pedidos"], 1)
        self.assertEqual(linhas["Feira de Santana"]["ticket_medio"], Decimal("100.00"))
        self.assertEqual(linhas["Iaçu"]["receita"], Decimal("200.00"))
        self.assertEqual(linhas["Iaçu"]["cmv"], Decimal("80.00"))

    def test_unidade_sem_venda_aparece_zerada(self):
        fs = UnidadeFactory(nome="Feira de Santana")
        UnidadeIacuFactory()
        produto = ProdutoFactory()
        _pedido_pago(
            produto=produto, unidade=fs, quantidade=1,
            preco=Decimal("100.00"), custo=Decimal("10.00"),
        )

        linhas = {
            linha["unidade"]: linha
            for linha in comparativo_unidades(DIA, DIA)
        }

        self.assertEqual(linhas["Iaçu"]["receita"], Decimal("0.00"))
        self.assertEqual(linhas["Iaçu"]["num_pedidos"], 0)
        self.assertEqual(linhas["Iaçu"]["ticket_medio"], Decimal("0.00"))

    def test_filtro_de_periodo(self):
        fs = UnidadeFactory(nome="Feira de Santana")
        UnidadeIacuFactory()
        produto = ProdutoFactory()
        _pedido_pago(
            produto=produto, unidade=fs, quantidade=1,
            preco=Decimal("100.00"), custo=Decimal("10.00"),
            dia=date(2026, 9, 1),
        )

        linhas = comparativo_unidades(DIA, DIA)
        fs_linha = next(
            linha
            for linha in linhas
            if linha["unidade"] == "Feira de Santana"
        )
        self.assertEqual(fs_linha["receita"], Decimal("0.00"))

    def test_tela_comparativo_renderiza(self):
        call_command("seed_groups", verbosity=0)
        gestor = Usuario.objects.create_user(
            username="gestor_comp", password="senha-forte-123"
        )
        gestor.groups.add(Group.objects.get(name="Gestor"))
        self.client.force_login(gestor)

        resposta = self.client.get(
            reverse("analytics:comparativo_unidades")
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Comparativo")

    def test_vendedor_recebe_403(self):
        call_command("seed_groups", verbosity=0)
        vendedor = Usuario.objects.create_user(
            username="vend_comp", password="senha-forte-123"
        )
        vendedor.groups.add(Group.objects.get(name="Vendedor"))
        self.client.force_login(vendedor)

        resposta = self.client.get(
            reverse("analytics:comparativo_unidades")
        )

        self.assertEqual(resposta.status_code, 403)
