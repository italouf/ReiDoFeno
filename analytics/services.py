"""Métricas do painel — sempre a partir de dados reais, sem inventário fake."""
from datetime import date, datetime, time
from decimal import Decimal

from django.db.models import DateTimeField, DecimalField, Exists, F, Max, OuterRef, Q, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

from costs.services import despesas_no_periodo
from sales.models import ItemPedido, Pagamento, Pedido

STATUS_EXCLUIDOS_VENDA = (Pedido.Status.CANCELADO,)
STATUS_AGUARDANDO = (
    Pedido.Status.AGUARDANDO_PAGAMENTO,
    Pedido.Status.PAGAMENTO_PENDENTE,
)
STATUS_FINANCEIROS_COM_RECEITA = (
    Pedido.StatusFinanceiro.PAGO,
    Pedido.StatusFinanceiro.ESTORNADO,
)


def _janela(inicio: date, fim: date):
    tz = timezone.get_current_timezone()
    começo = datetime.combine(inicio, time.min, tzinfo=tz)
    término = datetime.combine(fim, time.max, tzinfo=tz)
    return começo, término


def receita_do_periodo(inicio: date, fim: date) -> Decimal:
    """Receita por competência de pagamento aprovado menos estornos.

    A data da receita é ``Pagamento.aprovado_em``. Um estorno não apaga a
    receita histórica: ele entra como evento negativo em ``estornado_em``.
    ``Pedido.status`` não participa do cálculo.
    """
    começo, término = _janela(inicio, fim)

    receitas = (
        Pagamento.objects.filter(
            aprovado_em__range=(começo, término),
            aprovado_em__isnull=False,
            pedido__status_financeiro__in=STATUS_FINANCEIROS_COM_RECEITA,
        ).aggregate(total=Sum("valor"))["total"]
        or Decimal("0.00")
    )
    estornos = (
        Pagamento.objects.filter(
            estornado_em__range=(começo, término),
            estornado_em__isnull=False,
        ).aggregate(total=Sum("valor"))["total"]
        or Decimal("0.00")
    )
    return receitas - estornos


