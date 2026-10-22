"""B03: contrato de reserva e proteção do ciclo de vida."""

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import DatabaseError, connection
from django.db.models.deletion import ProtectedError
from django.test import TestCase

from catalog.factories import ProdutoFactory
from core.factories import UnidadeFactory
from sales.factories import ItemPedidoFactory, PedidoFactory
from sales.models import Pedido
from sales.services import marcar_pagamento_aprovado
from stock.factories import EstoqueFactory
from stock.models import (
    BloqueioLegado,
    Estoque,
    MovimentoEstoque,
    ReservaEstoque,
)
from stock.services import (
    consumir_reserva,
    reservar,
    resolver_bloqueio_legado,
    saldo_comprometido,
)


class ContratoReservaTests(TestCase):
    def setUp(self):
        self.produto = ProdutoFactory()
        self.unidade = UnidadeFactory()
        self.outra_unidade = UnidadeFactory(nome="Outra unidade")
        EstoqueFactory(
            produto=self.produto,
            unidade=self.unidade,
            quantidade="20.00",
        )
        EstoqueFactory(
            produto=self.produto,
            unidade=self.outra_unidade,
            quantidade="20.00",
        )
        self.pedido = PedidoFactory(
            unidade=self.unidade,
            status=Pedido.Status.AGUARDANDO_PAGAMENTO,
            status_financeiro=Pedido.StatusFinanceiro.PENDENTE,
        )
        self.item = ItemPedidoFactory(
            pedido=self.pedido,
            produto=self.produto,
            quantidade=Decimal("5.00"),
        )

    def _reservar(self, **kwargs):
        dados = {
            "produto": self.produto,
            "unidade": self.unidade,
            "quantidade": Decimal("5.00"),
            "pedido": self.pedido,
            "item_pedido": self.item,
        }
        dados.update(kwargs)
        return reservar(**dados)

    def test_reserva_valida(self):
        reserva = self._reservar()
        self.assertEqual(reserva.quantidade, Decimal("5.00"))

    def test_pedido_cancelado_nao_recebe_reserva(self):
        self.pedido.status = Pedido.Status.CANCELADO
        self.pedido.status_financeiro = Pedido.StatusFinanceiro.CANCELADO
        self.pedido.save(
            update_fields=["status", "status_financeiro"]
        )
        with pytest.raises(ValidationError):
            self._reservar()

    def test_pedido_pago_nao_recebe_reserva(self):
        self.pedido.status_financeiro = Pedido.StatusFinanceiro.PAGO
        self.pedido.save(update_fields=["status_financeiro"])
        with pytest.raises(ValidationError):
            self._reservar()

    def test_produto_divergente_do_item_e_rejeitado(self):
        outro = ProdutoFactory()
        EstoqueFactory(
            produto=outro, unidade=self.unidade, quantidade="20.00"
        )
        with pytest.raises(ValidationError):
            self._reservar(produto=outro)

    def test_quantidade_maior_que_o_item_e_rejeitada(self):
        with pytest.raises(ValidationError):
            self._reservar(quantidade=Decimal("6.00"))

    def test_unidade_divergente_do_pedido_e_rejeitada(self):
        with pytest.raises(ValidationError):
            self._reservar(unidade=self.outra_unidade)

    def test_reserva_repetida_com_mesma_quantidade_e_idempotente(self):
        primeira = self._reservar()
        segunda = self._reservar()
        assert segunda.pk == primeira.pk
        estoque = Estoque.objects.get(
            produto=self.produto, unidade=self.unidade
        )
        self.assertEqual(estoque.quantidade_bloqueada, Decimal("5.00"))

    def test_consumir_reserva_maior_que_o_item_e_rejeitado(self):
        reserva = ReservaEstoque.objects.create(
            pedido=self.pedido,
            item_pedido=self.item,
            produto=self.produto,
            unidade=self.unidade,
            quantidade=Decimal("6.00"),
            status=ReservaEstoque.Status.ATIVA,
        )
        Estoque.objects.filter(
            produto=self.produto, unidade=self.unidade
        ).update(quantidade_bloqueada=Decimal("6.00"))
        with pytest.raises(ValidationError):
            consumir_reserva(reserva)
        reserva.refresh_from_db()
        self.assertEqual(reserva.status, ReservaEstoque.Status.ATIVA)
        self.assertFalse(
            MovimentoEstoque.objects.filter(
                produto=self.produto, unidade=self.unidade
            ).exists()
        )

    def test_reserva_consumida_nao_baixa_de_novo_na_aprovacao(self):
        reserva = self._reservar()
        consumir_reserva(reserva)

        marcar_pagamento_aprovado(self.pedido, id_externo="pay-b03")

        estoque = Estoque.objects.get(
            produto=self.produto, unidade=self.unidade
        )
        self.assertEqual(estoque.quantidade, Decimal("15.00"))
        self.assertEqual(estoque.quantidade_bloqueada, Decimal("0.00"))
        self.assertEqual(
            MovimentoEstoque.objects.filter(
                produto=self.produto, unidade=self.unidade
            ).count(),
            1,
        )

    def test_reservar_apos_consumo_total_e_rejeitado(self):
        reserva = self._reservar()
        consumir_reserva(reserva)
        with pytest.raises(ValidationError):
            self._reservar()

    def test_reservar_restante_apos_consumo_parcial(self):
        reserva = ReservaEstoque.objects.create(
            pedido=self.pedido,
            item_pedido=self.item,
            produto=self.produto,
            unidade=self.unidade,
            quantidade=Decimal("2.00"),
            status=ReservaEstoque.Status.ATIVA,
        )
        Estoque.objects.filter(
            produto=self.produto, unidade=self.unidade
        ).update(quantidade_bloqueada=Decimal("2.00"))
        consumir_reserva(reserva)

        nova = self._reservar(quantidade=Decimal("3.00"))
        self.assertEqual(nova.quantidade, Decimal("3.00"))

    def test_item_com_reserva_nao_pode_ser_excluido(self):
        self._reservar()
        with pytest.raises(ProtectedError):
            self.item.delete()
        with pytest.raises(ProtectedError):
            self.pedido.delete()

    def test_bloqueio_legado_em_quarentena_reduz_e_pode_ser_resolvido(self):
        bloqueio = BloqueioLegado.objects.create(
            produto=self.produto,
            unidade=self.unidade,
            quantidade=Decimal("3.00"),
            motivo="bloqueio legado de teste",
        )
        Estoque.objects.filter(
            produto=self.produto, unidade=self.unidade
        ).update(quantidade_bloqueada=Decimal("3.00"))
        self.assertEqual(
            saldo_comprometido(self.produto, self.unidade),
            Decimal("3.00"),
        )

        resolver_bloqueio_legado(
            bloqueio, justificativa="reconciliação manual"
        )

        bloqueio.refresh_from_db()
        estoque = Estoque.objects.get(
            produto=self.produto, unidade=self.unidade
        )
        self.assertIsNotNone(bloqueio.resolvido_em)
        self.assertEqual(estoque.quantidade_bloqueada, Decimal("0.00"))
        self.assertEqual(
            saldo_comprometido(self.produto, self.unidade),
            Decimal("0.00"),
        )

    def test_resolver_bloqueio_recusa_cobertura_insuficiente(self):
        # Estado inconsistente: reserva ativa 8, bloqueio agregado 8 e
        # quarentena 3 não coberta pelo agregado.
        reserva = ReservaEstoque.objects.create(
            pedido=self.pedido,
            item_pedido=self.item,
            produto=self.produto,
            unidade=self.unidade,
            quantidade=Decimal("8.00"),
            status=ReservaEstoque.Status.ATIVA,
        )
        Estoque.objects.filter(
            produto=self.produto, unidade=self.unidade
        ).update(quantidade_bloqueada=Decimal("8.00"))
        bloqueio = BloqueioLegado.objects.create(
            produto=self.produto,
            unidade=self.unidade,
            quantidade=Decimal("3.00"),
            motivo="quarentena divergente",
        )
        with pytest.raises(ValidationError):
            resolver_bloqueio_legado(
                bloqueio, justificativa="tentativa"
            )
        bloqueio.refresh_from_db()
        estoque = Estoque.objects.get(
            produto=self.produto, unidade=self.unidade
        )
        self.assertIsNone(bloqueio.resolvido_em)
        self.assertEqual(estoque.quantidade_bloqueada, Decimal("8.00"))
        reserva.refresh_from_db()
        self.assertEqual(reserva.status, ReservaEstoque.Status.ATIVA)

    @pytest.mark.postgres
    def test_postgres_rejeita_nan_em_reserva_e_quarentena(self):
        if connection.vendor != "postgresql":  # pragma: no cover
            pytest.skip("Limites testados apenas no PostgreSQL.")

        reserva = self._reservar()
        bloqueio = BloqueioLegado.objects.create(
            produto=self.produto,
            unidade=self.unidade,
            quantidade=Decimal("1.00"),
            motivo="teste",
        )
        with pytest.raises(DatabaseError):
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE stock_reservaestoque SET quantidade = 'NaN' "
                    "WHERE id = %s",
                    [reserva.pk],
                )
        with pytest.raises(DatabaseError):
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE stock_bloqueiolegado SET quantidade = 'NaN' "
                    "WHERE id = %s",
                    [bloqueio.pk],
                )
