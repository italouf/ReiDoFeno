"""ADR-003: reservas com identidade de pedido e reconciliação."""

from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.test import TestCase, TransactionTestCase

from catalog.factories import ProdutoFactory
from core.factories import UnidadeFactory
from sales.factories import ItemPedidoFactory, PedidoFactory
from stock.factories import EstoqueFactory
from stock.models import Estoque, MovimentoEstoque, ReservaEstoque
from stock.services import consumir_reserva, liberar_reserva, reservar


class ReservaVinculadaTests(TransactionTestCase):
    def setUp(self):
        self.produto = ProdutoFactory()
        self.unidade = UnidadeFactory()
        EstoqueFactory(
            produto=self.produto,
            unidade=self.unidade,
            quantidade="100.00",
        )
        self.pedido1 = PedidoFactory(unidade=self.unidade)
        self.pedido2 = PedidoFactory(unidade=self.unidade)

    def _reservar(self, pedido, quantidade):
        item = ItemPedidoFactory(
            pedido=pedido,
            produto=self.produto,
            quantidade=Decimal(quantidade),
        )
        return reservar(
            produto=self.produto,
            unidade=self.unidade,
            quantidade=Decimal(quantidade),
            pedido=pedido,
            item_pedido=item,
        )

    def test_reserva_tem_identidade_do_pedido(self):
        reserva = self._reservar(self.pedido1, "5.00")
        assert reserva.pedido == self.pedido1
        assert reserva.status == ReservaEstoque.Status.ATIVA
        assert reserva.quantidade == Decimal("5.00")
        assert reserva.produto == self.produto
        assert reserva.unidade == self.unidade

    def test_reserva_sem_pedido_eh_rejeitada(self):
        from django.core.exceptions import ValidationError

        with pytest.raises(ValidationError):
            reservar(
                produto=self.produto,
                unidade=self.unidade,
                quantidade=Decimal("5.00"),
            )

    def test_duas_reservas_mesmo_produto_pedidos_diferentes(self):
        r1 = self._reservar(self.pedido1, "3.00")
        r2 = self._reservar(self.pedido2, "4.00")
        assert r1.pk != r2.pk
        estoque = Estoque.objects.get(produto=self.produto, unidade=self.unidade)
        assert estoque.quantidade_bloqueada == Decimal("7.00")

    def test_uma_reserva_ativa_por_pedido_produto_unidade(self):
        self._reservar(self.pedido1, "3.00")
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                self._reservar(self.pedido1, "2.00")

    def test_consumir_reserva_idempotente(self):
        reserva = self._reservar(self.pedido1, "5.00")
        consumir_reserva(reserva)
        estoque_antes = Estoque.objects.get(
            produto=self.produto, unidade=self.unidade
        ).quantidade_bloqueada
        movimentos_antes = MovimentoEstoque.objects.count()

        consumir_reserva(reserva)

        reserva.refresh_from_db()
        estoque = Estoque.objects.get(produto=self.produto, unidade=self.unidade)
        assert estoque.quantidade_bloqueada == estoque_antes == Decimal("0.00")
        assert MovimentoEstoque.objects.count() == movimentos_antes
        assert reserva.status == ReservaEstoque.Status.CONSUMIDA
        assert reserva.consumida_em is not None

    def test_consumir_reserva_gera_baixa_definitiva(self):
        reserva = self._reservar(self.pedido1, "5.00")
        consumir_reserva(reserva)
        movimento = MovimentoEstoque.objects.get(
            produto=self.produto, unidade=self.unidade
        )
        assert movimento.tipo == MovimentoEstoque.Tipo.BAIXA_DEFINITIVA
        assert movimento.delta == Decimal("-5.00")
        assert movimento.quantidade == Decimal("5.00")
        estoque = Estoque.objects.get(produto=self.produto, unidade=self.unidade)
        assert estoque.quantidade == Decimal("95.00")
        assert estoque.quantidade_bloqueada == Decimal("0.00")

    def test_liberar_reserva_nao_gera_movimento(self):
        reserva = self._reservar(self.pedido1, "5.00")
        movimentos_antes = MovimentoEstoque.objects.count()

        liberar_reserva(reserva)

        reserva.refresh_from_db()
        assert MovimentoEstoque.objects.count() == movimentos_antes
        assert reserva.status == ReservaEstoque.Status.LIBERADA
        assert reserva.liberada_em is not None
        estoque = Estoque.objects.get(produto=self.produto, unidade=self.unidade)
        assert estoque.quantidade_bloqueada == Decimal("0.00")
        assert estoque.quantidade == Decimal("100.00")

    def test_liberar_reserva_idempotente(self):
        reserva = self._reservar(self.pedido1, "5.00")
        liberar_reserva(reserva)
        liberar_reserva(reserva)
        estoque = Estoque.objects.get(produto=self.produto, unidade=self.unidade)
        assert estoque.quantidade_bloqueada == Decimal("0.00")
        assert reserva.status == ReservaEstoque.Status.LIBERADA

    def test_reserva_acima_do_disponivel_eh_rejeitada(self):
        from django.core.exceptions import ValidationError

        Estoque.objects.filter(
            produto=self.produto, unidade=self.unidade
        ).update(quantidade=Decimal("4.00"))
        with pytest.raises(ValidationError):
            self._reservar(self.pedido1, "5.00")

    def test_reserva_sem_estoque_eh_rejeitada(self):
        from django.core.exceptions import ValidationError

        produto_sem_estoque = ProdutoFactory()
        pedido = PedidoFactory(unidade=self.unidade)
        item = ItemPedidoFactory(
            pedido=pedido, produto=produto_sem_estoque, quantidade=Decimal("1.00")
        )
        with pytest.raises(ValidationError):
            reservar(
                produto=produto_sem_estoque,
                unidade=self.unidade,
                quantidade=Decimal("1.00"),
                pedido=pedido,
                item_pedido=item,
            )

    def test_item_de_outro_pedido_eh_rejeitado(self):
        from django.core.exceptions import ValidationError

        item_alheio = ItemPedidoFactory(
            pedido=self.pedido2,
            produto=self.produto,
            quantidade=Decimal("1.00"),
        )
        with pytest.raises(ValidationError):
            reservar(
                produto=self.produto,
                unidade=self.unidade,
                quantidade=Decimal("1.00"),
                pedido=self.pedido1,
                item_pedido=item_alheio,
            )

    def test_consumir_reserva_inconsistente_eh_rejeitado(self):
        from django.core.exceptions import ValidationError

        reserva = self._reservar(self.pedido1, "5.00")
        Estoque.objects.filter(
            produto=self.produto, unidade=self.unidade
        ).update(quantidade_bloqueada=Decimal("0.00"))
        with pytest.raises(ValidationError):
            consumir_reserva(reserva)
        reserva.refresh_from_db()
        assert reserva.status == ReservaEstoque.Status.ATIVA

    def test_liberar_reserva_inconsistente_eh_rejeitada(self):
        from django.core.exceptions import ValidationError

        reserva = self._reservar(self.pedido1, "5.00")
        Estoque.objects.filter(
            produto=self.produto, unidade=self.unidade
        ).update(quantidade_bloqueada=Decimal("0.00"))
        with pytest.raises(ValidationError):
            liberar_reserva(reserva)
        reserva.refresh_from_db()
        assert reserva.status == ReservaEstoque.Status.ATIVA

    def test_reserva_reconcilia_com_bloqueio(self):
        self._reservar(self.pedido1, "3.00")
        r2 = self._reservar(self.pedido2, "4.00")
        liberar_reserva(r2)

        ativas = ReservaEstoque.objects.filter(
            produto=self.produto,
            unidade=self.unidade,
            status=ReservaEstoque.Status.ATIVA,
        ).aggregate(total=Sum("quantidade"))["total"]
        estoque = Estoque.objects.get(produto=self.produto, unidade=self.unidade)
        assert ativas == estoque.quantidade_bloqueada == Decimal("3.00")


