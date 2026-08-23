import factory

from core.models import Unidade


class UnidadeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Unidade
        django_get_or_create = ("nome",)

    nome = "Feira de Santana"
    cidade = "Feira de Santana"
    tipo = Unidade.Tipo.LOJA
    ativa = True


class UnidadeIacuFactory(UnidadeFactory):
    nome = "Iaçu"
    cidade = "Iaçu"
