from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.urls import reverse_lazy
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from core.auditoria import AuditoriaFormValidMixin
from core.mixins import GrupoRequiredMixin

from .forms import CategoriaForm, ProdutoForm
from .models import Categoria, Produto

GRUPOS_CADASTROS = ("Administrador", "Gestor")
class CatalogBaseView(LoginRequiredMixin, GrupoRequiredMixin):
    grupos_permitidos = GRUPOS_CADASTROS


class ProdutoListView(CatalogBaseView, ListView):
    model = Produto
    template_name = "catalog/produto_list.html"
    context_object_name = "produtos"
    paginate_by = 25


class ProdutoCreateView(CatalogBaseView, AuditoriaFormValidMixin, CreateView):
    acao_prefixo = "produto"
    campos_auditados = (
        "nome", "categoria", "ncm", "unidade_medida",
        "custo", "preco_balcao", "preco_online", "ativo",
    )
    model = Produto
    form_class = ProdutoForm
    template_name = "catalog/produto_form.html"
    success_url = reverse_lazy("catalog:produto_lista")

    def form_valid(self, form):
        messages.success(self.request, "Produto cadastrado com sucesso.")
        return super().form_valid(form)


class ProdutoUpdateView(CatalogBaseView, AuditoriaFormValidMixin, UpdateView):
    acao_prefixo = "produto"
    campos_auditados = (
        "nome", "categoria", "ncm", "unidade_medida",
        "custo", "preco_balcao", "preco_online", "ativo",
    )
    model = Produto
    form_class = ProdutoForm
    template_name = "catalog/produto_form.html"
    success_url = reverse_lazy("catalog:produto_lista")

    def form_valid(self, form):
        messages.success(self.request, "Produto atualizado com sucesso.")
        return super().form_valid(form)


class CategoriaListView(CatalogBaseView, ListView):
    model = Categoria
    template_name = "catalog/categoria_list.html"
    context_object_name = "categorias"


class CategoriaCreateView(CatalogBaseView, AuditoriaFormValidMixin, CreateView):
    acao_prefixo = "categoria"
    model = Categoria
    form_class = CategoriaForm
    template_name = "catalog/categoria_form.html"
    success_url = reverse_lazy("catalog:categoria_lista")

    def form_valid(self, form):
        messages.success(self.request, "Categoria cadastrada com sucesso.")
        return super().form_valid(form)


class CategoriaUpdateView(CatalogBaseView, AuditoriaFormValidMixin, UpdateView):
    acao_prefixo = "categoria"
    model = Categoria
    form_class = CategoriaForm
    template_name = "catalog/categoria_form.html"
    success_url = reverse_lazy("catalog:categoria_lista")

    def form_valid(self, form):
        messages.success(self.request, "Categoria atualizada com sucesso.")
        return super().form_valid(form)


# ---------------------------------------------------------------------------
# Vitrine pública (sem autenticação)
# ---------------------------------------------------------------------------


class CatalogoLojaView(ListView):
    """Vitrine pública: somente produtos ativos.

    Aceita filtros opcionais por GET (busca, categoria, faixa de preço, ordem).
    Sem parâmetros, comporta-se exatamente como antes.
    """

    template_name = "catalog/catalogo.html"
    context_object_name = "produtos"
    queryset = Produto.objects.filter(ativo=True).select_related("categoria")
    paginate_by = 12

    ORDEM = {
        "relevancia": None,
        "preco": "preco_online",
        "preco_desc": "-preco_online",
        "nome": "nome",
    }

    def get_queryset(self):
        queryset = super().get_queryset()
        categoria_id = self.request.GET.get("categoria")
        if categoria_id:
            queryset = queryset.filter(categoria_id=categoria_id)

        busca = (self.request.GET.get("q") or "").strip()
        if busca:
            queryset = queryset.filter(
                Q(nome__icontains=busca) | Q(categoria__nome__icontains=busca)
            )

        for parametro, campo in (("preco_min", "gte"), ("preco_max", "lte")):
            bruto = (self.request.GET.get(parametro) or "").strip().replace(",", ".")
            if not bruto:
                continue
            try:
                valor = Decimal(bruto)
            except InvalidOperation:
                continue
            queryset = queryset.filter(**{f"preco_online__{campo}": valor})

        ordenar = self.request.GET.get("ordenar", "")
        campo_ordem = self.ORDEM.get(ordenar)
        if campo_ordem:
            queryset = queryset.order_by(campo_ordem)
        return queryset

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["categorias"] = Categoria.objects.filter(ativa=True)
        contexto["categoria_selecionada"] = self.request.GET.get("categoria", "")
        contexto["busca"] = (self.request.GET.get("q") or "").strip()
        contexto["ordenar"] = self.request.GET.get("ordenar", "")
        contexto["preco_min"] = (self.request.GET.get("preco_min") or "").strip()
        contexto["preco_max"] = (self.request.GET.get("preco_max") or "").strip()
        return contexto


class ProdutoLojaDetailView(DetailView):
    """Página pública do produto; inativos retornam 404."""

    template_name = "catalog/produto_loja.html"
    context_object_name = "produto"
    queryset = Produto.objects.filter(ativo=True)
