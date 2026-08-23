"""Fluxo auxiliar reutilizável: adiciona ao carrinho e conclui o checkout."""

from django.urls import reverse

from catalog.factories import ProdutoFactory
from core.factories import UnidadeFactory
from stock.factories import EstoqueFactory

DADOS_BASE = {
    "nome": "João Fazendeiro",
    "documento": "529.982.247-25",
    "email": "joao@example.com",
    "telefone": "(75) 99999-0001",
    "modalidade": "retirada",
}


def criar_produto_com_estoque(saldo="100.00", preco="10.00"):
    produto = ProdutoFactory(preco_online=preco)
    unidade = UnidadeFactory(nome="Feira de Santana")
    EstoqueFactory(
        produto=produto, unidade=unidade, quantidade=saldo
    )
    return produto, unidade


def fluxo_checkout(cliente_http, *, quantidade, dados_extra=None):
    """Cria produto/estoque, enche o carrinho e conclui o checkout.

    Retorna o Pedido criado em status aguardando_pagamento.
    """
    produto, _unidade = criar_produto_com_estoque()
    cliente_http.post(
        reverse("sales:adicionar"),
        {"produto_id": produto.pk, "quantidade": str(quantidade)},
    )

    from core.models import Unidade as ModeloUnidade

    dados = dict(DADOS_BASE)
    dados.update(dados_extra or {})
    dados["unidade"] = ModeloUnidade.objects.get().pk

    resposta = cliente_http.post(reverse("sales:checkout"), dados)
    assert resposta.status_code == 302, (
        "Checkout deveria redirecionar; erros: "
        f"{resposta.context['form'].errors if resposta.context else 'n/a'}"
    )

    from sales.models import Pedido

    pedido = (
        Pedido.objects.filter(cliente__documento="52998224725")
        .order_by("-pk")
        .first()
    )
    return pedido


def saldo_de(pedido):
    from stock.models import Estoque

    item = pedido.itens.select_related("produto").first()
    estoque = Estoque.objects.get(produto=item.produto, unidade=pedido.unidade)
    return estoque.quantidade, estoque.quantidade_bloqueada
