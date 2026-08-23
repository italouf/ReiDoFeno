"""Serviço transacional de estoque.

Toda alteração de saldo passa por aqui: trava a linha do estoque
(``select_for_update``), valida regras, grava o movimento imutável e
emite aviso de estoque baixo quando o mínimo é alcançado.
"""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from analytics.models import Aviso

from .models import Estoque, MovimentoEstoque


def _validar_quantidade(quantidade, *, permitir_negativo: bool) -> Decimal:
    quantidade = Decimal(quantidade)
    if quantidade == 0:
        raise ValidationError("A quantidade não pode ser zero.")
    if not permitir_negativo and quantidade <= 0:
        raise ValidationError("A quantidade deve ser maior que zero.")
    return quantidade


@transaction.atomic
def registrar_movimento(
    *,
    produto,
    unidade,
    tipo: str,
    quantidade,
    usuario=None,
    motivo: str = "",
    quantidade_minima=None,
) -> MovimentoEstoque:
    """Registra entrada/saída/ajuste em uma unidade e atualiza o saldo.

    Para AJUSTE, ``quantidade`` aceita sinal (+ entra / - sai).
    """
    tipo = MovimentoEstoque.Tipo(tipo)
    quantidade = _validar_quantidade(
        quantidade, permitir_negativo=(tipo == MovimentoEstoque.Tipo.AJUSTE)
    )

    if tipo == tipo.AJUSTE and not motivo.strip():
        raise ValidationError("Ajuste manual exige motivo obrigatório.")

    estoque, _ = Estoque.objects.select_for_update().get_or_create(
        produto=produto,
        unidade=unidade,
        defaults={"quantidade_minima": quantidade_minima or 0},
    )

    if tipo == tipo.ENTRADA:
        novo_saldo = estoque.quantidade + quantidade
        delta = quantidade
    elif tipo == tipo.SAIDA:
        disponivel = estoque.quantidade - estoque.quantidade_bloqueada
        if quantidade > disponivel:
            raise ValidationError(
                "Saída acima do saldo disponível (descontando reserva)."
            )
        novo_saldo = estoque.quantidade - quantidade
        delta = -quantidade
    else:  # AJUSTE (delta com sinal)
        delta = quantidade
        novo_saldo = estoque.quantidade + delta
        if novo_saldo < estoque.quantidade_bloqueada:
            raise ValidationError(
                "Ajuste deixaria o saldo abaixo da quantidade bloqueada."
            )

    estoque.quantidade = novo_saldo
    estoque.save(update_fields=["quantidade"])

    movimento = MovimentoEstoque.objects.create(
        produto=produto,
        unidade=unidade,
        tipo=tipo,
        quantidade=abs(delta),
        motivo=motivo,
        usuario=usuario,
    )

    if tipo == tipo.AJUSTE:
        from core.auditoria import registrar_auditoria

        registrar_auditoria(
            acao="estoque.ajuste_manual",
            instancia=movimento,
            antes={"saldo_anterior": str(estoque.quantidade - delta)},
            depois={"saldo_novo": str(estoque.quantidade), "motivo": motivo},
        )

    _avisar_estoque_baixo(estoque)
    return movimento


@transaction.atomic
def transferir_estoque(
    *, produto, unidade_origem, unidade_destino, quantidade, usuario=None
) -> tuple[MovimentoEstoque, MovimentoEstoque]:
    """Transfere estoque gerando saída na origem e entrada no destino vinculadas."""
    quantidade = _quantidade_positiva(quantidade)

    saida = registrar_movimento(
        produto=produto,
        unidade=unidade_origem,
        tipo=MovimentoEstoque.Tipo.SAIDA,
        quantidade=quantidade,
        usuario=usuario,
        motivo=f"Transferência para {unidade_destino.nome}",
    )
    entrada = registrar_movimento(
        produto=produto,
        unidade=unidade_destino,
        tipo=MovimentoEstoque.Tipo.ENTRADA,
        quantidade=quantidade,
        usuario=usuario,
        motivo=f"Transferência de {unidade_origem.nome}",
    )
    saida.movimento_par = entrada
    saida.save(_permitir_edicao=True)
    entrada.movimento_par = saida
    entrada.save(_permitir_edicao=True)
    return saida, entrada


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


def _quantidade_positiva(quantidade) -> Decimal:
    return _validar_quantidade(quantidade, permitir_negativo=False)


def reservar(*, produto, unidade, quantidade) -> None:
    """Reserva quantidade para um pedido em andamento."""
    from django.db.models import F

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
    """Libera reserva previamente feita para um pedido."""
    from django.db.models import F

    quantidade = _quantidade_positiva(quantidade)
    with transaction.atomic():
        atualizados = (
            Estoque.objects.select_for_update()
            .filter(produto=produto, unidade=unidade)
            .update(
                quantidade_bloqueada=F("quantidade_bloqueada") - quantidade
            )
        )
        if not atualizados:
            return
    # Garante que não ficou negativa (defesa extra além da constraint).
    Estoque.objects.filter(
        produto=produto, unidade=unidade, quantidade_bloqueada__lt=0
    ).update(quantidade_bloqueada=0)


def dar_baixa_definitiva(*, produto, unidade, quantidade, pedido=None, usuario=None) -> None:
    """Converte reserva em saída definitiva após pagamento aprovado."""
    liberar_reserva(produto=produto, unidade=unidade, quantidade=quantidade)
    registrar_movimento(
        produto=produto,
        unidade=unidade,
        tipo=MovimentoEstoque.Tipo.SAIDA,
        quantidade=quantidade,
        usuario=usuario,
        motivo=f"Baixa definitiva por pedido {pedido}",
    )
