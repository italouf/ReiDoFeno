import csv

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.generic import FormView, TemplateView

from core.auditoria import registrar_auditoria
from core.mixins import GrupoRequiredMixin
from sales.models import Pedido

from .forms import NotaManualForm
from .models import NotaFiscal
from .services import relatorio_fiscal

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
        with transaction.atomic():
            nota, _criada = NotaFiscal.objects.get_or_create(
                pedido=self.pedido, tipo=NotaFiscal.Tipo.SAIDA
            )
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


class RelatorioFiscalView(
    LoginRequiredMixin, GrupoRequiredMixin, TemplateView
):
    """Relatório fiscal com destaque para operações interestaduais."""

    template_name = "fiscal/relatorio_fiscal.html"
    grupos_permitidos = GRUPOS_FISCAIS

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
        return inicio, fim

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        inicio, fim = self._filtros()
        contexto.update(
            {
                "titulo": "Relatório fiscal",
                "inicio": inicio,
                "fim": fim,
                "relatorio": relatorio_fiscal(inicio, fim),
            }
        )
        return contexto

    def _exportar_csv(self):
        inicio, fim = self._filtros()
        relatorio = relatorio_fiscal(inicio, fim)
        resposta = HttpResponse(content_type="text/csv")
        resposta["Content-Disposition"] = (
            'attachment; filename="relatorio-fiscal.csv"'
        )
        escritor = csv.writer(resposta)
        escritor.writerow(
            [
                "Pedido",
                "Unidade",
                "UF de entrega",
                "Interestadual",
                "Aliquota ICMS",
                "Valor",
                "Aprovado em",
            ]
        )
        for linha in relatorio["linhas"]:
            escritor.writerow(
                [
                    linha["pedido"],
                    linha["unidade"],
                    linha["uf_entrega"],
                    "sim" if linha["interestadual"] else "nao",
                    f"{linha['aliquota_icms']:.4f}",
                    f"{linha['valor']:.2f}",
                    linha["aprovado_em"].isoformat()
                    if linha["aprovado_em"]
                    else "",
                ]
            )
        return resposta
