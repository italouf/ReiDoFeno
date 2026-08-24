"""Contexto global da loja: contador do carrinho e categorias ativas.

Não altera nenhuma lógica: apenas expõe dados já existentes para os templates.
"""
from catalog.models import Categoria

from .cart import Carrinho


def loja(request):
    return {
        "itens_carrinho": len(Carrinho(request)),
        "categorias_loja": Categoria.objects.filter(ativa=True).order_by("nome"),
    }
