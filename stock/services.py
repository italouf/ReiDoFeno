"""Serviço transacional de estoque.

Toda alteração de saldo passa por aqui: trava a linha do estoque
(``select_for_update``), valida regras, grava o movimento imutável com
``delta`` assinado e emite aviso de estoque baixo quando o mínimo é
alcançado.
"""
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F, Sum
from django.utils import timezone

from analytics.models import Aviso

from .exceptions import ImutabilidadeViolation
from .models import (
    TIPOS_DELTA_NEGATIVO,
    TIPOS_DELTA_POSITIVO,
    Estoque,
    MovimentoEstoque,
    ReservaEstoque,
)

__all__ = [
    "ImutabilidadeViolation",
    "consumir_reserva",
    "dar_baixa_definitiva",
    "liberar_bloqueio_legado",
    "liberar_reserva",
    "registrar_ajuste",
    "registrar_movimento",
    "reservar",
    "saldo_ledger",
    "transferir_estoque",
]

_TIPOS_AJUSTE = frozenset(
    {
        MovimentoEstoque.Tipo.AJUSTE,
        MovimentoEstoque.Tipo.AJUSTE_POSITIVO,
        MovimentoEstoque.Tipo.AJUSTE_NEGATIVO,
    }
)
_TIPOS_TRANSFERENCIA = frozenset(
    {
        MovimentoEstoque.Tipo.TRANSFERENCIA_ENTRADA,
        MovimentoEstoque.Tipo.TRANSFERENCIA_SAIDA,
    }
)


def _decimal(valor, campo: str) -> Decimal:
    try:
        return Decimal(str(valor))
    except (InvalidOperation, TypeError, ValueError) as erro:
        raise ValidationError(f"{campo} deve ser um número decimal.") from erro


def _quantidade_positiva(quantidade) -> Decimal:
    quantidade = _decimal(quantidade, "Quantidade")
    if quantidade <= 0:
        raise ValidationError("A quantidade deve ser maior que zero.")
    return quantidade


def _resolver_delta(
    *, tipo: str, delta=None, quantidade=None
) -> Decimal:
    """Resolve o delta assinado a partir da API nova ou da API legada."""
    if delta is not None and quantidade is not None:
        raise ValidationError("Informe delta ou quantidade, não ambos.")
    if delta is None and quantidade is None:
        raise ValidationError("Delta é obrigatório.")

    if delta is None:
        valor = _decimal(quantidade, "Quantidade")
        if valor == 0:
            raise ValidationError("A quantidade não pode ser zero.")
        if tipo in TIPOS_DELTA_NEGATIVO:
            delta = -abs(valor)
        elif tipo in TIPOS_DELTA_POSITIVO:
            delta = abs(valor)
        else:  # tipos legados aceitam o sinal informado
            delta = valor
    else:
        delta = _decimal(delta, "Delta")

    if delta == 0:
        raise ValidationError("Delta não pode ser zero.")
    if tipo in TIPOS_DELTA_POSITIVO and delta < 0:
        raise ValidationError(f"Tipo {tipo} exige delta positivo.")
    if tipo in TIPOS_DELTA_NEGATIVO and delta > 0:
        raise ValidationError(f"Tipo {tipo} exige delta negativo.")
    return delta


@transaction.atomic
def registrar_movimento(
    *,
    produto,
    unidade,
    tipo: str,
    delta=None,
    quantidade=None,
    usuario=None,
    motivo: str = "",
    quantidade_minima=None,
    request=None,
    movimento_par=None,
    _transferencia_interna: bool = False,
) -> MovimentoEstoque:
    """Registra um movimento com sinal e atualiza o saldo atomicamente.

    ``delta`` é a API canônica. ``quantidade`` é aceita para compatibilidade
    com chamadas da Fase 1 e é interpretada conforme o tipo (saídas ficam
    negativas; ajustes legados preservam o sinal informado).
    """
    tipo = MovimentoEstoque.Tipo(tipo)
    delta = _resolver_delta(tipo=tipo, delta=delta, quantidade=quantidade)

    motivo = (motivo or "").strip()
    if tipo in _TIPOS_AJUSTE and not motivo:
        raise ValidationError("Ajuste manual exige motivo obrigatório.")
    if (
        tipo in _TIPOS_TRANSFERENCIA
        and not _transferencia_interna
        and movimento_par is None
    ):
        raise ValidationError(
            "Movimento de transferência exige movimento_par."
        )

    estoque, _ = Estoque.objects.select_for_update().get_or_create(
        produto=produto,
        unidade=unidade,
        defaults={"quantidade_minima": quantidade_minima or 0},
    )

    novo_saldo = estoque.quantidade + delta
    if novo_saldo < estoque.quantidade_bloqueada:
        if tipo == MovimentoEstoque.Tipo.SAIDA:
            raise ValidationError(
                "Saída acima do saldo disponível (descontando reserva)."
            )
        if tipo in _TIPOS_AJUSTE:
            raise ValidationError(
                "Ajuste deixaria o saldo abaixo da quantidade bloqueada."
            )
        raise ValidationError(
            "Movimento deixaria o saldo abaixo da quantidade bloqueada."
        )

    Estoque.objects.filter(pk=estoque.pk).update(
        quantidade=F("quantidade") + delta
    )
    estoque.quantidade = novo_saldo  # instância em memória para aviso/auditoria

    movimento = MovimentoEstoque.objects.create(
        produto=produto,
        unidade=unidade,
        tipo=tipo,
        delta=delta,
        quantidade=abs(delta),
        motivo=motivo,
        usuario=usuario,
        movimento_par=movimento_par,
    )

    if tipo in _TIPOS_AJUSTE:
        acao = "estoque.ajuste_manual"
    else:
        acao = "estoque.movimento"

    from core.auditoria import registrar_auditoria

    registrar_auditoria(
        acao=acao,
        instancia=movimento,
        request=request,
        usuario=usuario,
        antes={"saldo_anterior": str(estoque.quantidade - delta)},
        depois={
            "saldo_novo": str(estoque.quantidade),
            "tipo": tipo,
            "delta": str(delta),
            "motivo": motivo,
        },
    )

    _avisar_estoque_baixo(estoque)
    return movimento


