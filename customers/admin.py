from django import forms
from django.contrib import admin

from customers.services import revisar_vinculo_cliente

from .models import Cliente


class ClienteAdminForm(forms.ModelForm):
    justificativa_vinculo = forms.CharField(
        label="Justificativa da revisão de vínculo",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )

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
            "usuario",
            "vinculo_verificado",
            "justificativa_vinculo",
        )

    def clean(self):
        cleaned = super().clean()
        if (
            cleaned.get("vinculo_verificado")
            and not cleaned.get("usuario")
        ):
            raise forms.ValidationError(
                "Para marcar o vínculo como comprovado, informe o usuário."
            )
        if self.instance.pk:
            anterior = (
                Cliente.objects.filter(pk=self.instance.pk)
                .values_list("vinculo_verificado", flat=True)
                .first()
            )
            if (
                anterior != cleaned.get("vinculo_verificado")
                and not (cleaned.get("justificativa_vinculo") or "").strip()
            ):
                raise forms.ValidationError(
                    "Informe a justificativa para alterar o vínculo."
                )
        return cleaned


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    form = ClienteAdminForm
    list_display = (
        "nome",
        "documento",
        "email",
        "usuario",
        "vinculo_verificado",
    )
    list_filter = ("vinculo_verificado", "categoria", "tipo_pessoa")
    search_fields = ("nome", "documento", "email")
    readonly_fields = ("criado_em",)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if change and "vinculo_verificado" in form.changed_data:
            revisar_vinculo_cliente(
                cliente=obj,
                verificado=obj.vinculo_verificado,
                justificativa=form.cleaned_data.get(
                    "justificativa_vinculo"
                ) or "",
                request=request,
            )
