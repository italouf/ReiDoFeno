"""ADR-008: CMV por item e snapshot histórico de custo."""

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.test import TestCase

from catalog.factories import ProdutoFactory
from sales.factories import ItemPedidoFactory, PedidoFactory
from sales.models import ItemPedido, Pedido
from stock.exceptions import ImutabilidadeViolation


class CMVSnapshotTests(TestCase):
    def test_item_pedido_captura_custo_no_checkout(self):
        from sales.pricing import calcular_item_pedido

        produto = ProdutoFactory(custo=Decimal("50.00"))
        item = calcular_item_pedido(
            produto=produto,
            cliente=None,
            quantidade=2,
            preco_base=Decimal("80.00"),
        )

        self.assertEqual(item.custo_unitario, Decimal("50.00"))

    def test_item_persistido_captura_custo_do_produto(self):
        produto = ProdutoFactory(custo=Decimal("50.00"))
        item = ItemPedidoFactory(produto=produto, quantidade=2)

        self.assertEqual(item.custo_unitario, Decimal("50.00"))

    def test_mudanca_de_custo_nao_afeta_itens_anteriores(self):
        produto = ProdutoFactory(custo=Decimal("50.00"))
        item = ItemPedidoFactory(produto=produto, quantidade=2)

        produto.custo = Decimal("70.00")
        produto.save()

        item.refresh_from_db()
        self.assertEqual(item.custo_unitario, Decimal("50.00"))

    def test_cmv_do_pedido(self):
        produto1 = ProdutoFactory(custo=Decimal("30.00"))
        produto2 = ProdutoFactory(custo=Decimal("40.00"))

        pedido = PedidoFactory()
        ItemPedidoFactory(
            pedido=pedido,
            produto=produto1,
            quantidade=2,
            preco_unitario=Decimal("50.00"),
        )
        ItemPedidoFactory(
            pedido=pedido,
            produto=produto2,
            quantidade=1,
            preco_unitario=Decimal("60.00"),
        )
        pedido.recalcular_totais()

        self.assertEqual(pedido.cmv, Decimal("100.00"))
        self.assertEqual(pedido.lucro_bruto, Decimal("60.00"))

    def test_lucro_bruto_por_item(self):
        produto = ProdutoFactory(
            custo=Decimal("50.00"), preco_balcao=Decimal("80.00")
        )
        item = ItemPedidoFactory(
            produto=produto,
            quantidade=2,
            preco_unitario=Decimal("80.00"),
        )

        self.assertEqual(item.lucro_bruto, Decimal("60.00"))

    def test_custo_unitario_imutavel_por_save(self):
        item = ItemPedidoFactory(custo_unitario=Decimal("50.00"))
        item.custo_unitario = Decimal("999.00")

        with pytest.raises(ImutabilidadeViolation):
            item.save()

    def test_custo_unitario_imutavel_por_update_direto(self):
        item = ItemPedidoFactory(custo_unitario=Decimal("50.00"))

        with pytest.raises(ImutabilidadeViolation):
            ItemPedido.objects.filter(pk=item.pk).update(
                custo_unitario=Decimal("999.00")
            )

    def test_custo_negativo_rejeitado_pela_validacao(self):
        item = ItemPedido(
            quantidade=Decimal("1.00"),
            preco_unitario=Decimal("10.00"),
            custo_unitario=Decimal("-1.00"),
        )

        with pytest.raises(ValidationError):
            item.clean()

    def test_metricas_do_periodo_incluem_cmv(self):
        from django.utils import timezone

        from analytics.services import metricas_do_periodo
        from sales.factories import PagamentoFactory
        from sales.models import Pagamento

        produto = ProdutoFactory(custo=Decimal("30.00"))
        pedido = PedidoFactory(
            status=Pedido.Status.PAGO,
            subtotal=Decimal("100.00"),
            total=Decimal("100.00"),
        )
        ItemPedidoFactory(
            pedido=pedido,
            produto=produto,
            quantidade=2,
            preco_unitario=Decimal("50.00"),
        )
        PagamentoFactory(
            pedido=pedido,
            valor=Decimal("100.00"),
            status=Pagamento.Status.APROVADO,
            aprovado_em=timezone.now(),
        )
        dia = timezone.localdate()

        metricas = metricas_do_periodo(dia, dia)

        self.assertEqual(metricas["cmv_total"], Decimal("60.00"))
        self.assertEqual(metricas["lucro_bruto"], Decimal("40.00"))

    def test_cmv_nao_inclui_frete(self):
        pedido = PedidoFactory(
            subtotal=Decimal("0.00"),
            frete=Decimal("20.00"),
            total=Decimal("20.00"),
        )
        ItemPedidoFactory(
            pedido=pedido,
            produto=ProdutoFactory(custo=Decimal("10.00")),
            quantidade=1,
            preco_unitario=Decimal("30.00"),
        )
        pedido.recalcular_totais()

        self.assertEqual(pedido.subtotal, Decimal("30.00"))
        self.assertEqual(pedido.total, Decimal("50.00"))
        self.assertEqual(pedido.cmv, Decimal("10.00"))
        self.assertEqual(pedido.lucro_bruto, Decimal("20.00"))
