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
    usuario=None,
) -> Cliente:
    """Localiza ou cria o cliente pelo documento (armazenado em dígitos)."""
    from customers.models import normalizar_documento

    documento = normalizar_documento(documento)
    cliente = Cliente.objects.filter(documento=documento).first()
    if cliente:
        if usuario is not None and cliente.usuario_id is None:
            cliente.usuario = usuario
            cliente.save(update_fields=["usuario"])
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
        usuario=usuario,
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
        usuario=usuario,
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
def marcar_pagamento_aprovado(pedido: Pedido, *, id_externo: str = "") -> None:
    """Idempotente: move o pedido para 'pago' e efetiva a baixa do estoque."""
    if pedido.status == Pedido.Status.PAGO:
        logger.info("Pedido %s já estava pago; evento ignorado.", pedido.numero)
        return

    pedido.transicionar(Pedido.Status.PAGO)

    for item in pedido.itens.select_related("produto"):
        dar_baixa_definitiva(
            produto=item.produto,
            unidade=pedido.unidade,
            quantidade=item.quantidade,
            pedido=pedido.numero,
        )

    pagamento = getattr(pedido, "pagamento", None)
    if pagamento is not None:
        from django.utils import timezone

        pagamento.status = Pagamento.Status.APROVADO
        pagamento.id_externo = id_externo or pagamento.id_externo
        pagamento.aprovado_em = timezone.now()
        pagamento.save()


@transaction.atomic
def cancelar_pedido(pedido: Pedido) -> None:
    """Cancela liberando reservas quando aplicável (idempotente)."""
    if pedido.status in (Pedido.Status.CANCELADO, Pedido.Status.CONCLUIDO):
        logger.info(
            "Pedido %s não pode ser cancelado a partir de %s.",
            pedido.numero,
            pedido.status,
        )
        return

    status_anterior = pedido.status
    pedido.transicionar(Pedido.Status.CANCELADO)

    if status_anterior in (
        Pedido.Status.AGUARDANDO_PAGAMENTO,
        Pedido.Status.PAGAMENTO_PENDENTE,
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
}


@transaction.atomic
def aplicar_resultado_pagamento(dados_consulta: dict) -> Pedido | None:
    """Aplica o resultado consultado no provedor ao pedido correspondente.

    Idempotente: eventos já refletidos não produzem novo efeito.
    """
    numero = str(dados_consulta.get("external_reference") or "")
    status_provedor = str(dados_consulta.get("status") or "")
    id_externo = str(dados_consulta.get("id") or "")

    pedido = Pedido.objects.filter(numero=numero).first()
    if pedido is None:
        logger.warning("Notificação sem pedido correspondente: %s", numero)
        return None

    if status_provedor == "approved":
        ja_estava_pago = pedido.status == Pedido.Status.PAGO
        marcar_pagamento_aprovado(pedido, id_externo=id_externo)
        if not ja_estava_pago:
            from .emails import email_pagamento_aprovado

            email_pagamento_aprovado(pedido)
        return pedido

    pagamento = getattr(pedido, "pagamento", None)
    if pagamento is not None:
        novo_status = STATUS_PROVEDOR_PARA_PAGAMENTO.get(status_provedor)
        if novo_status:
            pagamento.status = novo_status
            pagamento.id_externo = id_externo or pagamento.id_externo
            pagamento.save()

    if status_provedor in ("refused", "cancelled", "charged_back"):
        if pedido.status in (
            Pedido.Status.AGUARDANDO_PAGAMENTO,
            Pedido.Status.PAGAMENTO_PENDENTE,
        ):
            pedido.transicionar(Pedido.Status.FALHOU)
            # Recusa libera a reserva; o saldo volta a ficar disponível.
            for item in pedido.itens.select_related("produto"):
                liberar_reserva(
                    produto=item.produto,
                    unidade=pedido.unidade,
                    quantidade=item.quantidade,
                )
    elif status_provedor in ("pending", "in_process"):
        if pedido.status == Pedido.Status.AGUARDANDO_PAGAMENTO:
            pedido.transicionar(Pedido.Status.PAGAMENTO_PENDENTE)
    return pedido
