"""Serviços de pedido: criação no checkout, aprovação e cancelamento."""
import logging
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.shortcuts import get_object_or_404

from customers.models import Cliente
from stock.models import Estoque
from stock.services import (
    dar_baixa_definitiva,
    liberar_reserva,
    reservar,
)

from .cart import Carrinho
from .models import ItemPedido, Pagamento, Pedido

logger = logging.getLogger(__name__)

GRUPOS_INTERNOS = ("Administrador", "Gestor", "Vendedor")


def _pedido_bloqueado(pedido: Pedido) -> Pedido:
    """Re-lê o pedido sob row lock para evitar decisões com instância stale."""
    return Pedido.objects.select_for_update().get(pk=pedido.pk)


def pedidos_visiveis_para(usuario):
    """Recorte de autorização: gestor/admin tudo; vendedor só o que criou."""
    if usuario.is_superuser or usuario.groups.filter(
        name__in=("Administrador", "Gestor")
    ).exists():
        return Pedido.objects.all()
    return Pedido.objects.filter(usuario_criador=usuario)


@transaction.atomic
def alterar_status_operacional(
    pedido_id: int, novo_status: str, *, usuario, request=None
) -> Pedido:
    """Centraliza decisão e gravação sob lock, com autorização por objeto."""
    pedido = get_object_or_404(
        pedidos_visiveis_para(usuario).select_for_update(), pk=pedido_id
    )
    if novo_status == Pedido.Status.CANCELADO:
        return cancelar_pedido(pedido, request=request, usuario=usuario)
    pedido.transicionar(novo_status, request=request, usuario=usuario)
    return pedido


def saldo_disponivel(produto, unidade) -> Decimal:
    """Saldo livre (descontada reserva) do produto na unidade."""
    agregado = Estoque.objects.filter(produto=produto, unidade=unidade).aggregate(
        saldo=Sum("quantidade"), bloqueada=Sum("quantidade_bloqueada")
    )
    return (agregado["saldo"] or Decimal("0")) - (
        agregado["bloqueada"] or Decimal("0")
    )


def _cliente_por_documento(
    *, nome: str, documento: str, email: str, telefone: str,
) -> tuple[Cliente, bool]:
    """Localiza ou cria o cliente pelo documento (armazenado em dígitos).

    SEC-02/R4: o checkout nunca vincula ``Cliente.usuario``. O retorno
    indica também se o cadastro foi criado agora, para que os dados do
    pedido não sejam confundidos com identidade comprovada.
    """
    from customers.models import normalizar_documento

    documento = normalizar_documento(documento)
    cliente = Cliente.objects.filter(documento=documento).first()
    if cliente:
        return cliente, False
    tipo_pessoa = (
        Cliente.TipoPessoa.FISICA
        if len(documento) == 11
        else Cliente.TipoPessoa.JURIDICA
    )
    cliente = Cliente.objects.create(
        nome=nome,
        documento=documento,
        tipo_pessoa=tipo_pessoa,
        categoria=Cliente.Categoria.VAREJO,
        telefone=telefone,
        email=email,
        usuario=None,
    )
    return cliente, True


