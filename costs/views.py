from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, UpdateView

from core.auditoria import AuditoriaFormValidMixin
from core.mixins import GrupoRequiredMixin

from .forms import DespesaForm
from .models import Despesa

GRUPOS_CUSTOS = ("Administrador", "Gestor")


class CustosBaseView(LoginRequiredMixin, GrupoRequiredMixin):
    grupos_permitidos = GRUPOS_CUSTOS


class DespesaListView(CustosBaseView, ListView):
    model = Despesa
    template_name = "costs/despesa_list.html"
    context_object_name = "despesas"
    paginate_by = 25


class DespesaCreateView(CustosBaseView, AuditoriaFormValidMixin, CreateView):
    acao_prefixo = "despesa"
    model = Despesa
    form_class = DespesaForm
    template_name = "costs/despesa_form.html"
    success_url = reverse_lazy("costs:despesa_lista")

    def form_valid(self, form):
        messages.success(self.request, "Despesa registrada com sucesso.")
        return super().form_valid(form)


class DespesaUpdateView(CustosBaseView, AuditoriaFormValidMixin, UpdateView):
    acao_prefixo = "despesa"
    model = Despesa
    form_class = DespesaForm
    template_name = "costs/despesa_form.html"
    success_url = reverse_lazy("costs:despesa_lista")

    def form_valid(self, form):
        messages.success(self.request, "Despesa atualizada com sucesso.")
        return super().form_valid(form)
