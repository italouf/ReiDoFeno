import json
import logging
import uuid

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.http import Http404, HttpResponseNotAllowed, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import DetailView, FormView, ListView, TemplateView, View

from catalog.models import Produto
from core.auditoria import registrar_auditoria
from core.mixins import GRUPOS_INTERNOS, GrupoRequiredMixin
from core.rate_limit import chave_sessao, limitar_com_429

from .cart import Carrinho
from .emails import email_pedido_criado
from .forms import CheckoutForm
from .models import Pagamento, Pedido
from .services import (
    ResultadoPagamentoInvalido,
    alterar_status_operacional,
    criar_pedido_do_carrinho,
    pedidos_visiveis_para,
)

logger = logging.getLogger(__name__)

# SEC-01: o endpoint operacional nunca pode gravar um estado financeiro.
# Somente o retorno validado do provedor (services.aplicar_resultado_pagamento)
# pode alterar o status financeiro do pedido. `cancelado` é permitido porque
# também é uma ação operacional legítima.
STATUS_FINANCEIROS = frozenset(
    {
        Pedido.Status.PAGO,
        Pedido.Status.PAGAMENTO_PENDENTE,
        Pedido.Status.FALHOU,
        Pedido.StatusFinanceiro.PENDENTE,
        Pedido.StatusFinanceiro.ESTORNADO,
    }
)
PERMIS_SO_TRANSICOES_OPERACIONAIS = frozenset(
    set(Pedido.Status.values) - Pedido.STATUS_FINANCEIROS_LEGADOS
)


class CarrinhoView(TemplateView):
    template_name = "sales/carrinho.html"

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        carrinho = Carrinho(self.request)
        contexto["itens"] = carrinho.itens()
        contexto["total"] = carrinho.total()
        return contexto


class AdicionarAoCarrinhoView(View):
    def post(self, request):
        produto = get_object_or_404(Produto, pk=request.POST["produto_id"], ativo=True)
        try:
            quantidade = int(request.POST.get("quantidade", "1"))
        except ValueError:
            quantidade = 0
        if quantidade <= 0:
            messages.error(request, "Informe uma quantidade válida.")
            return redirect("loja:produto", produto.pk)

        disponivel = Carrinho.disponivel_total(produto)
        carrinho = Carrinho(request)
        ja_no_carrinho = int(carrinho.data.get(str(produto.pk), 0))
        if quantidade + ja_no_carrinho > disponivel:
            messages.error(
                request,
                f"Quantidade indisponível. Saldo atual: {disponivel} "
                f"{produto.unidade_medida}.",
            )
            return redirect("loja:produto", produto.pk)

        carrinho.adicionar(produto.pk, quantidade)
        carrinho.salvar()
        messages.success(request, f"{produto.nome} adicionado ao carrinho.")
        return redirect(reverse_lazy("sales:carrinho"))


class AlterarItemCarrinhoView(View):
    def post(self, request, produto_id):
        produto = get_object_or_404(Produto, pk=produto_id, ativo=True)
        try:
            quantidade = int(request.POST.get("quantidade", "0"))
        except ValueError:
            quantidade = -1

        carrinho = Carrinho(request)
        if quantidade > 0:
            disponivel = Carrinho.disponivel_total(produto)
            if quantidade > disponivel:
                messages.error(
                    request,
                    f"Quantidade indisponível. Saldo atual: {disponivel}.",
                )
                carrinho.salvar()
                return redirect("sales:carrinho")

        carrinho.definir(produto_id, quantidade)
        carrinho.salvar()
        messages.success(request, "Carrinho atualizado.")
        return redirect("sales:carrinho")


class RemoverItemCarrinhoView(View):
    def post(self, request, produto_id):
        carrinho = Carrinho(request)
        carrinho.remover(produto_id)
        carrinho.salvar()
        messages.success(request, "Item removido do carrinho.")
        return redirect("sales:carrinho")


# --------------------------------------------------------------------------- #
# Checkout
# --------------------------------------------------------------------------- #