class ReconciliacaoReservasTests(TestCase):
    def test_soma_reservas_ativas_igual_bloqueada_apos_consumo_e_liberacao(self):
        produto = ProdutoFactory()
        unidade = UnidadeFactory()
        EstoqueFactory(
            produto=produto,
            unidade=unidade,
            quantidade="100.00",
        )
        reservas = []
        for quantidade in ("5.00", "4.00", "3.00"):
            pedido = PedidoFactory(unidade=unidade)
            item = ItemPedidoFactory(
                pedido=pedido,
                produto=produto,
                quantidade=Decimal(quantidade),
            )
            reservas.append(
                reservar(
                    produto=produto,
                    unidade=unidade,
                    quantidade=Decimal(quantidade),
                    pedido=pedido,
                    item_pedido=item,
                )
            )

        consumir_reserva(reservas[0])
        liberar_reserva(reservas[1])

        ativas = ReservaEstoque.objects.filter(
            produto=produto,
            unidade=unidade,
            status=ReservaEstoque.Status.ATIVA,
        ).aggregate(total=Sum("quantidade"))["total"]
        estoque = Estoque.objects.get(produto=produto, unidade=unidade)
        assert ativas == estoque.quantidade_bloqueada == Decimal("3.00")
        assert estoque.quantidade == Decimal("95.00")
