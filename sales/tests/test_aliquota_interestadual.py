"""Alíquota interestadual BA→MG e identificação no pedido."""

from decimal import Decimal

from django.test import TestCase

from core.factories import UnidadeFactory
from sales.factories import PedidoFactory
from sales.interestadual import calcular_interestadual


class AliquotaInterestadualTests(TestCase):
    def test_venda_intrastadual_nao_interestadual(self):
        pedido = PedidoFactory(
            unidade=UnidadeFactory(uf="BA"),
            uf_entrega="BA",
        )

        self.assertFalse(pedido.interestadual)
        self.assertEqual(pedido.aliquota_icms, Decimal("0.0000"))

    def test_venda_ba_mg_interestadual(self):
        pedido = PedidoFactory(
            unidade=UnidadeFactory(uf="BA"),
            uf_entrega="MG",
        )

        self.assertTrue(pedido.interestadual)
        self.assertEqual(pedido.aliquota_icms, Decimal("0.1200"))

    def test_calculo_usa_uf_legada_quando_uf_entrega_ausente(self):
        pedido = PedidoFactory(
            unidade=UnidadeFactory(uf="BA"),
            uf="MG",
        )

        self.assertTrue(pedido.interestadual)
        self.assertEqual(pedido.aliquota_icms, Decimal("0.1200"))

    def test_unidade_sem_uf_nao_e_interestadual(self):
        pedido = PedidoFactory(unidade=UnidadeFactory(uf=""))
        self.assertFalse(pedido.interestadual)

        interestadual, aliquota = calcular_interestadual(pedido)
        self.assertFalse(interestadual)
        self.assertEqual(aliquota, Decimal("0.0000"))

    def test_mudanca_de_uf_recalcula_no_save(self):
        pedido = PedidoFactory(
            unidade=UnidadeFactory(uf="BA"),
            uf_entrega="BA",
        )
        self.assertFalse(pedido.interestadual)

        pedido.uf_entrega = "MG"
        pedido.save()

        pedido.refresh_from_db()
        self.assertTrue(pedido.interestadual)
        self.assertEqual(pedido.aliquota_icms, Decimal("0.1200"))

    def test_checkout_calcula_interestadual(self):
        from sales.tests.helpers import fluxo_checkout

        pedido = fluxo_checkout(
            self.client,
            quantidade=1,
            dados_extra={"uf": "MG"},
        )

        self.assertTrue(pedido.interestadual)
        self.assertEqual(pedido.aliquota_icms, Decimal("0.1200"))
        self.assertEqual(pedido.uf_entrega, "MG")
        self.assertEqual(pedido.uf, "MG")

    def test_pedido_sem_uf_nao_e_interestadual(self):
        pedido = PedidoFactory(unidade=UnidadeFactory(uf="BA"))

        self.assertFalse(pedido.interestadual)
        self.assertEqual(pedido.aliquota_icms, Decimal("0.0000"))
        self.assertEqual(pedido.uf_entrega, "")
