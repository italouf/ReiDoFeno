"""Métricas do painel — sempre a partir de dados reais, sem inventário fake."""
from datetime import date, datetime, time
from decimal import Decimal

from django.db.models import DateTimeField, DecimalField, F, Max, Q, Sum
from django.utils import timezone

from costs.services import despesas_no_periodo
from sales.models import ItemPedido, Pedido

STATUS_VENDA = (
    Pedido.Status.PAGO,
    Pedido.Status.CONCLUIDO,
)

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
    vendas_qs = Pedido.objects.filter(
        status__in=STATUS_VENDA,
        criado_em__range=(começo, término),
    )

    total_vendas: Decimal = (
        vendas_qs.aggregate(soma=Sum("total"))["soma"] or Decimal("0.00")
    )

    top_produtos = (
        ItemPedido.objects.filter(
            pedido__status__in=STATUS_VENDA,
            pedido__criado_em__range=(começo, término),
        )
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

    aguardando = Pedido.objects.filter(status__in=STATUS_AGUARDANDO)

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
    return (
        Cliente.objects.annotate(
            ultima_compra=Max(
                "pedidos__criado_em",
                filter=Q(pedidos__status__in=STATUS_VENDA),
                output_field=DateTimeField(),
            )
        )
        .filter(
            pedidos__status__in=STATUS_VENDA,
            pedidos__criado_em__lt=limite,
            ultima_compra__lt=limite,
        )
        .distinct()
    )
