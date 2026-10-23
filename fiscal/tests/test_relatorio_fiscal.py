"""Relatório fiscal: separação de vendas internas e interestaduais."""

from datetime import date, datetime, time
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from core.factories import UnidadeFactory
from fiscal.services import relatorio_fiscal
from sales.factories import PagamentoFactory, PedidoFactory
from sales.models import Pagamento, Pedido

DIA = date(2026, 10, 1)


def _pedido_pago(uf_entrega: str, valor: Decimal, unidade):
    pedido = PedidoFactory(
        status=Pedido.Status.PAGO,
        unidade=unidade,
        uf_entrega=uf_entrega,
        subtotal=valor,
        total=valor,
    )
    PagamentoFactory(
        pedido=pedido,
        valor=valor,
        status=Pagamento.Status.APROVADO,
        aprovado_em=timezone.make_aware(datetime.combine(DIA, time.min)),
    )
    return pedido


class RelatorioFiscalTests(TestCase):
    def test_separa_vendas_intrastaduais_e_interestaduais(self):
        unidade = UnidadeFactory(uf="BA")
        _pedido_pago("BA", Decimal("100.00"), unidade)
        _pedido_pago("MG", Decimal("200.00"), unidade)

        relatorio = relatorio_fiscal(DIA, DIA)

        self.assertEqual(
            relatorio["vendas_intrastaduais"], Decimal("100.00")
        )
        self.assertEqual(
            relatorio["vendas_interestaduais"], Decimal("200.00")
        )
        self.assertEqual(
            relatorio["aliquota_interestadual"], Decimal("0.1200")
        )

    def test_linhas_destacam_interestadual(self):
        unidade = UnidadeFactory(uf="BA")
        _pedido_pago("MG", Decimal("200.00"), unidade)

        relatorio = relatorio_fiscal(DIA, DIA)

        self.assertEqual(len(relatorio["linhas"]), 1)
        linha = relatorio["linhas"][0]
        self.assertTrue(linha["interestadual"])
        self.assertEqual(linha["aliquota_icms"], Decimal("0.1200"))
        self.assertEqual(linha["uf_entrega"], "MG")

    def test_periodo_fora_nao_entra(self):
        unidade = UnidadeFactory(uf="BA")
        _pedido_pago("MG", Decimal("200.00"), unidade)

        relatorio = relatorio_fiscal(date(2026, 9, 1), date(2026, 9, 30))

        self.assertEqual(
            relatorio["vendas_interestaduais"], Decimal("0.00")
        )
        self.assertEqual(relatorio["linhas"], [])
