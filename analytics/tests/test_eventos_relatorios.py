"""Coerência de eventos entre receita, CMV e relatórios após devolução."""

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from unittest import mock

from django.test import TestCase
from django.utils import timezone

from analytics.services import (
    comparativo_unidades,
    metricas_do_periodo,
    receita_do_periodo,
    vendas_por_produto,
)
from catalog.factories import ProdutoFactory
from core.factories import UnidadeFactory
from fiscal.services import relatorio_fiscal
from sales.factories import ItemPedidoFactory, PagamentoFactory, PedidoFactory
from sales.models import ObrigacaoEstoquePedido, Pagamento, Pedido
from stock.models import MovimentoEstoque


def _em(dia: date):
    return timezone.make_aware(datetime.combine(dia, time.min))


class EventosReceitaCmvTests(TestCase):
    def setUp(self):
        self.unidade = UnidadeFactory(uf="BA")
        self.produto = ProdutoFactory(nome="Feno Evento", custo=Decimal("30.00"))
        self.pedido = PedidoFactory(
            status=Pedido.Status.CONCLUIDO,
            unidade=self.unidade,
            uf_entrega="BA",
            subtotal=Decimal("100.00"),
            total=Decimal("100.00"),
        )
        ItemPedidoFactory(
            pedido=self.pedido,
            produto=self.produto,
            quantidade=2,
            preco_unitario=Decimal("50.00"),
            custo_unitario=Decimal("30.00"),
        )
        self.pagamento = PagamentoFactory(
            pedido=self.pedido,
            valor=Decimal("100.00"),
            status=Pagamento.Status.APROVADO,
            aprovado_em=_em(date(2026, 1, 1)),
        )

    def _devolver_em_fevereiro(self):
        self.pagamento.status = Pagamento.Status.CANCELADO
        self.pagamento.estornado_em = _em(date(2026, 2, 5))
        self.pagamento.save(update_fields=["status", "estornado_em"])
        self.pedido.status_financeiro = Pedido.StatusFinanceiro.ESTORNADO
        self.pedido.tipo_cancelamento = Pedido.TipoCancelamento.DEVOLUCAO
        self.pedido.cancelado_em = _em(date(2026, 2, 5))
        self.pedido.save(
            update_fields=[
                "status_financeiro",
                "tipo_cancelamento",
                "cancelado_em",
            ]
        )
        obrigacao = ObrigacaoEstoquePedido.objects.create(
            pedido=self.pedido,
            produto=self.produto,
            unidade=self.unidade,
            quantidade_devida=Decimal("2.00"),
            quantidade_baixada=Decimal("2.00"),
            status=ObrigacaoEstoquePedido.Status.RESOLVIDA,
        )
        with mock.patch(
            "django.utils.timezone.now",
            return_value=_em(date(2026, 2, 5)),
        ):
            MovimentoEstoque.objects.create(
                produto=self.produto,
                unidade=self.unidade,
                tipo=MovimentoEstoque.Tipo.ENTRADA_DEVOLUCAO,
                delta=Decimal("2.00"),
                obrigacao=obrigacao,
            )

    def test_cmv_e_lucro_permanecem_na_competencia_original(self):
        self._devolver_em_fevereiro()

        janeiro = metricas_do_periodo(
            date(2026, 1, 1), date(2026, 1, 31)
        )

        self.assertEqual(janeiro["receita"], Decimal("100.00"))
        self.assertEqual(janeiro["cmv_total"], Decimal("60.00"))
        self.assertEqual(janeiro["lucro_bruto"], Decimal("40.00"))

    def test_estorno_reverte_receita_e_cmv_na_data_do_evento(self):
        self._devolver_em_fevereiro()

        fevereiro = metricas_do_periodo(
            date(2026, 2, 1), date(2026, 2, 28)
        )

        self.assertEqual(fevereiro["receita"], Decimal("-100.00"))
        self.assertEqual(fevereiro["cmv_total"], Decimal("-60.00"))
        self.assertEqual(fevereiro["lucro_bruto"], Decimal("-40.00"))

    def test_relatorio_produto_inclui_devolucao_negativa(self):
        self._devolver_em_fevereiro()

        janeiro = vendas_por_produto(
            date(2026, 1, 1), date(2026, 1, 31), unidade=self.unidade
        )
        fevereiro = vendas_por_produto(
            date(2026, 2, 1), date(2026, 2, 28), unidade=self.unidade
        )

        self.assertEqual(janeiro[0]["quantidade"], Decimal("2.00"))
        self.assertEqual(janeiro[0]["receita"], Decimal("100.00"))
        self.assertEqual(janeiro[0]["cmv"], Decimal("60.00"))
        self.assertEqual(fevereiro[0]["quantidade"], Decimal("-2.00"))
        self.assertEqual(fevereiro[0]["receita"], Decimal("-100.00"))
        self.assertEqual(fevereiro[0]["cmv"], Decimal("-60.00"))

    def test_comparativo_reverte_receita_e_cmv(self):
        self._devolver_em_fevereiro()

        linhas = comparativo_unidades(
            date(2026, 2, 1), date(2026, 2, 28)
        )
        linha = next(
            item
            for item in linhas
            if item["unidade"] == self.unidade.nome
        )

        self.assertEqual(linha["receita"], Decimal("-100.00"))
        self.assertEqual(linha["cmv"], Decimal("-60.00"))
        self.assertEqual(linha["lucro_bruto"], Decimal("-40.00"))

    def test_relatorio_fiscal_reverte_no_periodo_do_estorno(self):
        self._devolver_em_fevereiro()

        janeiro = relatorio_fiscal(date(2026, 1, 1), date(2026, 1, 31))
        fevereiro = relatorio_fiscal(date(2026, 2, 1), date(2026, 2, 28))

        self.assertEqual(
            janeiro["vendas_intrastaduais"], Decimal("100.00")
        )
        self.assertEqual(
            fevereiro["vendas_intrastaduais"], Decimal("-100.00")
        )
        self.assertTrue(fevereiro["linhas"][0]["estorno"])

    def test_aprovacao_tardia_apos_cancelamento_nao_gera_receita(self):
        pedido = PedidoFactory(
            status=Pedido.Status.CANCELADO,
            status_financeiro=Pedido.StatusFinanceiro.CANCELADO,
            subtotal=Decimal("100.00"),
            total=Decimal("100.00"),
        )
        cancelado_em = timezone.now() - timedelta(hours=1)
        Pedido.objects.filter(pk=pedido.pk).update(
            cancelado_em=cancelado_em
        )
        PagamentoFactory(
            pedido=pedido,
            valor=Decimal("100.00"),
            status=Pagamento.Status.APROVADO,
            aprovado_em=timezone.now(),
        )
        dia = timezone.localdate()

        self.assertEqual(receita_do_periodo(dia, dia), Decimal("0.00"))
