from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.shortcuts import redirect
from django.utils import timezone
from django.views.generic import FormView, TemplateView, View

from .forms import NovaSolicitacaoForm
from .models import ConsentimentoLGPD, SolicitacaoTitular
from .services import (
    abrir_solicitacao,
    exportar_dados_do_titular,
    payload_json_exportacao,
    registrar_consentimento,
    tem_consentimento_ativo,
)


class PoliticaPrivacidadeView(TemplateView):
    template_name = "privacy/politica.html"


class TermosUsoView(TemplateView):
    template_name = "privacy/termos.html"


def _cliente_do_usuario(usuario):
    return getattr(usuario, "cliente", None)


class MinhaPrivacidadeView(LoginRequiredMixin, TemplateView):
    """Painel do titular: consentimentos e solicitações LGPD."""

    template_name = "privacy/minha_privacidade.html"

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        cliente = _cliente_do_usuario(self.request.user)
        contexto["cliente"] = cliente
        if cliente:
            contexto["consentimentos"] = {
                finalidade: tem_consentimento_ativo(cliente, finalidade)
                for finalidade in ConsentimentoLGPD.Finalidade.values
            }
            contexto["solicitacoes"] = cliente.solicitacoes_lgpd.all()
        return contexto


class RevogarConsentimentoView(LoginRequiredMixin, View):
    def post(self, request, finalidade):
        cliente = _cliente_do_usuario(request.user)
        if cliente is None:
            messages.error(request, "Nenhum cadastro vinculado ao usuário.")
            return redirect("sales:meus_pedidos")

        registrar_consentimento(
            cliente=cliente,
            finalidade=finalidade,
            aceito=False,
            ip=request.META.get("REMOTE_ADDR"),
        )
        messages.success(
            request, "Consentimento revogado. Novos usos para esta finalidade cessam."
        )
        return redirect("privacy:minha_privacidade")


class NovaSolicitacaoView(LoginRequiredMixin, FormView):
    form_class = NovaSolicitacaoForm
    template_name = "privacy/nova_solicitacao.html"

    def form_valid(self, form):
        cliente = _cliente_do_usuario(self.request.user)
        if cliente is None:
            messages.error(self.request, "Nenhum cadastro vinculado ao usuário.")
            return redirect("sales:meus_pedidos")

        tipo = form.cleaned_data["tipo"]
        if tipo == SolicitacaoTitular.Tipo.EXPORTACAO:
            dados = exportar_dados_do_titular(cliente)
            solicitacao = abrir_solicitacao(cliente=cliente, tipo=tipo)
            solicitacao.status = solicitacao.Status.CONCLUIDA
            solicitacao.responsavel = self.request.user
            solicitacao.concluida_em = timezone.now()
            solicitacao.save()
            resposta = HttpResponse(
                payload_json_exportacao(dados), content_type="application/json"
            )
            resposta["Content-Disposition"] = (
                f"attachment; filename=meus-dados-{cliente.pk}.json"
            )
            return resposta

        abrir_solicitacao(cliente=cliente, tipo=tipo)
        messages.success(
            self.request,
            "Solicitação registrada. Prazo legal de resposta: até 15 dias.",
        )
        return redirect("privacy:minha_privacidade")
