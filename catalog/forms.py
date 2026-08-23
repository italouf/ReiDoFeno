from django import forms

from .models import Categoria, Produto


class ProdutoForm(forms.ModelForm):
    class Meta:
        model = Produto
        fields = (
            "nome",
            "categoria",
            "ncm",
            "unidade_medida",
            "custo",
            "preco_balcao",
            "preco_online",
            "ativo",
        )


class CategoriaForm(forms.ModelForm):
    class Meta:
        model = Categoria
        fields = ("nome", "descricao", "ativa")
