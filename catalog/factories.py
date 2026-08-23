from decimal import Decimal

import factory

from catalog.models import Categoria, Produto


class CategoriaFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Categoria
        django_get_or_create = ("nome",)

    nome = factory.Sequence(lambda n: f"Categoria {n}")
    descricao = ""
    ativa = True


class ProdutoFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Produto

    nome = factory.Sequence(lambda n: f"Feno Tifton {n}")
    categoria = factory.SubFactory(CategoriaFactory)
    ncm = ""
    unidade_medida = Produto.UnidadeMedida.SACA
    custo = factory.LazyFunction(lambda: Decimal("80.00"))
    preco_balcao = factory.LazyFunction(lambda: Decimal("120.00"))
    preco_online = factory.LazyFunction(lambda: Decimal("110.00"))
    ativo = True
