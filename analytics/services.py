"""Métricas do painel — sempre a partir de dados reais, sem inventário fake."""
from datetime import date, datetime, time
from decimal import Decimal

from django.db.models import (
    Count,
    DateTimeField,
    Exists,
    F,
    Max,
    OuterRef,
    Q,
    Sum,
)
from django.utils import timezone

from costs.services import despesas_no_periodo
from sales.models import ItemPedido, Pagamento, Pedido

STATUS_AGUARDANDO = (
    Pedido.Status.AGUARDANDO_PAGAMENTO,
    Pedido.Status.PAGAMENTO_PENDENTE,
)
STATUS_FINANCEIROS_COM_RECEITA = (
    Pedido.StatusFinanceiro.PAGO,
    Pedido.StatusFinanceiro.ESTORNADO,
    Pedido.StatusFinanceiro.CANCELADO,
)
TIPOS_DEVOLUCAO = (
    Pedido.TipoCancelamento.PADRAO,
    Pedido.TipoCancelamento.DEVOLUCAO,
)


def _janela(inicio: date, fim: date):
    tz = timezone.get_current_timezone()
    começo = datetime.combine(inicio, time.min, tzinfo=tz)
    término = datetime.combine(fim, time.max, tzinfo=tz)
    return começo, término


def _excluir_aprovacao_pos_cancelamento(query, campo_aprovado):
    """Ignora aprovação tardia de pedido cancelado antes do pagamento."""
    return query.exclude(
        pedido__status=Pedido.Status.CANCELADO,
        pedido__cancelado_em__isnull=False,
        **{f"{campo_aprovado}__gt": F("pedido__cancelado_em")},
    )


def pagamentos_aprovados(inicio: date, fim: date, vendedor=None):
    """Pagamentos aprovados no período, sem aprovação tardia pós-cancelamento."""
    começo, término = _janela(inicio, fim)
    query = Pagamento.objects.filter(
        aprovado_em__range=(começo, término),
        aprovado_em__isnull=False,
        pedido__status_financeiro__in=STATUS_FINANCEIROS_COM_RECEITA,
    )
    query = _excluir_aprovacao_pos_cancelamento(query, "aprovado_em")
    if vendedor is not None:
        query = query.filter(pedido__usuario_criador=vendedor)
    return query.select_related("pedido", "pedido__unidade")


def pagamentos_estornados(inicio: date, fim: date, vendedor=None):
    """Estornos ocorridos no período, como eventos negativos."""
    começo, término = _janela(inicio, fim)
    query = Pagamento.objects.filter(
        estornado_em__range=(começo, término),
        estornado_em__isnull=False,
    )
    if vendedor is not None:
        query = query.filter(pedido__usuario_criador=vendedor)
    return query.select_related("pedido", "pedido__unidade")


def _itens_vendidos(inicio: date, fim: date, vendedor=None):
    começo, término = _janela(inicio, fim)
    query = (
        ItemPedido.objects.filter(
            pedido__pagamento__aprovado_em__range=(começo, término),
            pedido__pagamento__aprovado_em__isnull=False,
            pedido__status_financeiro__in=STATUS_FINANCEIROS_COM_RECEITA,
        )
        .exclude(
            pedido__status=Pedido.Status.CANCELADO,
            pedido__tipo_cancelamento__isnull=True,
        )
    )
    query = _excluir_aprovacao_pos_cancelamento(
        query, "pedido__pagamento__aprovado_em"
    )
    if vendedor is not None:
        query = query.filter(pedido__usuario_criador=vendedor)
    return query.select_related(
        "pedido__pagamento", "pedido__unidade", "produto"
    )


def _itens_devolvidos(inicio: date, fim: date, vendedor=None):
    começo, término = _janela(inicio, fim)
    query = ItemPedido.objects.filter(
        pedido__cancelado_em__range=(começo, término),
        pedido__cancelado_em__isnull=False,
        pedido__tipo_cancelamento__in=TIPOS_DEVOLUCAO,
    )
    if vendedor is not None:
        query = query.filter(pedido__usuario_criador=vendedor)
    return query.select_related("pedido__unidade", "produto")


