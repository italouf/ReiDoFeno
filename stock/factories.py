from decimal import Decimal

import factory

from catalog.factories import ProdutoFactory
from core.factories import UnidadeFactory
from stock.models import Estoque


class EstoqueFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Estoque
        django_get_or_create = ("produto", "unidade")

    produto = factory.SubFactory(ProdutoFactory)
    unidade = factory.SubFactory(UnidadeFactory)
    quantidade = factory.LazyFunction(lambda: Decimal("100.00"))
    quantidade_minima = factory.LazyFunction(lambda: Decimal("10.00"))
    quantidade_bloqueada = factory.LazyFunction(lambda: Decimal("0.00"))
