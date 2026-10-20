from django import forms
from django.contrib import admin
from django.utils import timezone

from core.auditoria import registrar_auditoria
from customers.services import revisar_vinculo_cliente

from .models import Cliente, VinculoClienteToken, normalizar_documento


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
                .values(
                    "usuario_id",
                    "email",
                    "documento",
                    "vinculo_verificado",
                )
                .first()
            )
            if anterior is not None:
                usuario = cleaned.get("usuario")
                usuario_novo = usuario.pk if usuario else None
                documento_novo = normalizar_documento(
                    cleaned.get("documento") or ""
                )
                identidade_mudou = (
                    anterior["usuario_id"] != usuario_novo
                    or anterior["email"] != (cleaned.get("email") or "")
                    or anterior["documento"] != documento_novo
                    or anterior["vinculo_verificado"]
                    != bool(cleaned.get("vinculo_verificado"))
                )
                if identidade_mudou and not (
                    cleaned.get("justificativa_vinculo") or ""
                ).strip():
                    raise forms.ValidationError(
                        "Informe a justificativa para alterar identidade, "
                        "e-mail, documento ou vínculo."
                    )
        elif cleaned.get("vinculo_verificado") and not (
            cleaned.get("justificativa_vinculo") or ""
        ).strip():
            raise forms.ValidationError(
                "Informe a justificativa para comprovar o vínculo na criação."
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
        antes = None
        if change:
            antes = (
                Cliente.objects.filter(pk=obj.pk)
                .values(
                    "usuario_id",
                    "email",
                    "documento",
                    "vinculo_verificado",
                )
                .first()
            )
        super().save_model(request, obj, form, change)
        if not change:
            if obj.vinculo_verificado:
                revisar_vinculo_cliente(
                    cliente=obj,
                    verificado=True,
                    justificativa=form.cleaned_data.get(
                        "justificativa_vinculo"
                    ) or "",
                    request=request,
                    antes={
                        "usuario_id": None,
                        "vinculo_verificado": False,
                    },
                )
            return
        if antes is None:
            return

        depois = {
            "usuario_id": obj.usuario_id,
            "email": obj.email,
            "documento": obj.documento,
            "vinculo_verificado": obj.vinculo_verificado,
            "justificativa": (
                form.cleaned_data.get("justificativa_vinculo") or ""
            )[:500],
        }
        identidade_mudou = (
            antes["usuario_id"] != obj.usuario_id
            or antes["email"] != obj.email
            or antes["documento"] != obj.documento
        )
        if identidade_mudou:
            # Troca de usuário/e-mail/documento nunca herda comprovação
            # nem o histórico privado do titular anterior.
            if obj.vinculo_verificado:
                obj.vinculo_verificado = False
                obj.save(update_fields=["vinculo_verificado"])
                depois["vinculo_verificado"] = False
            VinculoClienteToken.objects.filter(cliente=obj).update(
                revogado_em=timezone.now()
            )
            from sales.models import Pedido

            Pedido.objects.filter(cliente=obj).update(
                identidade_verificada=False
            )
            registrar_auditoria(
                acao="cliente.identidade_alterada_admin",
                instancia=obj,
                request=request,
                antes=antes,
                depois=depois,
            )
        elif antes["vinculo_verificado"] != obj.vinculo_verificado:
            revisar_vinculo_cliente(
                cliente=obj,
                verificado=obj.vinculo_verificado,
                justificativa=depois["justificativa"],
                request=request,
                antes=antes,
            )