def metricas_do_periodo(
    inicio: date, fim: date, vendedor=None
) -> dict:
    """Vendas, top produtos, despesas e lucro do intervalo [inicio, fim].

    A receita é reconhecida por pagamento aprovado (ANA-01), não pelo
    andamento operacional. Pedidos cancelados antes do pagamento ficam fora.
    ``vendedor`` aplica o recorte do ADR-010; ``None`` é a visão global.
    """
    começo, término = _janela(inicio, fim)
    pagamentos = Pagamento.objects.filter(
        aprovado_em__range=(começo, término),
        aprovado_em__isnull=False,
        pedido__status_financeiro__in=STATUS_FINANCEIROS_COM_RECEITA,
    )
    itens = ItemPedido.objects.filter(
        pedido__pagamento__aprovado_em__range=(começo, término),
        pedido__pagamento__aprovado_em__isnull=False,
        pedido__status_financeiro__in=STATUS_FINANCEIROS_COM_RECEITA,
    )
    aguardando = Pedido.objects.filter(
        status_financeiro=Pedido.StatusFinanceiro.PENDENTE,
        status__in=STATUS_AGUARDANDO,
    )
    if vendedor is not None:
        pagamentos = pagamentos.filter(pedido__usuario_criador=vendedor)
        itens = itens.filter(pedido__usuario_criador=vendedor)
        aguardando = aguardando.filter(usuario_criador=vendedor)

    pedidos_vendidos = pagamentos.values("pedido_id").distinct().count()
    total_vendas = (
        pagamentos.aggregate(total=Sum("valor"))["total"]
        or Decimal("0.00")
    )
    estornos = Pagamento.objects.filter(
        estornado_em__range=(começo, término),
        estornado_em__isnull=False,
    )
    if vendedor is not None:
        estornos = estornos.filter(pedido__usuario_criador=vendedor)
    total_vendas -= (
        estornos.aggregate(total=Sum("valor"))["total"]
        or Decimal("0.00")
    )

    top_produtos = (
        itens.exclude(pedido__status__in=STATUS_EXCLUIDOS_VENDA)
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

    cmv_total = (
        itens.filter(
            pedido__status_financeiro=Pedido.StatusFinanceiro.PAGO
        )
        .exclude(pedido__status__in=STATUS_EXCLUIDOS_VENDA)
        .aggregate(
            total=Sum(
                F("custo_unitario") * F("quantidade"),
                output_field=DecimalField(max_digits=14, decimal_places=2),
            )
        )["total"]
        or Decimal("0.00")
    )
    despesas_total = despesas_no_periodo(
        inicio, fim, usuario=vendedor
    )
    lucro_bruto = total_vendas - cmv_total

    return {
        "inicio": inicio,
        "fim": fim,
        "receita": total_vendas,
        "num_pedidos": pedidos_vendidos,
        "total_vendas": total_vendas,
        "pedidos_vendidos": pedidos_vendidos,
        "top_produtos": top_produtos,
        "cmv_total": cmv_total,
        "lucro_bruto": lucro_bruto,
        "despesas_total": despesas_total,
        "lucro_estimado": lucro_bruto - despesas_total,
        "aguardando_pagamento": aguardando.select_related("cliente", "unidade"),
        "aguardando_total": aguardando.count(),
    }


def vendas_por_produto(
    inicio: date, fim: date, unidade=None, vendedor=None
) -> list[dict]:
    """Vendas agrupadas por produto, dia de aprovação e unidade.

    A receita é a dos itens (preço × quantidade); frete não é receita de
    produto. CMV usa o snapshot de custo do item (ADR-008).
    """
    começo, término = _janela(inicio, fim)
    itens = ItemPedido.objects.filter(
        pedido__pagamento__aprovado_em__range=(começo, término),
        pedido__pagamento__aprovado_em__isnull=False,
        pedido__status_financeiro=Pedido.StatusFinanceiro.PAGO,
    ).exclude(pedido__status__in=STATUS_EXCLUIDOS_VENDA)
    if unidade is not None:
        itens = itens.filter(pedido__unidade=unidade)
    if vendedor is not None:
        itens = itens.filter(pedido__usuario_criador=vendedor)

    linhas = (
        itens.annotate(
            dia=TruncDate("pedido__pagamento__aprovado_em")
        )
        .values("produto__nome", "pedido__unidade__nome", "dia")
        .annotate(
            quantidade_total=Sum("quantidade"),
            receita=Sum(
                F("preco_unitario") * F("quantidade"),
                output_field=DecimalField(max_digits=14, decimal_places=2),
            ),
            cmv=Sum(
                F("custo_unitario") * F("quantidade"),
                output_field=DecimalField(max_digits=14, decimal_places=2),
            ),
        )
        .order_by("dia", "produto__nome", "pedido__unidade__nome")
    )

    resultado = []
    for linha in linhas:
        receita = linha["receita"] or Decimal("0.00")
        cmv = linha["cmv"] or Decimal("0.00")
        resultado.append(
            {
                "produto": linha["produto__nome"],
                "unidade": linha["pedido__unidade__nome"],
                "dia": linha["dia"],
                "quantidade": linha["quantidade_total"] or Decimal("0.00"),
                "receita": receita,
                "cmv": cmv,
                "lucro_bruto": receita - cmv,
            }
        )
    return resultado


def clientes_para_recompra(dias: int, vendedor=None):
    """Clientes com compra paga há mais de `dias` dias.

    Com ``vendedor``, tanto a existência da compra antiga quanto a data da
    última compra consideram apenas pedidos criados por ele (ADR-010).
    """
    from datetime import timedelta

    from customers.models import Cliente

    limite = timezone.now() - timedelta(days=dias)
    filtro_antigo = Q(
        cliente=OuterRef("pk"),
        status_financeiro=Pedido.StatusFinanceiro.PAGO,
        criado_em__lt=limite,
    )
    filtro_ultima = Q(
        pedidos__status_financeiro=Pedido.StatusFinanceiro.PAGO
    ) & ~Q(pedidos__status=Pedido.Status.CANCELADO)
    if vendedor is not None:
        filtro_antigo &= Q(usuario_criador=vendedor)
        filtro_ultima &= Q(pedidos__usuario_criador=vendedor)

    compras_antigas = Pedido.objects.filter(filtro_antigo).exclude(
        status=Pedido.Status.CANCELADO
    )
    return (
        Cliente.objects.filter(Exists(compras_antigas))
        .annotate(
            ultima_compra=Max(
                "pedidos__criado_em",
                filter=filtro_ultima,
                output_field=DateTimeField(),
            )
        )
        .filter(ultima_compra__lt=limite)
        .distinct()
    )
