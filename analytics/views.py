from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.views.generic import ListView, View

from core.mixins import GRUPOS_INTERNOS, GrupoRequiredMixin

from .models import Aviso


class AvisoListView(LoginRequiredMixin, GrupoRequiredMixin, ListView):
    """Central de avisos internos (não lidos primeiro)."""

    template_name = "analytics/aviso_list.html"
    context_object_name = "avisos"
    paginate_by = 30
    grupos_permitidos = GRUPOS_INTERNOS

    def get_queryset(self):
        return Aviso.objects.all().order_by("lido", "-criado_em")


class MarcarAvisoLidoView(LoginRequiredMixin, GrupoRequiredMixin, View):
    grupos_permitidos = GRUPOS_INTERNOS

    def post(self, request, pk):
        aviso = get_object_or_404(Aviso, pk=pk)
        aviso.lido = True
        aviso.save(update_fields=["lido"])
        messages.success(request, "Aviso marcado como lido.")
        return redirect("analytics:aviso_lista")
