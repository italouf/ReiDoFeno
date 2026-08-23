from django import forms

from .models import Despesa


class DespesaForm(forms.ModelForm):
    class Meta:
        model = Despesa
        fields = (
            "categoria",
            "tipo",
            "fornecedor",
            "fornecedor_cnpj",
            "valor",
            "recorrencia",
            "data",
            "observacao",
        )
        widgets = {
            "data": forms.DateInput(attrs={"type": "date"}),
        }
