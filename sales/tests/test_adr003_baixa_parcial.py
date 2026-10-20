"""ADR-003: baixa cobre itens mesmo quando a reserva legada é parcial."""

from decimal import Decimal

from django.db.models import Sum
from django.test import TestCase

from catalog.factories import ProdutoFactory
from core.factories import UnidadeFactory
from sales.factories import ItemPedidoFactory, PedidoFactory
from sales.models import Pedido
from sales.services import marcar_pagamento_aprovado
from stock.factories import EstoqueFactory
from stock.models import Estoque, MovimentoEstoque, ReservaEstoque
from stock.services import reservar


class BaixaComReservaParcialTests(TestCase):
    def test_item_maior_que_reserva_baixa_a_diferenca(self):
        produto = ProdutoFactory()
        unidade = UnidadeFactory()
        EstoqueFactory(
            produto=produto, unidade=unidade, quantidade="100.00"
        )
        pedido = PedidoFactory(
            status=Pedido.Status.AGUARDANDO_PAGAMENTO,
            status_financeiro=Pedido.StatusFinanceiro.PENDENTE,
            unidade=unidade,
            subtotal="30.00",
            frete="0.00",
            total="30.00",
        )
        item = ItemPedidoFactory(
            pedido=pedido,
            produto=produto,
            quantidade=Decimal("10.00"),
            preco_unitario=Decimal("3.00"),
        )
        # Legado: apenas 5 das 10 unidades estavam bloqueadas/identificadas.
        reserva = reservar(
            produto=produto,
            unidade=unidade,
            quantidade=Decimal("5.00"),
            pedido=pedido,
            item_pedido=item,
        )

        marcar_pagamento_aprovado(pedido, id_externo="pay-parcial")

        estoque = Estoque.objects.get(produto=produto, unidade=unidade)
        reserva.refresh_from_db()
        assert estoque.quantidade == Decimal("90.00")
        assert estoque.quantidade_bloqueada == Decimal("0.00")
        assert reserva.status == ReservaEstoque.Status.CONSUMIDA
        total = MovimentoEstoque.objects.filter(
            produto=produto, unidade=unidade
        ).aggregate(total=Sum("delta"))["total"]
        assert total == Decimal("-10.00")

    def test_dois_produtos_um_com_reserva_parcial(self):
        produto_a = ProdutoFactory()
        produto_b = ProdutoFactory()
        unidade = UnidadeFactory()
        EstoqueFactory(
            produto=produto_a, unidade=unidade, quantidade="100.00"
        )
        EstoqueFactory(
            produto=produto_b, unidade=unidade, quantidade="100.00"
        )
        pedido = PedidoFactory(
            status=Pedido.Status.AGUARDANDO_PAGAMENTO,
            status_financeiro=Pedido.StatusFinanceiro.PENDENTE,
            unidade=unidade,
            subtotal="40.00",
            frete="0.00",
            total="40.00",
        )
        item_a = ItemPedidoFactory(
            pedido=pedido,
            produto=produto_a,
            quantidade=Decimal("4.00"),
            preco_unitario=Decimal("5.00"),
        )
        ItemPedidoFactory(
            pedido=pedido,
            produto=produto_b,
            quantidade=Decimal("4.00"),
            preco_unitario=Decimal("5.00"),
        )
        reservar(
            produto=produto_a,
            unidade=unidade,
            quantidade=Decimal("4.00"),
            pedido=pedido,
            item_pedido=item_a,
        )

        marcar_pagamento_aprovado(pedido, id_externo="pay-dois")

        estoque_a = Estoque.objects.get(produto=produto_a, unidade=unidade)
        estoque_b = Estoque.objects.get(produto=produto_b, unidade=unidade)
        assert estoque_a.quantidade == Decimal("96.00")
        assert estoque_a.quantidade_bloqueada == Decimal("0.00")
        # Sem reserva identificada, o produto B usa o fallback agregado.
        assert estoque_b.quantidade == Decimal("96.00")
        assert estoque_b.quantidade_bloqueada == Decimal("0.00")
