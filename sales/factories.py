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
    status_financeiro = factory.LazyAttribute(
        lambda o: (
            Pedido.StatusFinanceiro.PAGO
            if o.status
            in (
                Pedido.Status.PAGO,
                Pedido.Status.EM_SEPARACAO,
                Pedido.Status.PRONTO_PARA_ENTREGA,
                Pedido.Status.ENVIADO,
                Pedido.Status.CONCLUIDO,
            )
            else (
                Pedido.StatusFinanceiro.CANCELADO
                if o.status
                in (Pedido.Status.CANCELADO, Pedido.Status.FALHOU)
                else Pedido.StatusFinanceiro.PENDENTE
            )
        )
    )
    financeiro_conciliado = factory.LazyAttribute(
        lambda o: (
            o.status_financeiro == Pedido.StatusFinanceiro.PAGO
        )
    )
    canal = Pedido.Canal.LOJA


class ItemPedidoFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ItemPedido

    pedido = factory.SubFactory(PedidoFactory)
    produto = factory.SubFactory(ProdutoFactory)
    produto_nome = factory.LazyAttribute(lambda o: o.produto.nome)
    quantidade = factory.LazyFunction(lambda: Decimal("2.00"))
    preco_unitario = factory.LazyAttribute(lambda o: o.produto.preco_online)
    custo_unitario = factory.LazyAttribute(lambda o: o.produto.custo)


class PagamentoFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Pagamento

    pedido = factory.SubFactory(PedidoFactory)
    valor = factory.LazyFunction(lambda: Decimal("100.00"))
    status = Pagamento.Status.PENDENTE
