"""Métricas do painel — sempre a partir de dados reais, sem inventário fake."""
from datetime import date, datetime, time
from decimal import Decimal

from django.db.models import DateTimeField, DecimalField, Exists, F, Max, OuterRef, Q, Sum
from django.utils import timezone

from costs.services import despesas_no_periodo
from sales.models import ItemPedido, Pedido

STATUS_EXCLUIDOS_VENDA = (Pedido.Status.CANCELADO,)
STATUS_AGUARDANDO = (
    Pedido.Status.AGUARDANDO_PAGAMENTO,
    Pedido.Status.PAGAMENTO_PENDENTE,
)


def _janela(inicio: date, fim: date):
    tz = timezone.get_current_timezone()
    começo = datetime.combine(inicio, time.min, tzinfo=tz)
    término = datetime.combine(fim, time.max, tzinfo=tz)
    return começo, término


def metricas_do_periodo(inicio: date, fim: date) -> dict:
    """Vendas, top produtos, despesas e lucro do intervalo [inicio, fim].

    Pedidos cancelados/falhos ficam de fora das vendas.
    """
    começo, término = _janela(inicio, fim)
    vendas_qs = (
        Pedido.objects.filter(
            status_financeiro=Pedido.StatusFinanceiro.PAGO,
            criado_em__range=(começo, término),
        )
        .exclude(status__in=STATUS_EXCLUIDOS_VENDA)
    )

    total_vendas: Decimal = (
        vendas_qs.aggregate(soma=Sum("total"))["soma"] or Decimal("0.00")
    )

    top_produtos = (
        ItemPedido.objects.filter(
            pedido__status_financeiro=Pedido.StatusFinanceiro.PAGO,
            pedido__criado_em__range=(começo, término),
        )
        .exclude(pedido__status__in=STATUS_EXCLUIDOS_VENDA)
        .values("produto_nome")
        .annotate(
            quantidade_vendida=Sum("quantidade"),
            receita=Sum(
                F("preco_unitario") * F("quantidade"),
                output_field=DecimalField(max_digits=14, decimal_places=2),
            ),
        )
        .order_by("-quantidade_vendida")[:5]
    )

    despesas_total = despesas_no_periodo(inicio, fim)

    aguardando = Pedido.objects.filter(
        status_financeiro=Pedido.StatusFinanceiro.PENDENTE,
        status__in=STATUS_AGUARDANDO,
    )

    return {
        "inicio": inicio,
        "fim": fim,
        "total_vendas": total_vendas,
        "pedidos_vendidos": vendas_qs.count(),
        "top_produtos": top_produtos,
        "despesas_total": despesas_total,
        "lucro_estimado": total_vendas - despesas_total,
        "aguardando_pagamento": aguardando.select_related("cliente", "unidade"),
        "aguardando_total": aguardando.count(),
    }


def clientes_para_recompra(dias: int):
    """Clientes com compra paga/concluída há mais de `dias` dias."""
    from datetime import timedelta

    from customers.models import Cliente

    limite = timezone.now() - timedelta(days=dias)
    compras_antigas = (
        Pedido.objects.filter(
            cliente=OuterRef("pk"),
            status_financeiro=Pedido.StatusFinanceiro.PAGO,
            criado_em__lt=limite,
        )
        .exclude(status=Pedido.Status.CANCELADO)
    )
    return (
        Cliente.objects.filter(Exists(compras_antigas))
        .annotate(
            ultima_compra=Max(
                "pedidos__criado_em",
                filter=Q(
                    pedidos__status_financeiro=Pedido.StatusFinanceiro.PAGO
                )
                & ~Q(pedidos__status=Pedido.Status.CANCELADO),
                output_field=DateTimeField(),
            )
        )
        .filter(ultima_compra__lt=limite)
        .distinct()
    )
