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
from stock.models import MovimentoEstoque

STATUS_AGUARDANDO = (
    Pedido.Status.AGUARDANDO_PAGAMENTO,
    Pedido.Status.PAGAMENTO_PENDENTE,
)
STATUS_FINANCEIROS_COM_RECEITA = (
    Pedido.StatusFinanceiro.PAGO,
    Pedido.StatusFinanceiro.ESTORNADO,
    Pedido.StatusFinanceiro.CANCELADO,
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
    ).exclude(
        status=Pagamento.Status.CANCELADO,
        estornado_em__isnull=True,
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
        aprovado_em__isnull=False,
    )
    query = _excluir_aprovacao_pos_cancelamento(query, "aprovado_em")
    if vendedor is not None:
        query = query.filter(pedido__usuario_criador=vendedor)
    return query.select_related("pedido", "pedido__unidade")


def _itens_aprovados(inicio: date, fim: date, vendedor=None):
    """Itens de pagamentos que tiveram aprovação, para o CMV histórico."""
    começo, término = _janela(inicio, fim)
    query = ItemPedido.objects.filter(
        pedido__pagamento__aprovado_em__range=(começo, término),
        pedido__pagamento__aprovado_em__isnull=False,
        pedido__status_financeiro__in=STATUS_FINANCEIROS_COM_RECEITA,
    )
    query = _excluir_aprovacao_pos_cancelamento(
        query, "pedido__pagamento__aprovado_em"
    )
    if vendedor is not None:
        query = query.filter(pedido__usuario_criador=vendedor)
    return query.select_related(
        "pedido__pagamento", "pedido__unidade", "produto"
    )


def _itens_financeiros(inicio: date, fim: date, vendedor=None):
    """Itens cujo pagamento é elegível para receita reconhecida."""
    return _itens_aprovados(inicio, fim, vendedor=vendedor).exclude(
        pedido__pagamento__status=Pagamento.Status.CANCELADO,
        pedido__pagamento__estornado_em__isnull=True,
    )


def _movimentos_devolucao(inicio: date, fim: date, vendedor=None):
    """Retornos físicos comprovados, inclusive movimentos legados."""
    começo, término = _janela(inicio, fim)
    return MovimentoEstoque.objects.filter(
        tipo=MovimentoEstoque.Tipo.ENTRADA_DEVOLUCAO,
        delta__gt=Decimal("0.00"),
        criado_em__range=(começo, término),
    ).select_related("produto", "unidade", "obrigacao__pedido")


def _custo_medio_item(pedido, produto) -> Decimal:
    """Custo unitário médio dos itens do pedido para um produto."""
    itens = ItemPedido.objects.filter(pedido=pedido, produto=produto)
    quantidade = sum(
        (item.quantidade for item in itens), Decimal("0.00")
    )
    if quantidade <= 0:
        return Decimal("0.00")
    custo = sum(
        (
            item.custo_unitario * item.quantidade
            for item in itens
        ),
        Decimal("0.00"),
    )
    return custo / quantidade


def _linha(linhas, *, produto_id, produto, unidade_id, unidade, dia):
    chave = (produto_id, produto, unidade_id, unidade, dia)
    return linhas.setdefault(
        chave,
        {
            "quantidade": Decimal("0.00"),
            "quantidade_devolvida": Decimal("0.00"),
            "receita": Decimal("0.00"),
            "cmv": Decimal("0.00"),
        },
    )