@method_decorator(
    limitar_com_429(
        key="ip",
        rate=settings.RATELIMIT_CHECKOUT_IP,
        retry_after=3600,
    ),
    name="dispatch",
)
@method_decorator(
    limitar_com_429(
        key=chave_sessao,
        rate=settings.RATELIMIT_CHECKOUT,
        retry_after=3600,
    ),
    name="dispatch",
)
class CheckoutView(FormView):
    template_name = "sales/checkout.html"
    form_class = CheckoutForm

    def get(self, request, *args, **kwargs):
        if not Carrinho(request).itens():
            messages.info(request, "Seu carrinho está vazio.")
            return redirect("loja:catalogo")
        return super().get(request, *args, **kwargs)

    def get_initial(self):
        inicial = super().get_initial()
        usuario = self.request.user
        if usuario.is_authenticated:
            cliente = getattr(usuario, "cliente", None)  # vinculado na Fase 4
            inicial.setdefault("nome", usuario.get_full_name() or "")
            inicial.setdefault("email", usuario.email or "")
            if cliente:
                inicial["documento"] = cliente.documento
                inicial.setdefault("telefone", cliente.telefone or "")
        return inicial

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        carrinho = Carrinho(self.request)
        contexto["itens"] = carrinho.itens()
        contexto["total"] = carrinho.total()
        return contexto

    def form_valid(self, form):
        try:
            pedido = criar_pedido_do_carrinho(self.request, form)
        except ValidationError as erro:
            form.add_error(None, erro.message)
            return self.form_invalid(form)

        email_pedido_criado(pedido)
        return redirect(reverse("sales:pedido_token", args=[pedido.token_acesso]))


class PedidoStatusPublicoView(DetailView):
    """Acompanhamento do pedido por token (sem expor IDs sequenciais)."""

    template_name = "sales/pedido_status.html"
    context_object_name = "pedido"

    def get_object(self, queryset=None):
        token = self.kwargs.get("token")
        try:
            pedido_uuid = uuid.UUID(str(token))
        except (ValueError, TypeError):
            raise Http404 from None
        return get_object_or_404(Pedido, token_acesso=pedido_uuid)


# --------------------------------------------------------------------------- #
# Pagamento (Mercado Pago Checkout Pro) e webhook
# --------------------------------------------------------------------------- #


def _pedido_por_token(token) -> Pedido:
    try:
        pedido_uuid = uuid.UUID(str(token))
    except (ValueError, TypeError):
        raise Http404 from None
    return get_object_or_404(Pedido, token_acesso=pedido_uuid)


@method_decorator(
    limitar_com_429(
        key="ip",
        rate=settings.RATELIMIT_PAGAMENTO,
        retry_after=60,
    ),
    name="dispatch",
)
class PagamentoIniciarView(View):
    """Cria/reutiliza preferência de pagamento via POST idempotente."""

    @staticmethod
    def _pode_iniciar(pedido: Pedido) -> bool:
        return pedido.status_financeiro == (
            Pedido.StatusFinanceiro.PENDENTE
        ) and pedido.status in (
            Pedido.Status.AGUARDANDO_PAGAMENTO,
            Pedido.Status.PAGAMENTO_PENDENTE,
        )

    def get(self, request, token):
        return HttpResponseNotAllowed(["POST"])

    def post(self, request, token):
        pedido = _pedido_por_token(token)
        if not self._pode_iniciar(pedido):
            messages.info(request, "Este pedido não está aguardando pagamento.")
            return redirect("sales:pedido_token", pedido.token_acesso)

        # Reuso idempotente antes de chamar o provedor.
        with transaction.atomic():
            pedido = Pedido.objects.select_for_update().get(pk=pedido.pk)
            if not self._pode_iniciar(pedido):
                messages.info(
                    request, "Este pedido não está aguardando pagamento."
                )
                return redirect("sales:pedido_token", pedido.token_acesso)
            pagamento = (
                Pagamento.objects.select_for_update()
                .filter(pedido=pedido)
                .first()
            )
            if (
                pagamento
                and pagamento.status == Pagamento.Status.PENDENTE
                and pagamento.init_point
            ):
                return redirect(pagamento.init_point)
            if pagamento and pagamento.status == Pagamento.Status.APROVADO:
                messages.info(request, "O pagamento deste pedido já foi aprovado.")
                return redirect("sales:pedido_token", pedido.token_acesso)

        from .payments import obter_client

        client = obter_client()
        preferencia_id, init_point = client.criar_preferencia(pedido)

        with transaction.atomic():
            pedido = Pedido.objects.select_for_update().get(pk=pedido.pk)
            if not self._pode_iniciar(pedido):
                messages.info(
                    request,
                    "O pedido foi atualizado durante a criação do pagamento.",
                )
                return redirect("sales:pedido_token", pedido.token_acesso)

            pagamento = (
                Pagamento.objects.select_for_update()
                .filter(pedido=pedido)
                .first()
            )
            if pagamento is None:
                pagamento = Pagamento.objects.create(
                    pedido=pedido,
                    preferencia_id=preferencia_id,
                    init_point=init_point,
                    valor=pedido.total,
                    status=Pagamento.Status.PENDENTE,
                )
            elif pagamento.status == Pagamento.Status.APROVADO:
                registrar_auditoria(
                    acao="pedido.pagamento_preferencia_ignorada",
                    instancia=pedido,
                    request=request,
                    depois={
                        "preferencia_id": preferencia_id,
                        "pagamento_id": pagamento.pk,
                        "motivo": "pagamento já aprovado",
                    },
                )
                messages.info(request, "O pagamento deste pedido já foi aprovado.")
                return redirect("sales:pedido_token", pedido.token_acesso)
            elif (
                pagamento.status == Pagamento.Status.PENDENTE
                and pagamento.init_point
            ):
                return redirect(pagamento.init_point)
            else:
                tentativa_anterior = pagamento.status
                pagamento.preferencia_id = preferencia_id
                pagamento.init_point = init_point
                pagamento.valor = pedido.total
                pagamento.status = Pagamento.Status.PENDENTE
                pagamento.save(
                    update_fields=[
                        "preferencia_id",
                        "init_point",
                        "valor",
                        "status",
                    ]
                )
                registrar_auditoria(
                    acao="pedido.pagamento_nova_tentativa",
                    instancia=pedido,
                    request=request,
                    antes={"pagamento_status": tentativa_anterior},
                    depois={
                        "pagamento_status": pagamento.status,
                        "preferencia_id": preferencia_id,
                    },
                )

            registrar_auditoria(
                acao="pedido.pagamento_preferencia_criada",
                instancia=pedido,
                request=request,
                depois={
                    "preferencia_id": preferencia_id,
                    "pagamento_id": pagamento.pk,
                    "valor": str(pedido.total),
                },
            )
        return redirect(init_point)


