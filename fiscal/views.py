from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.generic import FormView

from core.auditoria import registrar_auditoria
from core.mixins import GrupoRequiredMixin
from sales.models import Pedido

from .forms import NotaManualForm
from .models import NotaFiscal

GRUPOS_FISCAIS = ("Administrador", "Gestor")


class RegistrarNotaManualView(
    LoginRequiredMixin, GrupoRequiredMixin, FormView
):
    """Fallback: registra NF-e emitida fora do sistema (auditável)."""

    form_class = NotaManualForm
    template_name = "fiscal/nota_manual_form.html"
    grupos_permitidos = GRUPOS_FISCAIS

    def dispatch(self, request, *args, **kwargs):
        self.pedido = get_object_or_404(Pedido, pk=self.kwargs["pedido_pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["pedido"] = self.pedido
        return contexto

    def form_valid(self, form):
        nota, _criada = NotaFiscal.objects.get_or_create(pedido=self.pedido)
        nota.status = NotaFiscal.Status.AUTORIZADA
        nota.origem = NotaFiscal.Origem.MANUAL
        nota.numero = form.cleaned_data["numero"]
        nota.chave_acesso = form.cleaned_data["chave_acesso"]
        nota.link_documento = form.cleaned_data.get("link_documento", "")
        nota.save()

        registrar_auditoria(
            acao="fiscal.nota_manual_registrada",
            instancia=nota,
            request=self.request,
            depois={
                "numero": nota.numero,
                "chave": nota.chave_acesso,
                "origem": nota.origem,
            },
        )
        messages.success(
            self.request,
            f"NF-e manual {nota.numero} vinculada ao pedido {self.pedido.numero}.",
        )
        return redirect(reverse("sales:pedido_interno_detail", args=[self.pedido.pk]))
