from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.urls import reverse_lazy
from django.views.generic import FormView, ListView

from catalog.models import Produto
from core.mixins import GrupoRequiredMixin
from core.models import Unidade

from .forms import AjusteForm, MovimentoForm, TransferenciaForm
from .models import Estoque, MovimentoEstoque
from .services import registrar_movimento, transferir_estoque

GRUPOS_ESTOQUE = ("Administrador", "Gestor")


class EstoqueBaseView(LoginRequiredMixin, GrupoRequiredMixin):
    grupos_permitidos = GRUPOS_ESTOQUE


class EstoqueListView(EstoqueBaseView, ListView):
    template_name = "stock/estoque_list.html"
    context_object_name = "estoques"

    def get_queryset(self):
        queryset = Estoque.objects.select_related("produto", "unidade")
        unidade_id = self.request.GET.get("unidade")
        if unidade_id:
            queryset = queryset.filter(unidade_id=unidade_id)
        return queryset.order_by("produto__nome")

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["unidades"] = Unidade.objects.all()
        contexto["unidade_selecionada"] = self.request.GET.get("unidade", "")
        return contexto


class MovimentoListView(EstoqueBaseView, ListView):
    template_name = "stock/movimento_list.html"
    context_object_name = "movimentos"
    paginate_by = 30

    def get_queryset(self):
        return MovimentoEstoque.objects.select_related(
            "produto", "unidade", "usuario"
        )


class MovimentoCreateBaseView(EstoqueBaseView, FormView):
    success_url = reverse_lazy("stock:movimento_lista")


class MovimentoEntradaSaidaView(MovimentoCreateBaseView):
    template_name = "stock/movimento_form.html"
    form_class = MovimentoForm
    titulo = "Nova movimentação"

    def get_initial(self):
        inicial = super().get_initial()
        tipo = self.kwargs.get("tipo", MovimentoEstoque.Tipo.ENTRADA)
        inicial["tipo"] = tipo
        self.titulo = (
            "Registrar entrada" if tipo == MovimentoEstoque.Tipo.ENTRADA
            else "Registrar saída"
        )
        return inicial

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["titulo"] = self.titulo
        return contexto

    def form_valid(self, form):
        try:
            movimento = registrar_movimento(
                produto=form.cleaned_data["produto"],
                unidade=form.cleaned_data["unidade"],
                tipo=form.cleaned_data["tipo"],
                quantidade=form.cleaned_data["quantidade"],
                usuario=self.request.user,
            )
        except ValidationError as erro:
            form.add_error(None, erro.message)
            return self.form_invalid(form)
        messages.success(
            self.request, f"Movimentação registrada: {movimento}."
        )
        return super().form_valid(form)


class MovimentoAjusteView(MovimentoCreateBaseView):
    template_name = "stock/movimento_form.html"
    form_class = AjusteForm
    titulo = "Ajuste de estoque"

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["titulo"] = self.titulo
        return contexto

    def form_valid(self, form):
        try:
            movimento = registrar_movimento(
                produto=form.cleaned_data["produto"],
                unidade=form.cleaned_data["unidade"],
                tipo=MovimentoEstoque.Tipo.AJUSTE,
                quantidade=form.cleaned_data["quantidade"],
                motivo=form.cleaned_data["motivo"],
                usuario=self.request.user,
            )
        except ValidationError as erro:
            form.add_error(None, erro.message)
            return self.form_invalid(form)
        messages.success(
            self.request, f"Ajuste registrado: {movimento}."
        )
        return super().form_valid(form)


class MovimentoTransferenciaView(MovimentoCreateBaseView):
    template_name = "stock/movimento_form.html"
    form_class = TransferenciaForm
    titulo = "Transferência entre unidades"

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["titulo"] = self.titulo
        return contexto

    def form_valid(self, form):
        try:
            transferir_estoque(
                produto=form.cleaned_data["produto"],
                unidade_origem=form.cleaned_data["unidade_origem"],
                unidade_destino=form.cleaned_data["unidade_destino"],
                quantidade=form.cleaned_data["quantidade"],
                usuario=self.request.user,
            )
        except ValidationError as erro:
            form.add_error(None, erro.message)
            return self.form_invalid(form)
        messages.success(self.request, "Transferência registrada com sucesso.")
        return super().form_valid(form)


def produtos_ativos(request):  # utilitário p/ futuras APIs internas (HTMX)
    return Produto.objects.filter(ativo=True)