@transaction.atomic
def criar_pedido_do_carrinho(request, formulario) -> Pedido:
    """Cria o pedido com itens e reserva o estoque — tudo ou nada."""
    carrinho = Carrinho(request)
    itens = carrinho.itens()
    if not itens:
        raise ValidationError("O carrinho está vazio.")

    unidade = formulario.cleaned_data["unidade"]
    _validar_disponibilidade(itens, unidade)

    usuario = request.user if request.user.is_authenticated else None
    criado_por_interno = bool(
        usuario and usuario.groups.filter(name__in=GRUPOS_INTERNOS).exists()
    )
    cliente, _criado = _cliente_por_documento(
        nome=formulario.cleaned_data["nome"],
        documento=formulario.cleaned_data["documento"],
        email=formulario.cleaned_data["email"],
        telefone=formulario.cleaned_data.get("telefone", ""),
    )
    identidade_verificada = bool(
        not criado_por_interno
        and usuario is not None
        and cliente.usuario_id == usuario.pk
        and cliente.vinculo_verificado
    )
    aceita_marketing = bool(
        not criado_por_interno
        and formulario.cleaned_data.get("aceita_marketing")
    )

    canal = Pedido.Canal.VENDEDOR if criado_por_interno else Pedido.Canal.LOJA
    pedido = Pedido.objects.create(
        cliente=cliente,
        nome_contato=formulario.cleaned_data["nome"],
        identidade_verificada=identidade_verificada,
        consentimento_compras=not criado_por_interno,
        consentimento_marketing=aceita_marketing,
        usuario_criador=usuario,
        canal=canal,
        unidade=unidade,
        modalidade=formulario.cleaned_data["modalidade"],
        logradouro=formulario.cleaned_data.get("logradouro", ""),
        numero_endereco=formulario.cleaned_data.get("numero_endereco", ""),
        bairro=formulario.cleaned_data.get("bairro", ""),
        cidade=formulario.cleaned_data.get("cidade", ""),
        uf=formulario.cleaned_data.get("uf", ""),
        cep=formulario.cleaned_data.get("cep", ""),
        contato_email=formulario.cleaned_data["email"],
        contato_telefone=formulario.cleaned_data.get("telefone", ""),
    )

    for item in itens:
        ItemPedido.objects.create(
            pedido=pedido,
            produto=item["produto"],
            produto_nome=item["produto"].nome,
            quantidade=item["quantidade"],
            preco_unitario=item["produto"].preco_online,
        )
        reservar(
            produto=item["produto"],
            unidade=unidade,
            quantidade=item["quantidade"],
        )

    pedido.recalcular_totais()

    ip = request.META.get("REMOTE_ADDR")
    if identidade_verificada:
        # LGPD: somente o titular comprovado exerce consentimentos no cadastro.
        from privacy.services import registrar_consentimento

        registrar_consentimento(
            cliente=cliente,
            finalidade="compras",
            aceito=True,
            ip=ip,
        )
        if aceita_marketing:
            registrar_consentimento(
                cliente=cliente,
                finalidade="marketing",
                aceito=True,
                ip=ip,
            )

    from core.auditoria import registrar_auditoria

    registrar_auditoria(
        acao="pedido.criado",
        instancia=pedido,
        request=request,
        depois={
            "cliente_id": cliente.pk,
            "canal": pedido.canal,
            "identidade_verificada": identidade_verificada,
            "consentimento_compras": pedido.consentimento_compras,
            "consentimento_marketing": pedido.consentimento_marketing,
            "total": str(pedido.total),
            "itens": [
                {
                    "produto": item.produto_nome,
                    "quantidade": str(item.quantidade),
                }
                for item in pedido.itens.all()
            ],
        },
    )

    carrinho.limpar()
    return pedido


def _validar_disponibilidade(itens, unidade) -> None:
    faltas = []
    for item in itens:
        disponivel = saldo_disponivel(item["produto"], unidade)
        if disponivel < item["quantidade"]:
            faltas.append(
                f"{item['produto'].nome} (disponível: {disponivel})"
            )
    if faltas:
        raise ValidationError(
            "Quantidade indisponível em "
            f"{unidade.nome}: " + "; ".join(faltas)
        )


