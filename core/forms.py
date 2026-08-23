from django import forms

from .models import Unidade


class UnidadeForm(forms.ModelForm):
    class Meta:
        model = Unidade
        fields = ("nome", "cidade", "tipo", "ativa")
