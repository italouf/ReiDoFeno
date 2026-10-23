"""ANA-01: receita reconhecida por pagamento, não por andamento."""

from datetime import date, datetime, time
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from analytics.services import metricas_do_periodo, receita_do_periodo
from sales.factories import PagamentoFactory, PedidoFactory
from sales.models import Pagamento, Pedido


def _em(dia: date, hora: int = 12) -> datetime:
    return timezone.make_aware(datetime.combine(dia, time(hora, 0)))


def criar_pedido_pago(
    *,
    valor: Decimal = Decimal("100.00"),
    data: date | None = None,
    status: str = Pedido.Status.PAGO,
    status_financeiro: str = Pedido.StatusFinanceiro.PAGO,
    usuario_criador=None,
) -> Pedido:
    pedido = PedidoFactory(
        status=status,
        status_financeiro=status_financeiro,
        usuario_criador=usuario_criador,
        subtotal=valor,
        frete=Decimal("0.00"),
        total=valor,
    )
    PagamentoFactory(
        pedido=pedido,
        valor=valor,
        status=Pagamento.Status.APROVADO,
        aprovado_em=_em(data or timezone.localdate()),
    )
    return pedido


def estornar_pedido(pedido: Pedido, *, data: date) -> None:
    pagamento = pedido.pagamento
    pagamento.status = Pagamento.Status.CANCELADO
    pagamento.estornado_em = _em(data)
    pagamento.save(update_fields=["status", "estornado_em"])
    pedido.status_financeiro = Pedido.StatusFinanceiro.ESTORNADO
    pedido.save(update_fields=["status_financeiro"])


class ReceitaPorPagamentoTests(TestCase):
    """Receita reconhecida apenas quando há pagamento aprovado."""

    def test_pedido_pago_gera_receita(self):
        pedido = criar_pedido_pago(valor=Decimal("100.00"))
        dia = pedido.pagamento.aprovado_em.date()

        metricas = metricas_do_periodo(inicio=dia, fim=dia)

        self.assertEqual(metricas["receita"], Decimal("100.00"))

    def test_pedido_estornado_nao_gera_receita_liquida(self):
        pedido = criar_pedido_pago(valor=Decimal("100.00"))
        dia = pedido.pagamento.aprovado_em.date()
        estornar_pedido(pedido, data=dia)

        self.assertEqual(receita_do_periodo(dia, dia), Decimal("0.00"))

    def test_pedido_em_separacao_com_pagamento_aprovado_gera_receita(self):
        pedido = criar_pedido_pago(
            valor=Decimal("100.00"),
            status=Pedido.Status.EM_SEPARACAO,
        )
        dia = pedido.pagamento.aprovado_em.date()

        metricas = metricas_do_periodo(inicio=dia, fim=dia)

        self.assertEqual(metricas["receita"], Decimal("100.00"))

    def test_pedido_concluido_sem_pagamento_nao_gera_receita(self):
        pedido = PedidoFactory(
            status=Pedido.Status.CONCLUIDO,
            status_financeiro=Pedido.StatusFinanceiro.PENDENTE,
            subtotal=Decimal("100.00"),
            frete=Decimal("0.00"),
            total=Decimal("100.00"),
        )
        dia = timezone.localdate(pedido.criado_em)

        metricas = metricas_do_periodo(inicio=dia, fim=dia)

        self.assertEqual(metricas["receita"], Decimal("0.00"))

    def test_estorno_reduz_receita_no_periodo_do_estorno(self):
        pedido = criar_pedido_pago(
            valor=Decimal("100.00"), data=date(2026, 10, 1)
        )
        estornar_pedido(pedido, data=date(2026, 10, 5))

        receita_dia_1 = metricas_do_periodo(
            inicio=date(2026, 10, 1), fim=date(2026, 10, 1)
        )["receita"]
        receita_dia_5 = metricas_do_periodo(
            inicio=date(2026, 10, 5), fim=date(2026, 10, 5)
        )["receita"]

        self.assertEqual(receita_dia_1, Decimal("100.00"))
        self.assertEqual(receita_dia_5, Decimal("-100.00"))

    def test_serie_completa_fecha_em_zero_apos_estorno(self):
        pedido = criar_pedido_pago(
            valor=Decimal("100.00"), data=date(2026, 10, 1)
        )
        estornar_pedido(pedido, data=date(2026, 10, 5))

        total = receita_do_periodo(date(2026, 10, 1), date(2026, 10, 31))

        self.assertEqual(total, Decimal("0.00"))
