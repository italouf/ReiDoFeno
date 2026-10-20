"""Serviços de pedido: criação no checkout, aprovação e cancelamento."""
import logging
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum

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
) -> Cliente:
    """Localiza ou cria o cliente pelo documento (armazenado em dígitos).

    SEC-02: o checkout nunca vincula ``Cliente.usuario``. O vínculo exige
    comprovação de posse do e-mail cadastrado (customers.services) ou ato
    administrativo auditado.
    """
    from customers.models import normalizar_documento

    documento = normalizar_documento(documento)
    cliente = Cliente.objects.filter(documento=documento).first()
    if cliente:
        return cliente
    tipo_pessoa = (
        Cliente.TipoPessoa.FISICA
        if len(documento) == 11
        else Cliente.TipoPessoa.JURIDICA
    )
    return Cliente.objects.create(
        nome=nome,
        documento=documento,
        tipo_pessoa=tipo_pessoa,
        categoria=Cliente.Categoria.VAREJO,
        telefone=telefone,
        email=email,
        usuario=None,
    )


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
    cliente = _cliente_por_documento(
        nome=formulario.cleaned_data["nome"],
        documento=formulario.cleaned_data["documento"],
        email=formulario.cleaned_data["email"],
        telefone=formulario.cleaned_data.get("telefone", ""),
    )

    canal = Pedido.Canal.VENDEDOR if criado_por_interno else Pedido.Canal.LOJA
    pedido = Pedido.objects.create(
        cliente=cliente,
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

    # LGPD: consentimento de compras (base contrato) + marketing (opcional).
    from privacy.services import registrar_consentimento

    ip = request.META.get("REMOTE_ADDR")
    registrar_consentimento(
        cliente=cliente,
        finalidade="compras",
        aceito=True,
        ip=ip,
    )
    if formulario.cleaned_data.get("aceita_marketing"):
        registrar_consentimento(
            cliente=cliente,
            finalidade="marketing",
            aceito=True,
            ip=ip,
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
    if pedido.status_financeiro == Pedido.StatusFinanceiro.PAGO:
        logger.info("Pedido %s já estava pago; evento ignorado.", pedido.numero)
        return

    if pedido.status == Pedido.Status.CANCELADO:
        _registrar_pagamento_apos_cancelamento(
            pedido, id_externo=id_externo, request=request
        )
        return

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
        return

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
        return

    pedido.definir_status_financeiro(
        Pedido.StatusFinanceiro.PAGO,
        request=request,
        motivo="pagamento aprovado pelo provedor",
    )

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
            "id_externo": id_externo,
            "pagamento_id": getattr(
                getattr(pedido, "pagamento", None), "pk", None
            ),
        },
    )


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
def cancelar_pedido(pedido: Pedido, *, request=None, usuario=None) -> None:
    """Cancela liberando reservas quando aplicável (idempotente).

    Pedido com financeiro PAGO permanece com esse status: o cancelamento
    operacional não presume estorno. O caso é auditado para conciliação.
    """
    if pedido.status in (Pedido.Status.CANCELADO, Pedido.Status.CONCLUIDO):
        logger.info(
            "Pedido %s não pode ser cancelado a partir de %s.",
            pedido.numero,
            pedido.status,
        )
        return

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
        for item in pedido.itens.select_related("produto"):
            liberar_reserva(
                produto=item.produto,
                unidade=pedido.unidade,
                quantidade=item.quantidade,
            )

    from .emails import email_pedido_cancelado

    email_pedido_cancelado(pedido)


STATUS_PROVEDOR_PARA_PAGAMENTO = {
    "approved": Pagamento.Status.APROVADO,
    "refused": Pagamento.Status.RECUSADO,
    "cancelled": Pagamento.Status.CANCELADO,
    "charged_back": Pagamento.Status.CANCELADO,
    "pending": Pagamento.Status.PENDENTE,
    "in_process": Pagamento.Status.PENDENTE,
}


def _atualizar_pagamento_resultado(
    pedido: Pedido, *, status_provedor: str, id_externo: str
) -> None:
    pagamento = getattr(pedido, "pagamento", None)
    novo_status = STATUS_PROVEDOR_PARA_PAGAMENTO.get(status_provedor)
    if pagamento is None or novo_status is None:
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


@transaction.atomic
def aplicar_resultado_pagamento(dados_consulta: dict, *, request=None) -> Pedido | None:
    """Aplica o resultado consultado no provedor ao pedido correspondente.

    ADR-002/PAY-02: eventos fora de ordem não rebaixam um pagamento já
    aprovado. A aprovação altera apenas o financeiro; recusa/cancelamento
    encerram o andamento operacional e liberam reservas.
    """
    numero = str(dados_consulta.get("external_reference") or "")
    status_provedor = str(dados_consulta.get("status") or "")
    id_externo = str(dados_consulta.get("id") or "")

    pedido = Pedido.objects.select_for_update().filter(numero=numero).first()
    if pedido is None:
        logger.warning("Notificação sem pedido correspondente: %s", numero)
        return None

    if status_provedor == "approved":
        ja_estava_pago = (
            pedido.status_financeiro == Pedido.StatusFinanceiro.PAGO
        )
        marcar_pagamento_aprovado(
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

    if status_provedor == "charged_back":
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

    if status_provedor in ("refused", "cancelled"):
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
        cancelar_pedido(pedido, request=request)
        _registrar_resultado_financeiro(
            pedido,
            acao=(
                "pedido.pagamento_recusado"
                if status_provedor == "refused"
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
