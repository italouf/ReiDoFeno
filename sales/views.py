import json
import logging
import uuid

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import DetailView, FormView, ListView, TemplateView, View

from catalog.models import Produto
from core.mixins import GRUPOS_INTERNOS, GrupoRequiredMixin

from .cart import Carrinho
from .emails import email_pedido_criado
from .forms import CheckoutForm
from .models import Pagamento, Pedido
from .services import cancelar_pedido, criar_pedido_do_carrinho

logger = logging.getLogger(__name__)


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


class PagamentoIniciarView(View):
    """Cria a preferência no provedor e redireciona ao Checkout Pro."""

    def get(self, request, token):
        pedido = _pedido_por_token(token)
        if pedido.status not in (
            Pedido.Status.AGUARDANDO_PAGAMENTO,
            Pedido.Status.PAGAMENTO_PENDENTE,
            Pedido.Status.FALHOU,
        ):
            messages.info(request, "Este pedido não está aguardando pagamento.")
            return redirect("sales:pedido_token", pedido.token_acesso)

        from .payments import obter_client

        client = obter_client()
        preferencia_id, init_point = client.criar_preferencia(pedido)

        pagamento, _criado = Pagamento.objects.update_or_create(
            pedido=pedido,
            defaults={
                "preferencia_id": preferencia_id,
                "valor": pedido.total,
                "status": Pagamento.Status.PENDENTE,
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
        aplicar_resultado_pagamento(dados)
        return redirect("sales:pedido_token", pedido.token_acesso)


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

        data_id = extrair_data_id(request.META.get("QUERY_STRING", ""), payload)
        if not validar_assinatura_webhook(request.headers, data_id):
            logger.warning("Webhook com assinatura inválida rejeitado.")
            return JsonResponse({"erro": "assinatura invalida"}, status=403)

        evento = PagamentoWebhookEvento.objects.create(
            referencia_externa=data_id,
            payload=payload,
        )
        try:
            dados = obter_client().consultar_pagamento(data_id)
            pedido = aplicar_resultado_pagamento(dados)
            evento.processado = True
            evento.resultado = f"pedido={getattr(pedido, 'numero', 'n/a')}"
            evento.save()
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
            Pedido.objects.filter(cliente__usuario=self.request.user)
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
        vendas = meus.filter(status__in=(Pedido.Status.PAGO, Pedido.Status.CONCLUIDO))
        contexto["vendas_total"] = (
            vendas.aggregate(soma=Sum("total"))["soma"] or 0
        )
        contexto["clientes_atendidos"] = (
            vendas.values("cliente").distinct().count()
        )
        contexto["pendentes"] = meus.filter(
            status__in=(
                Pedido.Status.AGUARDANDO_PAGAMENTO,
                Pedido.Status.PAGAMENTO_PENDENTE,
            )
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
        usuario = self.request.user
        queryset = Pedido.objects.select_related(
            "cliente", "unidade"
        ).prefetch_related("itens")
        if usuario.is_superuser:
            return queryset
        if usuario.groups.filter(name="Vendedor").exists() and not (
            usuario.groups.filter(name__in=("Administrador", "Gestor")).exists()
        ):
            return queryset.filter(usuario_criador=usuario)
        return queryset


class PedidoInternoDetailView(LoginRequiredMixin, GrupoRequiredMixin, DetailView):
    template_name = "sales/pedido_interno_detail.html"
    context_object_name = "pedido"
    grupos_permitidos = GRUPOS_INTERNOS

    def get_queryset(self):
        usuario = self.request.user
        queryset = Pedido.objects.select_related("cliente", "unidade")
        if usuario.is_superuser:
            return queryset
        if usuario.groups.filter(name__in=("Administrador", "Gestor")).exists():
            return queryset
        return queryset.filter(usuario_criador=usuario)

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        permitidos = sorted(Pedido.TRANSICOES_VALIDAS.get(self.object.status, set()))
        contexto["proximos_status"] = [
            (valor, Pedido.Status(valor).label) for valor in permitidos
        ]
        return contexto


class PedidoAtualizarStatusView(LoginRequiredMixin, GrupoRequiredMixin, View):
    grupos_permitidos = GRUPOS_INTERNOS

    def post(self, request, pk):
        pedido = get_object_or_404(
            Pedido.objects.filter(self._recorte(request.user)),
            pk=pk,
        )
        novo_status = request.POST.get("status", "")
        if novo_status == Pedido.Status.CANCELADO:
            # cancelar_pedido faz a transição E libera reservas.
            cancelar_pedido(pedido)
            messages.success(
                request, f"Pedido {pedido.numero} → Cancelado."
            )
            return redirect("sales:pedido_interno_detail", pk)
        try:
            pedido.transicionar(novo_status)
        except ValidationError as erro:
            messages.error(request, erro.message)
        else:
            messages.success(
                request, f"Pedido {pedido.numero} → {pedido.get_status_display()}."
            )
        return redirect("sales:pedido_interno_detail", pk)

    @staticmethod
    def _recorte(usuario):
        if usuario.is_superuser or usuario.groups.filter(
            name__in=("Administrador", "Gestor")
        ).exists():
            return Q()
        return Q(usuario_criador=usuario)
