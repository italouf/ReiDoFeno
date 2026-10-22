import csv

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.generic import FormView, ListView, TemplateView

from core.auditoria import registrar_auditoria
from core.mixins import GrupoRequiredMixin
from sales.models import Pedido

from .forms import NotaEntradaManualForm, NotaManualForm
from .models import NotaFiscal
from .services import relatorio_fiscal

GRUPOS_FISCAIS = ("Administrador", "Gestor", "Emissor Fiscal")


def _csv_seguro(valor) -> str:
    """Evita que texto vindo do banco seja interpretado como fórmula."""
    texto = str(valor or "")
    if texto.startswith(("=", "+", "-", "@")):
        return "'" + texto
    return texto


class RegistrarNotaManualView(
    LoginRequiredMixin, GrupoRequiredMixin, FormView
):
    """Fallback: registra NF-e emitida fora do sistema (auditável)."""

    form_class = NotaManualForm
    template_name = "fiscal/nota_manual_form.html"
    grupos_permitidos = GRUPOS_FISCAIS

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not self.tem_acesso(request.user):
            raise PermissionDenied
        self.pedido = get_object_or_404(Pedido, pk=self.kwargs["pedido_pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["pedido"] = self.pedido
        return contexto

    def form_valid(self, form):
        from .services import pedido_elegivel

        nota_existente = NotaFiscal.objects.filter(
            pedido=self.pedido, tipo=NotaFiscal.Tipo.SAIDA
        ).first()
        if nota_existente is None and not pedido_elegivel(self.pedido):
            form.add_error(
                None,
                "O pedido precisa estar pago, conciliado e com documento válido.",
            )
            return self.form_invalid(form)

        numero = form.cleaned_data["numero"]
        chave = form.cleaned_data["chave_acesso"]
        cfop_informado = (form.cleaned_data.get("cfop") or "").strip()
        motivo = (form.cleaned_data.get("motivo_retificacao") or "").strip()
        evidencia = (
            form.cleaned_data.get("evidencia_retificacao") or ""
        ).strip()
        link = form.cleaned_data.get("link_documento", "")
        with transaction.atomic():
            nota = (
                NotaFiscal.objects.select_for_update()
                .filter(pedido=self.pedido, tipo=NotaFiscal.Tipo.SAIDA)
                .first()
            )
            if (
                nota is not None
                and nota.status == NotaFiscal.Status.AUTORIZADA
                and (
                    nota.numero != numero
                    or nota.chave_acesso != chave
                    or nota.link_documento != link
                )
            ):
                form.add_error(
                    None,
                    "NF-e autorizada não pode ser substituída por outro "
                    "documento. Cancele-a antes de registrar outra.",
                )
                return self.form_invalid(form)
            antes = None
            if nota is None:
                if not pedido_elegivel(self.pedido):
                    form.add_error(
                        None,
                        "O pedido precisa estar pago, conciliado e com "
                        "documento válido para a primeira emissão manual.",
                    )
                    return self.form_invalid(form)
                nota = NotaFiscal(
                    pedido=self.pedido, tipo=NotaFiscal.Tipo.SAIDA
                )
                cfop = cfop_informado or (
                    "6.102" if self.pedido.interestadual else "5.102"
                )
            else:
                antes = {
                    "numero": nota.numero,
                    "chave": nota.chave_acesso,
                    "cfop": nota.cfop,
                    "status": nota.status,
                }
                cfop = nota.cfop
                if cfop_informado and cfop_informado != nota.cfop:
                    if not motivo or not evidencia:
                        form.add_error(
                            None,
                            "Alteração de CFOP de nota autorizada exige "
                            "motivo e evidência documental.",
                        )
                        return self.form_invalid(form)
                    cfop = cfop_informado
                elif nota.cfop and not cfop_informado:
                    cfop = nota.cfop
            nota.status = NotaFiscal.Status.AUTORIZADA
            nota.origem = NotaFiscal.Origem.MANUAL
            nota.numero = numero
            nota.chave_acesso = chave
            nota.cfop = cfop
            nota.link_documento = link
            nota.full_clean()
            nota.save()

            acao = (
                "fiscal.nota_cfop_retificado"
                if antes and antes.get("cfop") != nota.cfop
                else "fiscal.nota_manual_registrada"
            )
            registrar_auditoria(
                acao=acao,
                instancia=nota,
                request=self.request,
                antes=antes,
                depois={
                    "numero": nota.numero,
                    "chave": nota.chave_acesso,
                    "cfop": nota.cfop,
                    "origem": nota.origem,
                    "motivo_retificacao": motivo or None,
                    "evidencia_retificacao": evidencia or None,
                },
            )
        messages.success(
            self.request,
            f"NF-e manual {nota.numero} vinculada ao pedido {self.pedido.numero}.",
        )
        return redirect(reverse("fiscal:relatorio_fiscal"))


class NotaEntradaListView(
    LoginRequiredMixin, GrupoRequiredMixin, ListView
):
    """Fila de NF-e de entrada/devolução para o Emissor Fiscal."""

    template_name = "fiscal/nota_entrada_list.html"
    context_object_name = "notas"
    grupos_permitidos = GRUPOS_FISCAIS

    def get_queryset(self):
        return (
            NotaFiscal.objects.filter(tipo=NotaFiscal.Tipo.ENTRADA)
            .select_related("pedido", "pedido__cliente")
            .order_by("status", "-criado_em")
        )


class RegistrarNotaEntradaView(
    LoginRequiredMixin, GrupoRequiredMixin, FormView
):
    """Completa o registro manual do documento de entrada emitido fora."""

    form_class = NotaEntradaManualForm
    template_name = "fiscal/nota_entrada_form.html"
    grupos_permitidos = GRUPOS_FISCAIS

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not self.tem_acesso(request.user):
            raise PermissionDenied
        self.nota = get_object_or_404(
            NotaFiscal, pk=self.kwargs["pk"], tipo=NotaFiscal.Tipo.ENTRADA
        )
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        inicial = super().get_initial()
        inicial.update(
            {
                "numero": self.nota.numero,
                "link_documento": self.nota.link_documento,
            }
        )
        return inicial

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["nota"] = self.nota
        return contexto

    def form_valid(self, form):
        with transaction.atomic():
            nota = NotaFiscal.objects.select_for_update().get(
                pk=self.nota.pk, tipo=NotaFiscal.Tipo.ENTRADA
            )
            saida = (
                NotaFiscal.objects.filter(
                    pedido_id=nota.pedido_id,
                    tipo=NotaFiscal.Tipo.SAIDA,
                    status=NotaFiscal.Status.AUTORIZADA,
                )
                .order_by("-pk")
                .first()
            )
            if (
                saida is None
                or not saida.chave_acesso
                or nota.chave_referenciada != saida.chave_acesso
            ):
                form.add_error(
                    None,
                    "A chave referenciada não corresponde à NF-e de saída "
                    "autorizada do pedido.",
                )
                return self.form_invalid(form)
            numero = form.cleaned_data["numero"]
            chave = form.cleaned_data["chave_acesso"]
            link = form.cleaned_data.get("link_documento", "")
            if (
                nota.status == NotaFiscal.Status.AUTORIZADA
                and (
                    nota.numero not in ("", numero)
                    or nota.chave_acesso not in ("", chave)
                    or nota.link_documento not in ("", link)
                )
            ):
                form.add_error(
                    None,
                    "Documento de entrada já confirmado não pode ser "
                    "substituído por outra chave/número.",
                )
                return self.form_invalid(form)
            antes = {
                "numero": nota.numero,
                "chave": nota.chave_acesso,
                "link": nota.link_documento,
                "status": nota.status,
            }
            nota.numero = numero
            nota.chave_acesso = chave
            nota.link_documento = link
            nota.origem = NotaFiscal.Origem.MANUAL
            nota.status = NotaFiscal.Status.AUTORIZADA
            nota.full_clean()
            nota.save()
            registrar_auditoria(
                acao="fiscal.nota_entrada_registrada",
                instancia=nota,
                request=self.request,
                antes=antes,
                depois={
                    "numero": nota.numero,
                    "chave": nota.chave_acesso,
                    "link": nota.link_documento,
                    "status": nota.status,
                    "origem": nota.origem,
                    "chave_referenciada": nota.chave_referenciada,
                },
            )
        messages.success(
            self.request,
            f"Documento de entrada {nota.numero} registrado para "
            f"{nota.pedido.numero}.",
        )
        return redirect("fiscal:nota_entrada_lista")


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
                "Evento",
                "Data do evento",
            ]
        )
        for linha in relatorio["linhas"]:
            escritor.writerow(
                [
                    _csv_seguro(linha["pedido"]),
                    _csv_seguro(linha["unidade"]),
                    _csv_seguro(linha["uf_entrega"]),
                    "sim" if linha["interestadual"] else "nao",
                    f"{linha['aliquota_icms']:.4f}",
                    f"{linha['valor']:.2f}",
                    linha["evento"],
                    linha["evento_em"].isoformat()
                    if linha["evento_em"]
                    else "",
                ]
            )
        return resposta