def registrar_ajuste(
    *, produto, unidade, delta, motivo, usuario=None, request=None
) -> MovimentoEstoque:
    """Atalho para ajuste manual com sinal explícito."""
    delta = _decimal(delta, "Delta")
    tipo = (
        MovimentoEstoque.Tipo.AJUSTE_POSITIVO
        if delta > 0
        else MovimentoEstoque.Tipo.AJUSTE_NEGATIVO
    )
    return registrar_movimento(
        produto=produto,
        unidade=unidade,
        tipo=tipo,
        delta=delta,
        motivo=motivo,
        usuario=usuario,
        request=request,
    )


@transaction.atomic
def transferir_estoque(
    *, produto, unidade_origem, unidade_destino, quantidade, usuario=None,
    request=None,
) -> tuple[MovimentoEstoque, MovimentoEstoque]:
    """Transfere estoque gerando saída na origem e entrada no destino vinculadas."""
    quantidade = _quantidade_positiva(quantidade)

    saida = registrar_movimento(
        produto=produto,
        unidade=unidade_origem,
        tipo=MovimentoEstoque.Tipo.TRANSFERENCIA_SAIDA,
        delta=-quantidade,
        usuario=usuario,
        motivo=f"Transferência para {unidade_destino.nome}",
        request=request,
        _transferencia_interna=True,
    )
    entrada = registrar_movimento(
        produto=produto,
        unidade=unidade_destino,
        tipo=MovimentoEstoque.Tipo.TRANSFERENCIA_ENTRADA,
        delta=quantidade,
        usuario=usuario,
        motivo=f"Transferência de {unidade_origem.nome}",
        request=request,
        movimento_par=saida,
    )
    MovimentoEstoque.objects.filter(pk=saida.pk)._update_permitido(
        movimento_par=entrada
    )
    saida.movimento_par = entrada
    return saida, entrada


def saldo_ledger(produto, unidade) -> Decimal:
    """Reconstrói o saldo exclusivamente pela soma dos deltas do ledger."""
    total = MovimentoEstoque.objects.filter(
        produto=produto, unidade=unidade
    ).aggregate(total=Sum("delta"))["total"]
    return total or Decimal("0.00")


def _avisar_estoque_baixo(estoque: Estoque) -> None:
    if estoque.quantidade <= estoque.quantidade_minima:
        Aviso.registrar(
            tipo=Aviso.Tipo.ESTOQUE_BAIXO,
            mensagem=(
                f"{estoque.produto} atingiu o mínimo em {estoque.unidade}: "
                f"saldo {estoque.quantidade} (mínimo {estoque.quantidade_minima})."
            ),
            objeto=estoque,
            severidade=Aviso.Severidade.ALERTA,
        )


