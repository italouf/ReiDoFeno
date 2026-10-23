import csv

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Case, IntegerField, Value, When
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
    if texto.lstrip().startswith(("=", "+", "-", "@")):
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
        from .services import LEASE_EMISSAO, pedido_elegivel

        numero = form.cleaned_data["numero"]
        chave = form.cleaned_data["chave_acesso"]
        cfop_informado = (form.cleaned_data.get("cfop") or "").strip()
        motivo = (form.cleaned_data.get("motivo_retificacao") or "").strip()
        evidencia = (
            form.cleaned_data.get("evidencia_retificacao") or ""
        ).strip()
        link = form.cleaned_data.get("link_documento", "")
        pedido_id = self.pedido.pk
        with transaction.atomic():
            # Pedido primeiro, nota depois: mesma ordem de cancelamento e
            # devolução. A ausência inicial de nota é serializada pelo lock
            # da linha do pedido, que existe desde o checkout.
            pedido = Pedido.objects.select_for_update().get(pk=pedido_id)
            nota = (
                NotaFiscal.objects.select_for_update()
                .filter(pedido=pedido, tipo=NotaFiscal.Tipo.SAIDA)
                .first()
            )
            if nota is None and not pedido_elegivel(pedido):
                form.add_error(
                    None,
                    "O pedido precisa estar pago, conciliado e com documento "
                    "válido.",
                )
                return self.form_invalid(form)
            if (
                nota is not None
                and nota.status == NotaFiscal.Status.CANCELADA
            ):
                form.add_error(
                    None,
                    "NF-e cancelada não pode ser reautorizada por esta rota. "
                    "Emita um novo documento fora do sistema e registre-o.",
                )
                return self.form_invalid(form)
            if (
                nota is not None
                and nota.processando_desde is not None
                and timezone.now() - nota.processando_desde < LEASE_EMISSAO
            ):
                form.add_error(
                    None,
                    "Há uma emissão automática em andamento para este pedido. "
                    "Aguarde a conclusão antes de registrar a NF-e manualmente.",
                )
                return self.form_invalid(form)
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
            tentativa_expirada = None
            processando_expirado = None
            if nota is None:
                if not pedido_elegivel(pedido):
                    form.add_error(
                        None,
                        "O pedido precisa estar pago, conciliado e com "
                        "documento válido para a primeira emissão manual.",
                    )
                    return self.form_invalid(form)
                nota = NotaFiscal(
                    pedido=pedido, tipo=NotaFiscal.Tipo.SAIDA
                )
                cfop = cfop_informado or (
                    "6.102" if pedido.interestadual else "5.102"
                )
            else:
                tentativa_expirada = nota.tentativa_atual
                processando_expirado = nota.processando_desde
                antes = {
                    "numero": nota.numero,
                    "chave": nota.chave_acesso,
                    "cfop": nota.cfop,
                    "status": nota.status,
                    "tentativa": (
                        str(nota.tentativa_atual)
                        if nota.tentativa_atual
                        else None
                    ),
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
            # Uma confirmação manual invalida qualquer claim expirado. A
            # tentativa antiga, se ainda estiver em voo, não poderá mais
            # sobrescrever este documento ao retornar.
            nota.tentativa_atual = None
            nota.processando_desde = None
            nota.status = NotaFiscal.Status.AUTORIZADA
            nota.origem = NotaFiscal.Origem.MANUAL
            nota.numero = numero
            nota.chave_acesso = chave
            nota.cfop = cfop
            nota.link_documento = link
            try:
                nota.full_clean()
                with transaction.atomic():
                    nota.save()
            except ValidationError as erro:
                form.add_error(None, erro.messages)
                return self.form_invalid(form)
            except IntegrityError:
                form.add_error(
                    "chave_acesso",
                    "Já existe uma nota registrada com esta chave.",
                )
                return self.form_invalid(form)

            if tentativa_expirada:
                registrar_auditoria(
                    acao="fiscal.tentativa_manual_assumida",
                    instancia=nota,
                    request=self.request,
                    antes={
                        "tentativa": str(tentativa_expirada),
                        "processando_desde": (
                            processando_expirado.isoformat()
                            if processando_expirado
                            else None
                        ),
                    },
                    depois={
                        "tentativa": None,
                        "origem": nota.origem,
                        "numero": nota.numero,
                        "motivo": "lease expirado assumido pelo registro manual",
                    },
                )

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
            f"NF-e manual {nota.numero} vinculada ao pedido {pedido.numero}.",
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
            .annotate(
                fila=Case(
                    When(
                        status=NotaFiscal.Status.PENDENTE,
                        then=Value(0),
                    ),
                    default=Value(1),
                    output_field=IntegerField(),
                )
            )
            .order_by("fila", "-criado_em")
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
        pedido_id = self.nota.pedido_id
        with transaction.atomic():
            Pedido.objects.select_for_update().get(pk=pedido_id)
            nota = NotaFiscal.objects.select_for_update().get(
                pk=self.nota.pk, tipo=NotaFiscal.Tipo.ENTRADA
            )
            if nota.status == NotaFiscal.Status.CANCELADA:
                form.add_error(
                    None,
                    "Documento de entrada cancelado não pode ser reautorizado.",
                )
                return self.form_invalid(form)
            saida = (
                NotaFiscal.objects.select_for_update()
                .filter(
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
            if chave == nota.chave_referenciada:
                form.add_error(
                    "chave_acesso",
                    "A chave da entrada não pode ser igual à chave "
                    "referenciada da saída.",
                )
                return self.form_invalid(form)
            if (
                NotaFiscal.objects.filter(chave_acesso=chave)
                .exclude(pk=nota.pk)
                .exists()
            ):
                form.add_error(
                    "chave_acesso",
                    "Já existe uma nota registrada com esta chave.",
                )
                return self.form_invalid(form)
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
            try:
                nota.full_clean()
                with transaction.atomic():
                    nota.save()
            except ValidationError as erro:
                form.add_error(None, erro.messages)
                return self.form_invalid(form)
            except IntegrityError:
                form.add_error(
                    "chave_acesso",
                    "Já existe uma nota registrada com esta chave.",
                )
                return self.form_invalid(form)
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