@transaction.atomic
def marcar_pagamento_aprovado(
    pedido: Pedido, *, id_externo: str = "", request=None
) -> None:
    """Idempotente: confirma o financeiro e efetiva a baixa do estoque.

    ADR-002: não altera ``Pedido.status`` (andamento operacional).
    """
    pedido = _pedido_bloqueado(pedido)
    if pedido.status_financeiro == Pedido.StatusFinanceiro.PAGO:
        if not pedido.tem_prova_financeira():
            pedido.financeiro_conciliado = True
            pedido.save(update_fields=["financeiro_conciliado", "atualizado_em"])
            from core.auditoria import registrar_auditoria

            registrar_auditoria(
                acao="pedido.financeiro_reconciliado",
                instancia=pedido,
                request=request,
                depois={
                    "origem": "provedor",
                    "id_externo": id_externo,
                    "financeiro_conciliado": True,
                },
            )
        logger.info("Pedido %s já estava pago; evento ignorado.", pedido.numero)
        return pedido

    if pedido.status == Pedido.Status.CANCELADO:
        _registrar_pagamento_apos_cancelamento(
            pedido, id_externo=id_externo, request=request
        )
        return pedido

    if pedido.status_financeiro in (
        Pedido.StatusFinanceiro.CANCELADO,
        Pedido.StatusFinanceiro.ESTORNADO,
    ):
        from core.auditoria import registrar_auditoria

        logger.error(
            "Pedido %s com financeiro %s recebeu aprovação; "
            "conciliação manual necessária.",
            pedido.numero,
            pedido.status_financeiro,
        )
        registrar_auditoria(
            acao="pedido.pagamento_inconsistente",
            instancia=pedido,
            request=request,
            depois={
                "status": pedido.status,
                "status_financeiro": pedido.status_financeiro,
                "id_externo": id_externo,
            },
        )
        _atualizar_pagamento_aprovado(pedido, id_externo=id_externo)
        return pedido

    if pedido.status in (
        Pedido.Status.RASCUNHO,
        Pedido.Status.FALHOU,
        Pedido.Status.EM_SEPARACAO,
        Pedido.Status.PRONTO_PARA_ENTREGA,
        Pedido.Status.ENVIADO,
        Pedido.Status.CONCLUIDO,
    ):
        from core.auditoria import registrar_auditoria

        logger.error(
            "Pedido %s está em %s sem status financeiro pago; "
            "aprovação exige conciliação manual.",
            pedido.numero,
            pedido.status,
        )
        registrar_auditoria(
            acao="pedido.pagamento_inconsistente",
            instancia=pedido,
            request=request,
            depois={
                "status": pedido.status,
                "status_financeiro": pedido.status_financeiro,
                "id_externo": id_externo,
            },
        )
        _atualizar_pagamento_aprovado(pedido, id_externo=id_externo)
        return pedido

    pedido.definir_status_financeiro(
        Pedido.StatusFinanceiro.PAGO,
        request=request,
        motivo="pagamento aprovado pelo provedor",
    )
    pedido.financeiro_conciliado = True
    pedido.save(update_fields=["financeiro_conciliado", "atualizado_em"])

    for item in pedido.itens.select_related("produto"):
        dar_baixa_definitiva(
            produto=item.produto,
            unidade=pedido.unidade,
            quantidade=item.quantidade,
            pedido=pedido.numero,
            request=request,
        )

    _atualizar_pagamento_aprovado(pedido, id_externo=id_externo)

    from core.auditoria import registrar_auditoria

    registrar_auditoria(
        acao="pedido.pagamento_aprovado",
        instancia=pedido,
        request=request,
        depois={
            "status": pedido.status,
            "status_financeiro": pedido.status_financeiro,
            "financeiro_conciliado": pedido.financeiro_conciliado,
            "id_externo": id_externo,
            "pagamento_id": getattr(
                getattr(pedido, "pagamento", None), "pk", None
            ),
        },
    )
    return pedido


def _atualizar_pagamento_aprovado(pedido: Pedido, *, id_externo: str) -> None:
    pagamento = getattr(pedido, "pagamento", None)
    if pagamento is None:
        return
    from django.utils import timezone

    pagamento.status = Pagamento.Status.APROVADO
    pagamento.id_externo = id_externo or pagamento.id_externo
    pagamento.aprovado_em = timezone.now()
    pagamento.save()


def _registrar_pagamento_apos_cancelamento(
    pedido: Pedido, *, id_externo: str, request
) -> None:
    """Mantém o pedido cancelado e sinaliza conciliação manual."""
    from core.auditoria import registrar_auditoria

    logger.error(
        "Pagamento aprovado para pedido cancelado %s; conciliação manual "
        "necessária (id externo=%s).",
        pedido.numero,
        id_externo,
    )
    _atualizar_pagamento_aprovado(pedido, id_externo=id_externo)
    registrar_auditoria(
        acao="pedido.pagamento_apos_cancelamento",
        instancia=pedido,
        request=request,
        depois={
            "status": pedido.status,
            "status_financeiro": pedido.status_financeiro,
            "id_externo": id_externo,
        },
    )


