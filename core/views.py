from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import F
from django.http import Http404, JsonResponse
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import (
    CreateView,
    ListView,
    TemplateView,
    UpdateView,
)

from analytics.models import Aviso
from catalog.models import Produto
from core.mixins import GrupoRequiredMixin
from costs.models import Despesa
from stock.models import Estoque, MovimentoEstoque

from .auditoria import AuditoriaFormValidMixin
from .forms import UnidadeForm
from .models import Unidade

GRUPOS_CADASTROS = ("Administrador", "Gestor")


def healthz(request):
    """Endpoint de saúde para monitoramento (sem dados sensíveis)."""
    return JsonResponse({"status": "ok"})


def healthz_ip(request):
    """Diagnóstico de smoke: expõe somente REMOTE_ADDR, nunca em produção."""
    if not getattr(settings, "SMOKE_DIAGNOSTICS", False):
        raise Http404
    return JsonResponse({"remote_addr": request.META.get("REMOTE_ADDR", "")})


class PainelView(GrupoRequiredMixin, TemplateView):
    template_name = "core/painel.html"
    grupos_permitidos = ("Administrador", "Gestor")

    def get_context_data(self, **kwargs):

        from analytics.services import metricas_do_periodo

        contexto = super().get_context_data(**kwargs)
        contexto["titulo"] = "Painel"

        hoje = timezone.localdate()
        inicio = _parse_data(self.request.GET.get("inicio")) or hoje.replace(day=1)
        fim = _parse_data(self.request.GET.get("fim")) or hoje
        metricas = metricas_do_periodo(inicio, fim)
        contexto["metricas"] = metricas
        contexto["receita"] = metricas["receita"]
        contexto["num_pedidos"] = metricas["num_pedidos"]
        contexto["filtro_inicio"] = inicio.isoformat()
        contexto["filtro_fim"] = fim.isoformat()

        contexto["total_produtos"] = Produto.objects.filter(ativo=True).count()
        contexto["estoques_baixos"] = (
            Estoque.objects.select_related("produto", "unidade")
            .filter(quantidade__lte=F("quantidade_minima"))
            .order_by("quantidade")[:5]
        )
        contexto["ultimas_movimentacoes"] = MovimentoEstoque.objects.select_related(
            "produto", "unidade", "usuario"
        )[:5]
        contexto["despesas_recentes"] = Despesa.objects.all()[:5]
        contexto["avisos_nao_lidos"] = Aviso.objects.filter(lido=False)[:5]
        return contexto


def _parse_data(valor: str | None):
    from django.utils.dateparse import parse_date

    if not valor:
        return None
    return parse_date(valor)


class CadastroBaseView(LoginRequiredMixin, GrupoRequiredMixin):
    grupos_permitidos = GRUPOS_CADASTROS


class UnidadeListView(CadastroBaseView, ListView):
    model = Unidade
    template_name = "core/unidade_list.html"
    context_object_name = "unidades"


class UnidadeCreateView(
    CadastroBaseView, AuditoriaFormValidMixin, CreateView
):
    acao_prefixo = "unidade"
    model = Unidade
    form_class = UnidadeForm
    template_name = "core/unidade_form.html"
    success_url = reverse_lazy("core:unidade_lista")

    def form_valid(self, form):
        messages.success(self.request, "Unidade cadastrada com sucesso.")
        return super().form_valid(form)


class UnidadeUpdateView(
    CadastroBaseView, AuditoriaFormValidMixin, UpdateView
):
    acao_prefixo = "unidade"
    model = Unidade
    form_class = UnidadeForm
    template_name = "core/unidade_form.html"
    success_url = reverse_lazy("core:unidade_lista")

    def form_valid(self, form):
        messages.success(self.request, "Unidade atualizada com sucesso.")
        return super().form_valid(form)
