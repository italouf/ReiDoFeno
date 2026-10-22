"""DAT-01: constraints de integridade financeira no banco."""

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection
from django.test import TransactionTestCase

from core.factories import UnidadeFactory
from customers.factories import ClienteFactory
from sales.factories import (
    ItemPedidoFactory,
    PagamentoFactory,
    PedidoFactory,
)
from sales.models import ItemPedido, Pagamento, Pedido


def _pedido(**kwargs):
    return PedidoFactory(**kwargs)


class CheckConstraintsTests(TransactionTestCase):
    def setUp(self):
        self.cliente = ClienteFactory()
        self.unidade = UnidadeFactory()

    def test_pedido_subtotal_negativo_rejeitado(self):
        with pytest.raises(IntegrityError):
            _pedido(
                cliente=self.cliente,
                unidade=self.unidade,
                subtotal=Decimal("-100.00"),
                frete=Decimal("0.00"),
                total=Decimal("-100.00"),
            )

    def test_pedido_frete_negativo_rejeitado(self):
        with pytest.raises(IntegrityError):
            _pedido(
                cliente=self.cliente,
                unidade=self.unidade,
                subtotal=Decimal("100.00"),
                frete=Decimal("-10.00"),
                total=Decimal("90.00"),
            )

    def test_pedido_total_negativo_rejeitado(self):
        with pytest.raises(IntegrityError):
            _pedido(
                cliente=self.cliente,
                unidade=self.unidade,
                subtotal=Decimal("0.00"),
                frete=Decimal("0.00"),
                total=Decimal("-1.00"),
            )

    def test_pedido_total_inconsistente_rejeitado(self):
        """total != subtotal + frete deve ser rejeitado."""
        with pytest.raises(IntegrityError):
            _pedido(
                cliente=self.cliente,
                unidade=self.unidade,
                subtotal=Decimal("100.00"),
                frete=Decimal("10.00"),
                total=Decimal("50.00"),
            )

    def test_pedido_total_consistente_aceito(self):
        pedido = _pedido(
            cliente=self.cliente,
            unidade=self.unidade,
            subtotal=Decimal("100.00"),
            frete=Decimal("10.00"),
            total=Decimal("110.00"),
        )
        self.assertEqual(pedido.total, Decimal("110.00"))

    def test_pedido_com_frete_nao_inteiro_aceito(self):
        """A igualdade de totais não pode depender de float do SQLite."""
        for subtotal, frete, total in (
            ("33.33", "0.01", "33.34"),
            ("0.10", "0.20", "0.30"),
            ("19.99", "7.77", "27.76"),
        ):
            with self.subTest(subtotal=subtotal, frete=frete, total=total):
                pedido = _pedido(
                    cliente=self.cliente,
                    unidade=self.unidade,
                    subtotal=Decimal(subtotal),
                    frete=Decimal(frete),
                    total=Decimal(total),
                )
                self.assertEqual(pedido.total, Decimal(total))

    def test_item_quantidade_zero_rejeitada(self):
        pedido = _pedido(cliente=self.cliente, unidade=self.unidade)
        with pytest.raises(IntegrityError):
            ItemPedidoFactory(
                pedido=pedido,
                produto_nome="Teste",
                quantidade=Decimal("0.00"),
                preco_unitario=Decimal("10.00"),
            )

    def test_item_quantidade_negativa_rejeitada(self):
        pedido = _pedido(cliente=self.cliente, unidade=self.unidade)
        with pytest.raises(IntegrityError):
            ItemPedidoFactory(
                pedido=pedido,
                quantidade=Decimal("-1.00"),
            )

    def test_item_preco_negativo_rejeitado(self):
        pedido = _pedido(cliente=self.cliente, unidade=self.unidade)
        with pytest.raises(IntegrityError):
            ItemPedidoFactory(
                pedido=pedido,
                preco_unitario=Decimal("-0.01"),
            )

    def test_pagamento_valor_negativo_rejeitado(self):
        pedido = _pedido(cliente=self.cliente, unidade=self.unidade)
        with pytest.raises(IntegrityError):
            PagamentoFactory(pedido=pedido, valor=Decimal("-50.00"))

    def test_valores_zero_validos_nos_limites(self):
        pedido = _pedido(
            cliente=self.cliente,
            unidade=self.unidade,
            subtotal=Decimal("0.00"),
            frete=Decimal("0.00"),
            total=Decimal("0.00"),
        )
        item = ItemPedidoFactory(
            pedido=pedido,
            quantidade=Decimal("1.00"),
            preco_unitario=Decimal("0.00"),
        )
        pagamento = PagamentoFactory(pedido=pedido, valor=Decimal("0.00"))
        self.assertEqual(item.subtotal, Decimal("0.00"))
        self.assertEqual(pagamento.valor, Decimal("0.00"))

    def test_subtotal_do_item_e_produto_de_quantidade_por_preco(self):
        pedido = _pedido(cliente=self.cliente, unidade=self.unidade)
        item = ItemPedidoFactory(
            pedido=pedido,
            quantidade=Decimal("3.00"),
            preco_unitario=Decimal("10.00"),
        )
        self.assertEqual(item.subtotal, Decimal("30.00"))
        self.assertEqual(
            item.subtotal,
            item.quantidade * item.preco_unitario,
        )
        self.assertFalse(
            ItemPedido.objects.filter(pk=item.pk, quantidade__lte=0).exists()
        )
        self.assertFalse(
            Pagamento.objects.filter(pedido=pedido, valor__lt=0).exists()
        )

    def test_modelos_rejeitam_nan_na_validacao(self):
        pedido = Pedido(
            subtotal=Decimal("NaN"),
            frete=Decimal("0.00"),
            total=Decimal("NaN"),
        )
        with pytest.raises(ValidationError):
            pedido.clean()

        item = ItemPedido(
            quantidade=Decimal("NaN"),
            preco_unitario=Decimal("0.00"),
        )
        with pytest.raises(ValidationError):
            item.clean()

        pagamento = Pagamento(valor=Decimal("NaN"))
        with pytest.raises(ValidationError):
            pagamento.clean()

    @pytest.mark.postgres
    def test_postgres_rejeita_nan_em_sql_direto(self):
        pedido = _pedido(
            cliente=self.cliente,
            unidade=self.unidade,
            subtotal=Decimal("10.00"),
            frete=Decimal("0.00"),
            total=Decimal("10.00"),
        )
        with pytest.raises(IntegrityError):
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE sales_pedido SET subtotal = 'NaN', total = 'NaN' "
                    "WHERE id = %s",
                    [pedido.pk],
                )