@transaction.atomic
def reconciliar_pedido_financeiro(
    pedido: Pedido, *, justificativa: str, request=None, origem="manual"
) -> Pedido:
    """Marca prova financeira legada após conciliação humana explícita."""
    if not justificativa.strip():
        raise ValidationError("Justificativa é obrigatória.")
    pedido = _pedido_bloqueado(pedido)
    if pedido.status_financeiro != Pedido.StatusFinanceiro.PAGO:
        raise ValidationError(
            "Só é possível reconciliar pedido com financeiro pago."
        )
    antes = {"financeiro_conciliado": pedido.financeiro_conciliado}
    pedido.financeiro_conciliado = True
    pedido.save(update_fields=["financeiro_conciliado", "atualizado_em"])
    from core.auditoria import registrar_auditoria

    registrar_auditoria(
        acao="pedido.financeiro_reconciliado",
        instancia=pedido,
        request=request,
        antes=antes,
        depois={
            "financeiro_conciliado": True,
            "justificativa": justificativa.strip()[:500],
            "origem": origem,
        },
    )
    return pedido


@transaction.atomic
def cancelar_pedido(
    pedido: Pedido, *, request=None, usuario=None, permitir_pago: bool = True
) -> Pedido:
    """Cancela liberando reservas quando aplicável (idempotente).

    Re-lê o pedido sob lock; ``permitir_pago=False`` é usado pela expiração
    para nunca cancelar um pedido que foi pago concorrentemente.
    Pedido com financeiro PAGO permanece com esse status: o cancelamento
    operacional não presume estorno. O caso é auditado para conciliação.
    """
    pedido = _pedido_bloqueado(pedido)
    if not permitir_pago and pedido.status_financeiro == (
        Pedido.StatusFinanceiro.PAGO
    ):
        logger.info(
            "Pedido %s está pago; expiração/cancelamento automático ignorado.",
            pedido.numero,
        )
        return pedido
    if pedido.status in (Pedido.Status.CANCELADO, Pedido.Status.CONCLUIDO):
        logger.info(
            "Pedido %s não pode ser cancelado a partir de %s.",
            pedido.numero,
            pedido.status,
        )
        return pedido

    status_anterior = pedido.status
    financeiro_anterior = pedido.status_financeiro
    pedido.transicionar(Pedido.Status.CANCELADO, request=request, usuario=usuario)

    if financeiro_anterior == Pedido.StatusFinanceiro.PENDENTE:
        pedido.definir_status_financeiro(
            Pedido.StatusFinanceiro.CANCELADO,
            request=request,
            usuario=usuario,
            motivo="pedido cancelado antes do pagamento",
        )
        pagamento = getattr(pedido, "pagamento", None)
        if pagamento and pagamento.status == Pagamento.Status.PENDENTE:
            pagamento.status = Pagamento.Status.CANCELADO
            pagamento.save(update_fields=["status"])
            from core.auditoria import registrar_auditoria

            registrar_auditoria(
                acao="pedido.pagamento_cancelado",
                instancia=pedido,
                request=request,
                usuario=usuario,
                depois={"pagamento_id": pagamento.pk, "status": pagamento.status},
            )
    elif financeiro_anterior == Pedido.StatusFinanceiro.PAGO:
        from core.auditoria import registrar_auditoria

        registrar_auditoria(
            acao="pedido.cancelado_com_pagamento",
            instancia=pedido,
            request=request,
            usuario=usuario,
            depois={
                "status": pedido.status,
                "status_financeiro": pedido.status_financeiro,
                "motivo": "cancelamento após pagamento exige conciliação",
            },
        )

    if (
        financeiro_anterior == Pedido.StatusFinanceiro.PENDENTE
        and status_anterior
        in (
            Pedido.Status.AGUARDANDO_PAGAMENTO,
            Pedido.Status.PAGAMENTO_PENDENTE,
        )
    ):
        itens_liberados = []
        for item in pedido.itens.select_related("produto"):
            liberar_reserva(
                produto=item.produto,
                unidade=pedido.unidade,
                quantidade=item.quantidade,
            )
            itens_liberados.append(
                {
                    "produto": item.produto_nome,
                    "quantidade": str(item.quantidade),
                }
            )
        if itens_liberados:
            from core.auditoria import registrar_auditoria

            registrar_auditoria(
                acao="pedido.reservas_liberadas",
                instancia=pedido,
                request=request,
                usuario=usuario,
                depois={
                    "status_anterior": status_anterior,
                    "itens": itens_liberados,
                },
            )

    from .emails import email_pedido_cancelado

    email_pedido_cancelado(pedido)
    return pedido


