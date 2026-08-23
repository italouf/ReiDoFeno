from decimal import Decimal

import factory

from catalog.factories import ProdutoFactory
from core.factories import UnidadeFactory
from customers.factories import ClienteFactory
from sales.models import ItemPedido, Pagamento, Pedido


class PedidoFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Pedido

    cliente = factory.SubFactory(ClienteFactory)
    usuario_criador = None
    unidade = factory.SubFactory(UnidadeFactory)
    modalidade = Pedido.Modalidade.RETIRADA
    status = Pedido.Status.AGUARDANDO_PAGAMENTO
    canal = Pedido.Canal.LOJA


class ItemPedidoFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ItemPedido

    pedido = factory.SubFactory(PedidoFactory)
    produto = factory.SubFactory(ProdutoFactory)
    produto_nome = factory.LazyAttribute(lambda o: o.produto.nome)
    quantidade = factory.LazyFunction(lambda: Decimal("2.00"))
    preco_unitario = factory.LazyAttribute(lambda o: o.produto.preco_online)


class PagamentoFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Pagamento

    pedido = factory.SubFactory(PedidoFactory)
    valor = factory.LazyFunction(lambda: Decimal("100.00"))
    status = Pagamento.Status.PENDENTE