def _linhas_itens(inicio: date, fim: date, unidade=None, vendedor=None):
    """Eventos de item: venda, estorno financeiro e retorno físico.

    A venda reconhece receita, quantidade financeira e CMV. O estorno
    financeiro reduz receita/quantidade, mas não o CMV. O retorno físico
    reduz apenas o CMV e alimenta a quantidade devolvida, sem criar uma
    segunda linha de receita.
    """
    linhas = {}

    vendidos = _itens_financeiros(inicio, fim, vendedor=vendedor)
    if unidade is not None:
        vendidos = vendidos.filter(pedido__unidade=unidade)
    for item in vendidos:
        dia = timezone.localtime(
            item.pedido.pagamento.aprovado_em
        ).date()
        linha = _linha(
            linhas,
            produto_id=item.produto_id,
            produto=item.produto_nome,
            unidade_id=item.pedido.unidade_id,
            unidade=item.pedido.unidade.nome,
            dia=dia,
        )
        linha["quantidade"] += item.quantidade
        linha["receita"] += item.subtotal

    # CMV é histórico: incerteza sobre estorno não apaga uma baixa/custo
    # comprovado. A receita elegível continua separada acima.
    itens_cmv = _itens_aprovados(inicio, fim, vendedor=vendedor)
    if unidade is not None:
        itens_cmv = itens_cmv.filter(pedido__unidade=unidade)
    for item in itens_cmv:
        dia = timezone.localtime(
            item.pedido.pagamento.aprovado_em
        ).date()
        linha = _linha(
            linhas,
            produto_id=item.produto_id,
            produto=item.produto_nome,
            unidade_id=item.pedido.unidade_id,
            unidade=item.pedido.unidade.nome,
            dia=dia,
        )
        linha["cmv"] += item.custo_unitario * item.quantidade

    estornos = pagamentos_estornados(inicio, fim, vendedor=vendedor)
    for pagamento in estornos:
        itens = ItemPedido.objects.filter(pedido=pagamento.pedido)
        if unidade is not None:
            itens = itens.filter(pedido__unidade=unidade)
        dia = timezone.localtime(pagamento.estornado_em).date()
        for item in itens:
            linha = _linha(
                linhas,
                produto_id=item.produto_id,
                produto=item.produto_nome,
                unidade_id=pagamento.pedido.unidade_id,
                unidade=pagamento.pedido.unidade.nome,
                dia=dia,
            )
            linha["quantidade"] -= item.quantidade
            linha["receita"] -= item.subtotal

    devolvidos = _movimentos_devolucao(inicio, fim)
    from sales.services import _obrigacao_por_movimento

    for movimento in devolvidos:
        obrigacao = movimento.obrigacao or _obrigacao_por_movimento(
            movimento
        )
        if obrigacao is None:
            continue
        pedido = obrigacao.pedido
        if vendedor is not None and pedido.usuario_criador_id != vendedor.pk:
            continue
        if unidade is not None and movimento.unidade_id != unidade.pk:
            continue
        custo_unitario = _custo_medio_item(pedido, movimento.produto)
        dia = timezone.localtime(movimento.criado_em).date()
        linha = _linha(
            linhas,
            produto_id=movimento.produto_id,
            produto=movimento.produto.nome,
            unidade_id=movimento.unidade_id,
            unidade=movimento.unidade.nome,
            dia=dia,
        )
        linha["quantidade_devolvida"] += movimento.delta
        linha["cmv"] -= custo_unitario * movimento.delta

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
                "quantidade_devolvida": valores["quantidade_devolvida"],
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
    conciliacao = Pagamento.objects.filter(
        aprovado_em__range=_janela(inicio, fim),
        aprovado_em__isnull=False,
        status=Pagamento.Status.CANCELADO,
        estornado_em__isnull=True,
        pedido__status_financeiro__in=STATUS_FINANCEIROS_COM_RECEITA,
    )
    if vendedor is not None:
        conciliacao = conciliacao.filter(pedido__usuario_criador=vendedor)
    receita_em_conciliacao = (
        conciliacao.aggregate(total=Sum("valor"))["total"]
        or Decimal("0.00")
    )

    linhas = _linhas_itens(inicio, fim, vendedor=vendedor)
    receita_produtos = sum(
        (linha["receita"] for linha in linhas), Decimal("0.00")
    )
    cmv_total = sum(
        (linha["cmv"] for linha in linhas), Decimal("0.00")
    )
    receita_frete = total_vendas - receita_produtos
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
        "receita_frete": receita_frete,
        "receita_em_conciliacao": receita_em_conciliacao,
        "cmv_total": cmv_total,
        "lucro_bruto": lucro_bruto,
        "despesas_total": despesas_total,
        "lucro_estimado": total_vendas - cmv_total - despesas_total,
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
    receita_produtos_por_unidade = {}
    for linha in _linhas_itens(inicio, fim):
        unidade_id = linha["unidade_id"]
        cmv_por_unidade[unidade_id] = (
            cmv_por_unidade.get(unidade_id, Decimal("0.00"))
            + linha["cmv"]
        )
        receita_produtos_por_unidade[unidade_id] = (
            receita_produtos_por_unidade.get(
                unidade_id, Decimal("0.00")
            )
            + linha["receita"]
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
        receita_produtos = (
            receita_produtos_por_unidade.get(unidade.pk)
            or Decimal("0.00")
        )
        resultado.append(
            {
                "unidade": unidade.nome,
                "receita": receita,
                "receita_produtos": receita_produtos,
                "receita_frete": receita - receita_produtos,
                "cmv": custo,
                "lucro_bruto": receita_produtos - custo,
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