STATUS_PROVEDOR_PARA_PAGAMENTO = {
    "approved": Pagamento.Status.APROVADO,
    "refused": Pagamento.Status.RECUSADO,
    "rejected": Pagamento.Status.RECUSADO,
    "cancelled": Pagamento.Status.CANCELADO,
    "charged_back": Pagamento.Status.CANCELADO,
    "refunded": Pagamento.Status.CANCELADO,
    "pending": Pagamento.Status.PENDENTE,
    "in_process": Pagamento.Status.PENDENTE,
}


class ResultadoPagamentoInvalido(Exception):
    """Resposta do provedor não corresponde ao contrato local da tentativa."""

    def __init__(self, motivo: str):
        self.motivo = motivo
        super().__init__(motivo)


def _validar_contrato_pagamento(
    pedido: Pedido, dados_consulta: dict, *, id_consultado=None
) -> Pagamento:
    """Valida tentativa local, ID, valor, moeda, recebedor e ambiente."""
    pagamento = getattr(pedido, "pagamento", None)
    if pagamento is None:
        raise ResultadoPagamentoInvalido(
            "pedido não possui tentativa de pagamento local"
        )
    if pagamento.valor != pedido.total:
        raise ResultadoPagamentoInvalido(
            "tentativa local com valor divergente do pedido"
        )

    id_retornado = str(dados_consulta.get("id") or "").strip()
    if not id_retornado:
        raise ResultadoPagamentoInvalido("resposta sem id de pagamento")
    if id_consultado not in (None, "") and id_retornado != str(id_consultado):
        raise ResultadoPagamentoInvalido(
            "id retornado difere do recurso consultado"
        )
    if pagamento.id_externo and pagamento.id_externo != id_retornado:
        raise ResultadoPagamentoInvalido(
            "tentativa local pertence a outro id externo"
        )

    external_reference = str(
        dados_consulta.get("external_reference") or ""
    ).strip()
    if external_reference != pedido.numero:
        raise ResultadoPagamentoInvalido(
            "external_reference não corresponde ao pedido"
        )

    valor_bruto = dados_consulta.get("transaction_amount")
    if valor_bruto is None:
        raise ResultadoPagamentoInvalido("resposta sem valor")
    try:
        valor = Decimal(str(valor_bruto))
    except (InvalidOperation, TypeError, ValueError) as erro:
        raise ResultadoPagamentoInvalido("valor inválido") from erro
    if valor != pedido.total:
        raise ResultadoPagamentoInvalido(
            f"valor divergente: provedor={valor}, pedido={pedido.total}"
        )

    moeda = str(dados_consulta.get("currency_id") or "").strip().upper()
    if moeda != "BRL":
        raise ResultadoPagamentoInvalido(f"moeda divergente: {moeda or 'ausente'}")

    collector = str(dados_consulta.get("collector_id") or "").strip()
    collector_configurado = str(
        getattr(settings, "MERCADO_PAGO_COLLECTOR_ID", "") or ""
    ).strip()
    if collector_configurado:
        if collector != collector_configurado:
            raise ResultadoPagamentoInvalido("recebedor divergente")
    elif not getattr(settings, "MERCADO_PAGO_FAKE", False):
        raise ResultadoPagamentoInvalido("recebedor não configurado")

    if "live_mode" in dados_consulta:
        live_mode = dados_consulta.get("live_mode")
        if isinstance(live_mode, str):
            live_mode = live_mode.strip().lower() == "true"
        if bool(live_mode) != bool(
            getattr(settings, "MERCADO_PAGO_LIVE_MODE", False)
        ):
            raise ResultadoPagamentoInvalido("ambiente (live_mode) divergente")
    elif not getattr(settings, "MERCADO_PAGO_FAKE", False):
        raise ResultadoPagamentoInvalido("resposta sem live_mode")

    return pagamento


def _registrar_contrato_invalido(
    pedido: Pedido, dados_consulta: dict, erro: ResultadoPagamentoInvalido, request
) -> None:
    from core.auditoria import registrar_auditoria

    registrar_auditoria(
        acao="pedido.pagamento_contrato_invalido",
        instancia=pedido,
        request=request,
        depois={
            "motivo": erro.motivo[:300],
            "id_retornado": str(dados_consulta.get("id") or "")[:80],
            "external_reference": str(
                dados_consulta.get("external_reference") or ""
            )[:30],
            "status_provedor": str(
                dados_consulta.get("status") or ""
            )[:30],
        },
    )


