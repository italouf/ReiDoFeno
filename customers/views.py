from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404
from django.urls import reverse, reverse_lazy
from django.views.generic import (
    CreateView,
    DetailView,
    ListView,
    UpdateView,
)

from core.auditoria import AuditoriaFormValidMixin
from core.mixins import GRUPOS_INTERNOS, GrupoRequiredMixin

from .forms import ClienteForm, InteracaoForm
from .models import Cliente

GRUPOS_CADASTROS = ("Administrador", "Gestor")
GRUPOS_CONSULTA = ("Administrador", "Gestor", "Vendedor")


class ClienteBaseView(LoginRequiredMixin, GrupoRequiredMixin):
    pass


class ClienteListView(ClienteBaseView, ListView):
    model = Cliente
    template_name = "customers/cliente_list.html"
    context_object_name = "clientes"
    paginate_by = 25
    grupos_permitidos = GRUPOS_CONSULTA

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["pode_gerenciar"] = (
            self.request.user.is_superuser
            or self.request.user.groups.filter(name__in=GRUPOS_CADASTROS).exists()
        )
        return contexto


class ClienteDetailView(ClienteBaseView, DetailView):
    model = Cliente
    template_name = "customers/cliente_detail.html"
    context_object_name = "cliente"
    grupos_permitidos = GRUPOS_CONSULTA

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["pode_gerenciar"] = (
            self.request.user.is_superuser
            or self.request.user.groups.filter(name__in=GRUPOS_CADASTROS).exists()
        )
        contexto["interacoes"] = self.object.interacoes.select_related("vendedor")[:20]
        return contexto


class RegistrarInteracaoView(ClienteBaseView, CreateView):
    """Vendedor/admin registra atendimento ao cliente."""

    form_class = InteracaoForm
    template_name = "customers/interacao_form.html"
    grupos_permitidos = GRUPOS_INTERNOS

    def dispatch(self, request, *args, **kwargs):
        self.cliente = get_object_or_404(
            Cliente, pk=self.kwargs["cliente_pk"]
        )
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.cliente = self.cliente
        form.instance.vendedor = self.request.user
        messages.success(self.request, "Interação registrada.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("customers:cliente_detalhe", args=[self.cliente.pk])

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["cliente"] = self.cliente
        return contexto


class ClienteCreateView(
    ClienteBaseView, AuditoriaFormValidMixin, CreateView
):
    acao_prefixo = "cliente"
    model = Cliente
    form_class = ClienteForm
    template_name = "customers/cliente_form.html"
    success_url = reverse_lazy("customers:cliente_lista")
    grupos_permitidos = GRUPOS_CADASTROS

    def form_valid(self, form):
        messages.success(self.request, "Cliente cadastrado com sucesso.")
        return super().form_valid(form)


class ClienteUpdateView(ClienteBaseView, AuditoriaFormValidMixin, UpdateView):
    acao_prefixo = "cliente"
    model = Cliente
    form_class = ClienteForm
    template_name = "customers/cliente_form.html"
    success_url = reverse_lazy("customers:cliente_lista")
    grupos_permitidos = GRUPOS_CADASTROS

    def tem_acesso(self, usuario) -> bool:
        # LGPD art. 18: o próprio titular pode corrigir seus dados.
        if super().tem_acesso(usuario):
            return True
        cliente_vinculado = getattr(usuario, "cliente", None)
        alvo = self.kwargs.get("pk")
        return (
            usuario.is_authenticated
            and cliente_vinculado is not None
            and str(cliente_vinculado.pk) == str(alvo)
        )

    def form_valid(self, form):
        messages.success(self.request, "Cliente atualizado com sucesso.")
        return super().form_valid(form)
