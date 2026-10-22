import csv
import json

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.generic import ListView, TemplateView, View

from core.mixins import GRUPOS_INTERNOS, GrupoRequiredMixin
from core.models import Unidade

from .models import Aviso
from .services import comparativo_unidades, vendas_por_produto

GRUPOS_GESTAO = ("Administrador", "Gestor")


def _csv_seguro(valor) -> str:
    texto = str(valor or "")
    if texto.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + texto
    return texto


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


class RelatorioVendasProdutoView(
    LoginRequiredMixin, GrupoRequiredMixin, TemplateView
):
    """Vendas por produto/dia/unidade, com exportação CSV."""

    template_name = "analytics/relatorio_vendas_produto.html"
    grupos_permitidos = GRUPOS_GESTAO

    def get(self, request, *args, **kwargs):
        if request.GET.get("formato") == "csv" or request.GET.get("format") == "csv":
            return self._exportar_csv()
        return super().get(request, *args, **kwargs)

    def _filtros(self):
        hoje = timezone.localdate()
        inicio = parse_date(self.request.GET.get("inicio") or "") or hoje.replace(
            day=1
        )
        fim = parse_date(self.request.GET.get("fim") or "") or hoje
        unidade_id = self.request.GET.get("unidade") or ""
        unidade = None
        if unidade_id.isdigit():
            unidade = Unidade.objects.filter(pk=int(unidade_id)).first()
        return inicio, fim, unidade

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        inicio, fim, unidade = self._filtros()
        vendas = vendas_por_produto(inicio, fim, unidade=unidade)
        contexto.update(
            {
                "titulo": "Vendas por produto",
                "inicio": inicio,
                "fim": fim,
                "unidade": unidade,
                "unidades": Unidade.objects.filter(ativa=True),
                "vendas": vendas,
                "grafico_labels": json.dumps(
                    [
                        f"{v['produto']} · {v['unidade']} · {v['dia']:%d/%m}"
                        for v in vendas
                    ],
                    ensure_ascii=False,
                ),
                "grafico_valores": json.dumps(
                    [float(v["receita"]) for v in vendas]
                ),
                "total_receita": sum(
                    (v["receita"] for v in vendas), start=0
                ),
                "total_cmv": sum((v["cmv"] for v in vendas), start=0),
            }
        )
        return contexto

    def _exportar_csv(self):
        inicio, fim, unidade = self._filtros()
        vendas = vendas_por_produto(inicio, fim, unidade=unidade)
        # CSV com os mesmos filtros da tela.
        resposta = HttpResponse(content_type="text/csv")
        resposta["Content-Disposition"] = (
            'attachment; filename="vendas-por-produto.csv"'
        )
        escritor = csv.writer(resposta)
        escritor.writerow(
            [
                "Produto",
                "Unidade",
                "Dia",
                "Quantidade vendida",
                "Quantidade devolvida",
                "Receita",
                "CMV",
                "Lucro bruto",
            ]
        )
        for linha in vendas:
            escritor.writerow(
                [
                    _csv_seguro(linha["produto"]),
                    _csv_seguro(linha["unidade"]),
                    linha["dia"].isoformat(),
                    f"{linha['quantidade']:.2f}",
                    f"{linha['quantidade_devolvida']:.2f}",
                    f"{linha['receita']:.2f}",
                    f"{linha['cmv']:.2f}",
                    f"{linha['lucro_bruto']:.2f}",
                ]
            )
        return resposta


class ComparativoUnidadesView(
    LoginRequiredMixin, GrupoRequiredMixin, TemplateView
):
    """Comparação lado a lado entre as unidades ativas."""

    template_name = "analytics/comparativo_unidades.html"
    grupos_permitidos = GRUPOS_GESTAO

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        hoje = timezone.localdate()
        inicio = parse_date(self.request.GET.get("inicio") or "") or hoje.replace(
            day=1
        )
        fim = parse_date(self.request.GET.get("fim") or "") or hoje
        linhas = comparativo_unidades(inicio, fim)
        contexto.update(
            {
                "titulo": "Comparativo de unidades",
                "inicio": inicio,
                "fim": fim,
                "linhas": linhas,
                "grafico_labels": json.dumps(
                    [linha["unidade"] for linha in linhas],
                    ensure_ascii=False,
                ),
                "grafico_series": json.dumps(
                    [
                        {
                            "label": "Receita produtos",
                            "color": "#2f6b4f",
                            "values": [
                                float(linha["receita_produtos"])
                                for linha in linhas
                            ],
                        },
                        {
                            "label": "CMV",
                            "color": "#b07d3f",
                            "values": [
                                float(linha["cmv"]) for linha in linhas
                            ],
                        },
                        {
                            "label": "Lucro bruto",
                            "color": "#3d7d63",
                            "values": [
                                float(linha["lucro_bruto"]) for linha in linhas
                            ],
                        },
                    ]
                ),
            }
        )
        return contexto
