from django import forms

from .models import Cliente, InteracaoVendedor, normalizar_documento


class ClienteForm(forms.ModelForm):
    class Meta:
        model = Cliente
        fields = (
            "nome",
            "tipo_pessoa",
            "documento",
            "categoria",
            "telefone",
            "email",
            "logradouro",
            "numero",
            "bairro",
            "cidade",
            "uf",
            "cep",
            "preferencia",
        )

    def clean_documento(self):
        documento = normalizar_documento(self.cleaned_data["documento"])
        existentes = Cliente.objects.filter(documento=documento)
        if self.instance.pk:
            existentes = existentes.exclude(pk=self.instance.pk)
        if existentes.exists():
            raise forms.ValidationError("Este CPF/CNPJ já está cadastrado.")
        return documento


class InteracaoForm(forms.ModelForm):
    class Meta:
        model = InteracaoVendedor
        fields = ("tipo", "observacao", "pedido")
