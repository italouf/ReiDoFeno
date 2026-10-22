from django import forms

from accounts.models import Usuario

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
            "usuario_responsavel",
            "observacao",
        )
        widgets = {
            "data": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["usuario_responsavel"].queryset = (
            Usuario.objects.filter(
                is_active=True,
                groups__name__in=("Administrador", "Gestor", "Vendedor"),
            )
            .distinct()
            .order_by("username")
        )