def _atualizar_pagamento_resultado(
    pedido: Pedido, *, status_provedor: str, id_externo: str
) -> None:
    pagamento = getattr(pedido, "pagamento", None)
    novo_status = STATUS_PROVEDOR_PARA_PAGAMENTO.get(status_provedor)
    if pagamento is None or novo_status is None:
        return
    if (
        pagamento.status == Pagamento.Status.APROVADO
        and status_provedor not in ("charged_back", "refunded")
    ):
        return
    if novo_status == Pagamento.Status.PENDENTE and pagamento.status in (
        Pagamento.Status.APROVADO,
        Pagamento.Status.RECUSADO,
        Pagamento.Status.CANCELADO,
    ):
        return
    pagamento.status = novo_status
    pagamento.id_externo = id_externo or pagamento.id_externo
    pagamento.save(update_fields=["status", "id_externo"])


def _registrar_resultado_financeiro(
    pedido: Pedido, *, acao: str, status_provedor: str,
    id_externo: str, request,
) -> None:
    from core.auditoria import registrar_auditoria

    registrar_auditoria(
        acao=acao,
        instancia=pedido,
        request=request,
        depois={
            "status_provedor": status_provedor,
            "status": pedido.status,
            "status_financeiro": pedido.status_financeiro,
            "id_externo": id_externo,
        },
    )


def _aplicar_resultado_valido(
    pedido: Pedido,
    dados_consulta: dict,
    *,
    request,
    status_provedor: str,
    id_externo: str,
) -> Pedido:
    """Aplica um resultado já validado, com o pedido bloqueado pelo chamador."""
    if status_provedor == "approved":
        ja_estava_pago = (
            pedido.status_financeiro == Pedido.StatusFinanceiro.PAGO
        )
        pedido = marcar_pagamento_aprovado(
            pedido, id_externo=id_externo, request=request
        )
        if (
            not ja_estava_pago
            and pedido.status_financeiro == Pedido.StatusFinanceiro.PAGO
        ):
            from .emails import email_pagamento_aprovado

            email_pagamento_aprovado(pedido)
        return pedido

    _atualizar_pagamento_resultado(
        pedido, status_provedor=status_provedor, id_externo=id_externo
    )

    if status_provedor in ("charged_back", "refunded"):
        if pedido.status_financeiro != Pedido.StatusFinanceiro.PAGO:
            logger.warning(
                "Chargeback sem pagamento aprovado no pedido %s.",
                pedido.numero,
            )
            _registrar_resultado_financeiro(
                pedido,
                acao="pedido.pagamento_estorno_inconsistente",
                status_provedor=status_provedor,
                id_externo=id_externo,
                request=request,
            )
            return pedido
        pedido.definir_status_financeiro(
            Pedido.StatusFinanceiro.ESTORNADO,
            request=request,
            motivo="chargeback do provedor",
        )
        if pedido.status not in (
            Pedido.Status.CANCELADO,
            Pedido.Status.CONCLUIDO,
        ):
            try:
                pedido.transicionar(Pedido.Status.CANCELADO, request=request)
            except ValidationError:
                logger.error(
                    "Chargeback no pedido %s em %s; cancelamento operacional "
                    "exige revisão manual.",
                    pedido.numero,
                    pedido.status,
                )
                _registrar_resultado_financeiro(
                    pedido,
                    acao="pedido.estorno_com_andamento",
                    status_provedor=status_provedor,
                    id_externo=id_externo,
                    request=request,
                )
        _registrar_resultado_financeiro(
            pedido,
            acao="pedido.pagamento_estornado",
            status_provedor=status_provedor,
            id_externo=id_externo,
            request=request,
        )
        return pedido

    if status_provedor in ("refused", "rejected", "cancelled"):
        if pedido.status_financeiro == Pedido.StatusFinanceiro.PAGO:
            logger.warning(
                "Evento %s ignorado: pedido %s já está pago.",
                status_provedor,
                pedido.numero,
            )
            _registrar_resultado_financeiro(
                pedido,
                acao="pedido.pagamento_evento_ignorado",
                status_provedor=status_provedor,
                id_externo=id_externo,
                request=request,
            )
            return pedido
        if pedido.status in (
            Pedido.Status.EM_SEPARACAO,
            Pedido.Status.PRONTO_PARA_ENTREGA,
            Pedido.Status.ENVIADO,
            Pedido.Status.CONCLUIDO,
        ):
            logger.warning(
                "Evento %s ignorado: pedido %s já está em andamento (%s).",
                status_provedor,
                pedido.numero,
                pedido.status,
            )
            _registrar_resultado_financeiro(
                pedido,
                acao="pedido.pagamento_evento_ignorado",
                status_provedor=status_provedor,
                id_externo=id_externo,
                request=request,
            )
            return pedido
        pedido = cancelar_pedido(pedido, request=request)
        _registrar_resultado_financeiro(
            pedido,
            acao=(
                "pedido.pagamento_recusado"
                if status_provedor in ("refused", "rejected")
                else "pedido.pagamento_cancelado"
            ),
            status_provedor=status_provedor,
            id_externo=id_externo,
            request=request,
        )
        return pedido

    if status_provedor in ("pending", "in_process"):
        if (
            pedido.status_financeiro != Pedido.StatusFinanceiro.PENDENTE
            or pedido.status
            in (
                Pedido.Status.CANCELADO,
                Pedido.Status.CONCLUIDO,
            )
        ):
            logger.warning(
                "Evento %s ignorado: pedido %s está em %s/%s.",
                status_provedor,
                pedido.numero,
                pedido.status,
                pedido.status_financeiro,
            )
            _registrar_resultado_financeiro(
                pedido,
                acao="pedido.pagamento_evento_ignorado",
                status_provedor=status_provedor,
                id_externo=id_externo,
                request=request,
            )
            return pedido
        pedido.definir_status_financeiro(
            Pedido.StatusFinanceiro.PENDENTE,
            request=request,
            motivo=f"provedor informou {status_provedor}",
        )
        _registrar_resultado_financeiro(
            pedido,
            acao="pedido.pagamento_pendente",
            status_provedor=status_provedor,
            id_externo=id_externo,
            request=request,
        )
        return pedido

    if status_provedor == "in_mediation":
        _registrar_resultado_financeiro(
            pedido,
            acao="pedido.pagamento_em_mediacao",
            status_provedor=status_provedor,
            id_externo=id_externo,
            request=request,
        )
        return pedido

    _registrar_resultado_financeiro(
        pedido,
        acao="pedido.pagamento_status_desconhecido",
        status_provedor=status_provedor,
        id_externo=id_externo,
        request=request,
    )
    return pedido


