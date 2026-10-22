from django import forms
from django.core.validators import RegexValidator


class NotaManualForm(forms.Form):
    numero = forms.CharField(label="Número da NF-e", max_length=20)
    chave_acesso = forms.CharField(
        label="Chave de acesso",
        max_length=44,
        validators=[RegexValidator(r"^\d{44}$", "Informe 44 dígitos.")],
    )
    cfop = forms.CharField(
        label="CFOP",
        max_length=10,
        required=False,
        help_text="Preenchido automaticamente quando vazio.",
    )
    link_documento = forms.URLField(
        label="Link do XML/DANFE", required=False
    )
