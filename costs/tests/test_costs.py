from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from costs.factories import DespesaFactory
from costs.models import Despesa
from costs.services import despesas_no_periodo


class DespesaModelTests(TestCase):
    def test_cnpj_invalido_do_fornecedor_e_rejeitado(self):
        despesa = DespesaFactory.build(fornecedor_cnpj="11.222.333/0001-99")
        with self.assertRaises(ValidationError):
            despesa.full_clean()

    def test_valor_negativo_e_rejeitado(self):
        despesa = DespesaFactory.build(valor=Decimal("-1"))
        with self.assertRaises(ValidationError):
            despesa.full_clean()


class DespesasNoPeriodoTests(TestCase):
    def test_despesa_unica_dentro_do_periodo(self):
        DespesaFactory(
            recorrencia=Despesa.Recorrencia.UNICA,
            data=date(2026, 3, 10),
            valor=Decimal("200.00"),
        )
        total = despesas_no_periodo(date(2026, 3, 1), date(2026, 3, 31))
        self.assertEqual(total, Decimal("200.00"))

    def test_despesa_unica_fora_do_periodo(self):
        DespesaFactory(
            recorrencia=Despesa.Recorrencia.UNICA,
            data=date(2026, 2, 10),
            valor=Decimal("200.00"),
        )
        total = despesas_no_periodo(date(2026, 3, 1), date(2026, 3, 31))
        self.assertEqual(total, Decimal("0.00"))

    def test_despesa_mensal_conta_em_cada_mes(self):
        DespesaFactory(valor=Decimal("100.00"), data=date(2026, 1, 15))
        total = despesas_no_periodo(date(2026, 2, 1), date(2026, 3, 31))
        self.assertEqual(total, Decimal("200.00"))

    def test_despesa_mensal_antes_do_inicio_nao_retroage(self):
        DespesaFactory(valor=Decimal("100.00"), data=date(2026, 5, 1))
        total = despesas_no_periodo(date(2026, 2, 1), date(2026, 3, 31))
        self.assertEqual(total, Decimal("0.00"))

    def test_despesa_anual_conta_uma_vez_por_ano(self):
        DespesaFactory(
            recorrencia=Despesa.Recorrencia.ANUAL,
            valor=Decimal("1200.00"),
            data=date(2024, 7, 1),
        )
        total = despesas_no_periodo(date(2026, 1, 1), date(2026, 12, 31))
        self.assertEqual(total, Decimal("1200.00"))