def _linhas_itens(inicio: date, fim: date, unidade=None, vendedor=None):
    """Linhas de item com sinal: venda positiva, devolução negativa."""
    linhas = {}

    vendidos = _itens_vendidos(inicio, fim, vendedor=vendedor)
    if unidade is not None:
        vendidos = vendidos.filter(pedido__unidade=unidade)
    for item in vendidos:
        dia = timezone.localtime(
            item.pedido.pagamento.aprovado_em
        ).date()
        chave = (
            item.produto_id,
            item.produto_nome,
            item.pedido.unidade_id,
            item.pedido.unidade.nome,
            dia,
        )
        linha = linhas.setdefault(
            chave,
            {
                "quantidade": Decimal("0.00"),
                "receita": Decimal("0.00"),
                "cmv": Decimal("0.00"),
            },
        )
        linha["quantidade"] += item.quantidade
        linha["receita"] += item.subtotal
        linha["cmv"] += item.custo_unitario * item.quantidade

    devolvidos = _itens_devolvidos(inicio, fim, vendedor=vendedor)
    if unidade is not None:
        devolvidos = devolvidos.filter(pedido__unidade=unidade)
    for item in devolvidos:
        dia = timezone.localtime(item.pedido.cancelado_em).date()
        chave = (
            item.produto_id,
            item.produto_nome,
            item.pedido.unidade_id,
            item.pedido.unidade.nome,
            dia,
        )
        linha = linhas.setdefault(
            chave,
            {
                "quantidade": Decimal("0.00"),
                "receita": Decimal("0.00"),
                "cmv": Decimal("0.00"),
            },
        )
        linha["quantidade"] -= item.quantidade
        linha["receita"] -= item.subtotal
        linha["cmv"] -= item.custo_unitario * item.quantidade

    resultado = []
    for (
        produto_id,
        produto,
        unidade_id,
        unidade_nome,
        dia,
    ), valores in sorted(
        linhas.items(),
        key=lambda entrada: (
            entrada[0][4],
            entrada[0][1],
            entrada[0][3],
        ),
    ):
        if not any(valores.values()):
            continue
        resultado.append(
            {
                "produto_id": produto_id,
                "produto": produto,
                "unidade_id": unidade_id,
                "unidade": unidade_nome,
                "dia": dia,
                "quantidade": valores["quantidade"],
                "receita": valores["receita"],
                "cmv": valores["cmv"],
                "lucro_bruto": valores["receita"] - valores["cmv"],
            }
        )
    return resultado


def receita_do_periodo(inicio: date, fim: date) -> Decimal:
    """Receita por competência de pagamento aprovado menos estornos."""
    receitas = (
        pagamentos_aprovados(inicio, fim).aggregate(
            total=Sum("valor")
        )["total"]
        or Decimal("0.00")
    )
    estornos = (
        pagamentos_estornados(inicio, fim).aggregate(
            total=Sum("valor")
        )["total"]
        or Decimal("0.00")
    )
    return receitas - estornos