class SimuladorPagamentoView(TemplateView):
    """Somente modo fake (dev/testes): simula o retorno do Checkout Pro."""

    template_name = "sales/simulador_pagamento.html"

    def dispatch(self, request, *args, **kwargs):
        if not settings.MERCADO_PAGO_FAKE:
            raise Http404
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["pedido"] = _pedido_por_token(self.kwargs.get("token"))
        return contexto


class SimularResultadoView(View):
    def post(self, request, token):
        if not settings.MERCADO_PAGO_FAKE:
            raise Http404
        pedido = _pedido_por_token(token)
        aprovado = request.POST.get("resultado") == "aprovado"
        id_externo = (
            f"fake-pay-{pedido.numero}-{'ok' if aprovado else 'recusado'}"
        )

        from .payments import obter_client
        from .services import aplicar_resultado_pagamento

        dados = obter_client().consultar_pagamento(id_externo)
        aplicar_resultado_pagamento(
            dados, request=request, id_consultado=id_externo
        )
        return redirect("sales:pedido_token", pedido.token_acesso)


@method_decorator(
    limitar_com_429(
        key="ip",
        rate=settings.RATELIMIT_WEBHOOK,
        retry_after=60,
    ),
    name="dispatch",
)
@method_decorator(csrf_exempt, name="dispatch")
class MercadoPagoWebhookView(View):
    """Recebe notificações do provedor: assinatura validada + idempotência."""

    def post(self, request):
        from .models import PagamentoWebhookEvento
        from .payments import (
            extrair_data_id,
            obter_client,
            validar_assinatura_webhook,
        )
        from .services import aplicar_resultado_pagamento

        try:
            payload = json.loads(request.body.decode() or "{}")
        except json.JSONDecodeError:
            payload = {}

        data_id_query = extrair_data_id(
            request.META.get("QUERY_STRING", ""), {}
        )
        data_id_body = extrair_data_id("", payload)
        if (
            data_id_query
            and data_id_body
            and data_id_query != data_id_body
        ):
            logger.warning(
                "Webhook com IDs divergentes na query e no body rejeitado."
            )
            return JsonResponse(
                {"erro": "identificadores divergentes"}, status=400
            )
        data_id = data_id_body or data_id_query
        if not data_id:
            logger.warning("Webhook sem identificador de recurso rejeitado.")
            return JsonResponse({"erro": "identificador ausente"}, status=400)

        if not validar_assinatura_webhook(request.headers, data_id):
            logger.warning("Webhook com assinatura inválida rejeitado.")
            return JsonResponse({"erro": "assinatura invalida"}, status=403)

        evento = PagamentoWebhookEvento.objects.create(
            referencia_externa=data_id,
            payload=payload,
        )
        try:
            dados = obter_client().consultar_pagamento(data_id)
            pedido = aplicar_resultado_pagamento(
                dados,
                request=request,
                id_consultado=data_id,
            )
            evento.processado = True
            evento.resultado = f"pedido={getattr(pedido, 'numero', 'n/a')}"
            evento.save()
        except ResultadoPagamentoInvalido as erro:
            evento.erro = str(erro)[:500]
            evento.resultado = "reconciliacao"
            evento.save(update_fields=["erro", "resultado"])
            logger.error(
                "Webhook %s rejeitado por contrato divergente: %s",
                data_id,
                erro,
            )
            return JsonResponse({"recebido": True, "reconciliacao": True})
        except Exception as erro:
            evento.erro = str(erro)[:500]
            evento.save()
            logger.exception("Falha ao processar webhook %s.", data_id)
            return JsonResponse({"erro": "processamento falhou"}, status=500)

        return JsonResponse({"recebido": True})


