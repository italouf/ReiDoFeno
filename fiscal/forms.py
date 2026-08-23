from django import forms


class NotaManualForm(forms.Form):
    numero = forms.CharField(label="Número da NF-e", max_length=20)
    chave_acesso = forms.CharField(label="Chave de acesso", max_length=44)
    link_documento = forms.URLField(
        label="Link do XML/DANFE", required=False
    )