def metricas_do_periodo(
    inicio: date, fim: date, vendedor=None
) -> dict:
    """Vendas, CMV, top produtos, despesas e lucro no intervalo."""
    aprovados = pagamentos_aprovados(inicio, fim, vendedor=vendedor)
    estornos = pagamentos_estornados(inicio, fim, vendedor=vendedor)
    total_vendas = (
        aprovados.aggregate(total=Sum("valor"))["total"]
        or Decimal("0.00")
    ) - (
        estornos.aggregate(total=Sum("valor"))["total"]
        or Decimal("0.00")
    )
    pedidos_vendidos = aprovados.values("pedido_id").distinct().count()

    linhas = _linhas_itens(inicio, fim, vendedor=vendedor)
    receita_produtos = sum(
        (linha["receita"] for linha in linhas), Decimal("0.00")
    )
    cmv_total = sum(
        (linha["cmv"] for linha in linhas), Decimal("0.00")
    )
    lucro_bruto = receita_produtos - cmv_total

    produtos = {}
    for linha in linhas:
        dados = produtos.setdefault(
            linha["produto"],
            {
                "produto_nome": linha["produto"],
                "quantidade_vendida": Decimal("0.00"),
                "receita": Decimal("0.00"),
            },
        )
        dados["quantidade_vendida"] += linha["quantidade"]
        dados["receita"] += linha["receita"]
    top_produtos = sorted(
        produtos.values(),
        key=lambda linha: linha["quantidade_vendida"],
        reverse=True,
    )[:5]

    despesas_total = despesas_no_periodo(
        inicio, fim, usuario=vendedor
    )
    aguardando = Pedido.objects.filter(
        status_financeiro=Pedido.StatusFinanceiro.PENDENTE,
        status__in=STATUS_AGUARDANDO,
    )
    if vendedor is not None:
        aguardando = aguardando.filter(usuario_criador=vendedor)

    return {
        "inicio": inicio,
        "fim": fim,
        "receita": total_vendas,
        "num_pedidos": pedidos_vendidos,
        "total_vendas": total_vendas,
        "pedidos_vendidos": pedidos_vendidos,
        "top_produtos": top_produtos,
        "receita_produtos": receita_produtos,
        "cmv_total": cmv_total,
        "lucro_bruto": lucro_bruto,
        "despesas_total": despesas_total,
        "lucro_estimado": lucro_bruto - despesas_total,
        "aguardando_pagamento": aguardando.select_related(
            "cliente", "unidade"
        ),
        "aguardando_total": aguardando.count(),
    }


def vendas_por_produto(
    inicio: date, fim: date, unidade=None, vendedor=None
) -> list[dict]:
    """Vendas por produto/dia/unidade, com devoluções como linhas negativas."""
    return _linhas_itens(
        inicio, fim, unidade=unidade, vendedor=vendedor
    )


def comparativo_unidades(inicio: date, fim: date) -> list[dict]:
    """Receita, CMV, lucro, pedidos e ticket médio por unidade ativa."""
    from core.models import Unidade

    aprovados = (
        pagamentos_aprovados(inicio, fim)
        .values("pedido__unidade_id")
        .annotate(
            receita=Sum("valor"),
            num_pedidos=Count("pedido_id", distinct=True),
        )
    )
    estornos = (
        pagamentos_estornados(inicio, fim)
        .values("pedido__unidade_id")
        .annotate(total=Sum("valor"))
    )
    receitas = {linha["pedido__unidade_id"]: linha for linha in aprovados}
    estornos_por_unidade = {
        linha["pedido__unidade_id"]: linha["total"] for linha in estornos
    }
    cmv_por_unidade = {}
    for linha in _linhas_itens(inicio, fim):
        cmv_por_unidade[linha["unidade_id"]] = (
            cmv_por_unidade.get(linha["unidade_id"], Decimal("0.00"))
            + linha["cmv"]
        )

    resultado = []
    for unidade in Unidade.objects.filter(ativa=True).order_by("nome"):
        dados = receitas.get(unidade.pk, {})
        receita = (
            dados.get("receita") or Decimal("0.00")
        ) - (
            estornos_por_unidade.get(unidade.pk) or Decimal("0.00")
        )
        num_pedidos = dados.get("num_pedidos") or 0
        custo = cmv_por_unidade.get(unidade.pk) or Decimal("0.00")
        resultado.append(
            {
                "unidade": unidade.nome,
                "receita": receita,
                "cmv": custo,
                "lucro_bruto": receita - custo,
                "num_pedidos": num_pedidos,
                "ticket_medio": (
                    receita / num_pedidos
                    if num_pedidos
                    else Decimal("0.00")
                ),
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
