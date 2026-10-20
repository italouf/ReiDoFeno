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

from analytics.models import Aviso

from .exceptions import ImutabilidadeViolation
from .models import (
    TIPOS_DELTA_NEGATIVO,
    TIPOS_DELTA_POSITIVO,
    Estoque,
    MovimentoEstoque,
)

__all__ = [
    "ImutabilidadeViolation",
    "dar_baixa_definitiva",
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
    if novo_saldo < 0:
        raise ValidationError("O saldo não pode ficar negativo.")

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


def reservar(*, produto, unidade, quantidade) -> None:
    """Reserva quantidade para um pedido em andamento (API agregada legada)."""
    quantidade = _quantidade_positiva(quantidade)
    with transaction.atomic():
        estoque = (
            Estoque.objects.select_for_update()
            .filter(produto=produto, unidade=unidade)
            .first()
        )
        if estoque is None or estoque.disponivel < quantidade:
            raise ValidationError("Quantidade indisponível na unidade.")
        Estoque.objects.filter(pk=estoque.pk).update(
            quantidade_bloqueada=F("quantidade_bloqueada") + quantidade
        )


def liberar_reserva(*, produto, unidade, quantidade) -> None:
    """Libera reserva agregada (API legada usada por fluxos sem identidade)."""
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


def dar_baixa_definitiva(
    *, produto, unidade, quantidade, pedido=None, usuario=None, request=None
) -> None:
    """Converte reserva agregada em saída definitiva após pagamento aprovado."""
    quantidade = _quantidade_positiva(quantidade)
    liberar_reserva(produto=produto, unidade=unidade, quantidade=quantidade)
    registrar_movimento(
        produto=produto,
        unidade=unidade,
        tipo=MovimentoEstoque.Tipo.BAIXA_DEFINITIVA,
        delta=-quantidade,
        usuario=usuario,
        motivo=f"Baixa definitiva por pedido {pedido}",
        request=request,
    )
