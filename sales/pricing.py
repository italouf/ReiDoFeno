"""Cotação de preços do checkout (compartilhada entre carrinho e pedido)."""

from decimal import Decimal

from catalog.models import Produto
from customers.models import Cliente
from sales.models import ItemPedido

LIMIAR_ATACADO = Decimal("50.00")


def calcular_preco_unitario(
    *, produto, cliente, quantidade, preco_base=None
) -> Decimal:
    """Preço do item no checkout, com a regra de atacado (>50 fardos).

    A elegibilidade (vínculo comprovado/vendedor interno) é decidida pelo
    chamador, que passa ``cliente`` apenas quando a tabela é permitida.
    """
    base = produto.preco_balcao if preco_base is None else preco_base
    quantidade = Decimal(str(quantidade))
    if (
        cliente is not None
        and cliente.categoria == Cliente.Categoria.ATACADO
        and produto.unidade_medida == Produto.UnidadeMedida.FARDO
        and quantidade > LIMIAR_ATACADO
        and produto.preco_atacado is not None
    ):
        return produto.preco_atacado
    return base


def calcular_item_pedido(
    *, produto, cliente, quantidade, preco_base=None
) -> ItemPedido:
    """Monta um ``ItemPedido`` não persistido com o preço correto."""
    quantidade = Decimal(str(quantidade))
    return ItemPedido(
        produto=produto,
        produto_nome=produto.nome,
        quantidade=quantidade,
        preco_unitario=calcular_preco_unitario(
            produto=produto,
            cliente=cliente,
            quantidade=quantidade,
            preco_base=preco_base,
        ),
    )