# --------------------------------------------------------------------------- #
# Listagens e acompanhamento operacional
# --------------------------------------------------------------------------- #


class MeusPedidosView(LoginRequiredMixin, TemplateView):
    """Cliente autenticado vê SOMENTE os próprios pedidos."""

    template_name = "sales/meus_pedidos.html"

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["pedidos"] = (
            Pedido.objects.filter(
                cliente__usuario=self.request.user,
                cliente__vinculo_verificado=True,
                identidade_verificada=True,
            )
            .prefetch_related("itens")
        )
        return contexto


class MinhasMetricasView(LoginRequiredMixin, GrupoRequiredMixin, TemplateView):
    """Métricas individuais do vendedor (isoladas por usuário)."""

    template_name = "sales/minhas_metricas.html"
    grupos_permitidos = GRUPOS_INTERNOS

    def get_context_data(self, **kwargs):
        from datetime import date

        from django.db.models import Sum
        from django.utils import timezone

        contexto = super().get_context_data(**kwargs)
        meus = Pedido.objects.filter(usuario_criador=self.request.user)
        hoje = timezone.localdate()

        contexto["pedidos_hoje"] = meus.filter(criado_em__date=hoje).count()
        vendas = meus.filter(
            status_financeiro=Pedido.StatusFinanceiro.PAGO
        ).exclude(status=Pedido.Status.CANCELADO)
        contexto["vendas_total"] = (
            vendas.aggregate(soma=Sum("total"))["soma"] or 0
        )
        contexto["clientes_atendidos"] = (
            vendas.values("cliente").distinct().count()
        )
        contexto["pendentes"] = meus.filter(
            status_financeiro=Pedido.StatusFinanceiro.PENDENTE,
            status__in=(
                Pedido.Status.AGUARDANDO_PAGAMENTO,
                Pedido.Status.PAGAMENTO_PENDENTE,
            ),
        ).count()
        contexto["interacoes_hoje"] = self.request.user.interacoes.filter(
            criado_em__date=date.today()
        ).count()
        return contexto


class PedidosInternosListView(LoginRequiredMixin, GrupoRequiredMixin, ListView):
    template_name = "sales/pedido_list_interna.html"
    context_object_name = "pedidos"
    paginate_by = 25
    grupos_permitidos = GRUPOS_INTERNOS

    def get_queryset(self):
        return pedidos_visiveis_para(self.request.user).select_related(
            "cliente", "unidade"
        ).prefetch_related("itens")


class PedidoInternoDetailView(LoginRequiredMixin, GrupoRequiredMixin, DetailView):
    template_name = "sales/pedido_interno_detail.html"
    context_object_name = "pedido"
    grupos_permitidos = GRUPOS_INTERNOS

    def get_queryset(self):
        return pedidos_visiveis_para(self.request.user).select_related(
            "cliente", "unidade"
        )

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        permitidos = (
            Pedido.TRANSICOES_VALIDAS.get(self.object.status, set())
            & PERMIS_SO_TRANSICOES_OPERACIONAIS
        )
        if self.object.status_financeiro != Pedido.StatusFinanceiro.PAGO:
            permitidos -= Pedido.EXIGE_FINANCEIRO_PAGO
        contexto["proximos_status"] = [
            (valor, Pedido.Status(valor).label)
            for valor in sorted(permitidos)
        ]
        return contexto


class PedidoAtualizarStatusView(LoginRequiredMixin, GrupoRequiredMixin, View):
    grupos_permitidos = GRUPOS_INTERNOS

    def post(self, request, pk):
        novo_status = request.POST.get("status", "")
        if novo_status in STATUS_FINANCEIROS:
            pedido = get_object_or_404(
                pedidos_visiveis_para(request.user), pk=pk
            )
            registrar_auditoria(
                acao="tentativa_bloqueada_transicao_financeira",
                instancia=pedido,
                request=request,
                antes={"status": pedido.status},
                depois={
                    "status_solicitado": novo_status,
                    "status_atual": pedido.status,
                },
            )
            raise PermissionDenied(
                "Transições financeiras só podem ser alteradas pelo provedor "
                "de pagamento."
            )
        try:
            pedido = alterar_status_operacional(
                pk,
                novo_status,
                usuario=request.user,
                request=request,
            )
        except ValidationError as erro:
            messages.error(request, erro.message)
        else:
            messages.success(
                request,
                f"Pedido {pedido.numero} → {pedido.get_status_display()}.",
            )
        return redirect("sales:pedido_interno_detail", pk)