def reservar(
    *, produto, unidade, quantidade, pedido=None, item_pedido=None
) -> ReservaEstoque:
    """Cria reserva identificada pelo pedido e bloqueia o estoque."""
    quantidade = _quantidade_positiva(quantidade)
    if pedido is None:
        raise ValidationError(
            "Reserva de estoque exige pedido identificado; "
            "reservas órfãs não são permitidas."
        )
    if item_pedido is not None and item_pedido.pedido_id != pedido.pk:
        raise ValidationError("Item do pedido não pertence ao pedido informado.")

    with transaction.atomic():
        estoque = (
            Estoque.objects.select_for_update()
            .filter(produto=produto, unidade=unidade)
            .first()
        )
        if estoque is None or estoque.disponivel < quantidade:
            raise ValidationError("Quantidade indisponível na unidade.")

        reserva = ReservaEstoque.objects.create(
            pedido=pedido,
            item_pedido=item_pedido,
            produto=produto,
            unidade=unidade,
            quantidade=quantidade,
            status=ReservaEstoque.Status.ATIVA,
        )
        Estoque.objects.filter(pk=estoque.pk).update(
            quantidade_bloqueada=F("quantidade_bloqueada") + quantidade
        )
        return reserva


def _estoque_bloqueado(produto, unidade) -> Estoque:
    return Estoque.objects.select_for_update().get(
        produto=produto, unidade=unidade
    )


def _desbloquear(estoque: Estoque, quantidade) -> None:
    if estoque.quantidade_bloqueada < quantidade:
        raise ValidationError(
            "Reserva inconsistente: quantidade bloqueada menor que a reserva."
        )
    Estoque.objects.filter(pk=estoque.pk).update(
        quantidade_bloqueada=F("quantidade_bloqueada") - quantidade
    )


def _sincronizar_reserva(original, atual):
    if original is atual:
        return
    original.status = atual.status
    original.consumida_em = atual.consumida_em
    original.liberada_em = atual.liberada_em


@transaction.atomic
def consumir_reserva(
    reserva: ReservaEstoque, *, usuario=None, request=None
) -> ReservaEstoque:
    """Consome uma reserva ativa; idempotente para reserva já finalizada."""
    original = reserva
    reserva = ReservaEstoque.objects.select_for_update().get(pk=reserva.pk)
    if reserva.status != ReservaEstoque.Status.ATIVA:
        _sincronizar_reserva(original, reserva)
        return reserva

    estoque = _estoque_bloqueado(reserva.produto, reserva.unidade)
    _desbloquear(estoque, reserva.quantidade)

    registrar_movimento(
        produto=reserva.produto,
        unidade=reserva.unidade,
        tipo=MovimentoEstoque.Tipo.BAIXA_DEFINITIVA,
        delta=-reserva.quantidade,
        motivo=f"Consumo da reserva do pedido {reserva.pedido.numero}",
        usuario=usuario,
        request=request,
    )

    reserva.status = ReservaEstoque.Status.CONSUMIDA
    reserva.consumida_em = timezone.now()
    reserva.save(update_fields=["status", "consumida_em"])
    _sincronizar_reserva(original, reserva)
    return reserva


@transaction.atomic
def liberar_reserva(reserva: ReservaEstoque) -> ReservaEstoque:
    """Libera uma reserva ativa; idempotente e sem movimento de estoque."""
    original = reserva
    reserva = ReservaEstoque.objects.select_for_update().get(pk=reserva.pk)
    if reserva.status != ReservaEstoque.Status.ATIVA:
        _sincronizar_reserva(original, reserva)
        return reserva

    estoque = _estoque_bloqueado(reserva.produto, reserva.unidade)
    _desbloquear(estoque, reserva.quantidade)

    reserva.status = ReservaEstoque.Status.LIBERADA
    reserva.liberada_em = timezone.now()
    reserva.save(update_fields=["status", "liberada_em"])
    _sincronizar_reserva(original, reserva)
    return reserva


def liberar_bloqueio_legado(*, produto, unidade, quantidade) -> None:
    """Compatibilidade com bloqueios legados sem identidade de pedido."""
    quantidade = _quantidade_positiva(quantidade)
    with transaction.atomic():
        estoque = (
            Estoque.objects.select_for_update()
            .filter(produto=produto, unidade=unidade)
            .first()
        )
        if estoque is None:
            return
        novo_bloqueio = max(
            estoque.quantidade_bloqueada - quantidade, Decimal("0.00")
        )
        Estoque.objects.filter(pk=estoque.pk).update(
            quantidade_bloqueada=novo_bloqueio
        )


@transaction.atomic
def dar_baixa_definitiva(
    *, produto, unidade, quantidade, pedido=None, usuario=None, request=None
) -> None:
    """Converte reserva agregada legada em saída definitiva."""
    quantidade = _quantidade_positiva(quantidade)
    liberar_bloqueio_legado(
        produto=produto, unidade=unidade, quantidade=quantidade
    )
    registrar_movimento(
        produto=produto,
        unidade=unidade,
        tipo=MovimentoEstoque.Tipo.BAIXA_DEFINITIVA,
        delta=-quantidade,
        usuario=usuario,
        motivo=f"Baixa definitiva por pedido {pedido}",
        request=request,
    )
