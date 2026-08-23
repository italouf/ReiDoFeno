from datetime import date
from decimal import Decimal

import factory

from costs.models import Despesa


class DespesaFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Despesa

    categoria = Despesa.Categoria.OPERACIONAL
    tipo = "Aluguel do galpão"
    fornecedor = "Imobiliária Sítio"
    fornecedor_cnpj = ""
    valor = factory.LazyFunction(lambda: Decimal("1500.00"))
    recorrencia = Despesa.Recorrencia.MENSAL
    data = date(2026, 1, 1)
    observacao = ""