def aplicar_resultado_pagamento(
    dados_consulta: dict, *, request=None, id_consultado=None
) -> Pedido | None:
    """Valida o contrato e aplica o resultado sob lock.

    R1/PAY-02: divergência de tentativa/ID/valor/moeda/recebedor/ambiente
    não altera pedido, pagamento ou estoque; gera LogAuditoria e levanta
    ``ResultadoPagamentoInvalido`` após commitar a ocorrência.
    """
    numero = str(dados_consulta.get("external_reference") or "")
    status_provedor = str(dados_consulta.get("status") or "")
    id_externo = str(dados_consulta.get("id") or "")

    pedido_inicial = Pedido.objects.filter(numero=numero).first()
    if pedido_inicial is None:
        logger.warning("Notificação sem pedido correspondente: %s", numero)
        return None

    erro_contrato = None
    resultado = None
    with transaction.atomic():
        pedido = Pedido.objects.select_for_update().get(pk=pedido_inicial.pk)
        try:
            _validar_contrato_pagamento(
                pedido, dados_consulta, id_consultado=id_consultado
            )
        except ResultadoPagamentoInvalido as erro:
            logger.error(
                "Resultado de pagamento inválido para %s: %s",
                pedido.numero,
                erro.motivo,
            )
            _registrar_contrato_invalido(
                pedido, dados_consulta, erro, request
            )
            erro_contrato = erro
        else:
            resultado = _aplicar_resultado_valido(
                pedido,
                dados_consulta,
                request=request,
                status_provedor=status_provedor,
                id_externo=id_externo,
            )

    if erro_contrato is not None:
        raise erro_contrato
    return resultado
