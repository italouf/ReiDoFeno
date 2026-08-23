import factory

from customers.models import Cliente
from customers.validators import _calcula_digito


def cpf_valido(n: int) -> str:
    """Gera um CPF numérico válido e determinístico para testes."""
    base = f"{n:09d}"[-9:]
    d1 = _calcula_digito(base, tuple(range(10, 1, -1)))
    d2 = _calcula_digito(base + str(d1), tuple(range(11, 1, -1)))
    return base + f"{d1}{d2}"


class ClienteFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Cliente
        django_get_or_create = ("documento",)

    nome = factory.Sequence(lambda n: f"Cliente {n}")
    tipo_pessoa = Cliente.TipoPessoa.FISICA
    documento = factory.Sequence(cpf_valido)
    categoria = Cliente.Categoria.VAREJO
    telefone = factory.Sequence(lambda n: f"(75) 9{n:04d}-0000")
    email = factory.LazyAttribute(
        lambda o: f"{o.nome.replace(' ', '').lower()}@example.com"
    )
    cidade = "Feira de Santana"
    uf = "BA"
