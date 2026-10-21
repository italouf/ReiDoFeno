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
    BloqueioLegado,
    Estoque,
    MovimentoEstoque,
    ReservaEstoque,
)

__all__ = [
    "ImutabilidadeViolation",
    "baixar_saldo_livre",
    "consumir_reserva",
    "liberar_reserva",
    "registrar_ajuste",
    "registrar_movimento",
    "reservar",
    "resolver_bloqueio_legado",
    "saldo_comprometido",
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
        numero = Decimal(str(valor))
    except (InvalidOperation, TypeError, ValueError) as erro:
        raise ValidationError(f"{campo} deve ser um número decimal.") from erro
    if not numero.is_finite():
        raise ValidationError(f"{campo} deve ser um número finito.")
    return numero


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
    obrigacao=None,
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
    if obrigacao is not None and (
        obrigacao.produto_id != produto.pk
        or obrigacao.unidade_id != unidade.pk
    ):
        raise ValidationError(
            "Movimento e obrigação de estoque divergem em produto/unidade."
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
        obrigacao=obrigacao,
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

    # Ordem global de locks por unidade evita deadlock A→B/B→A.
    for unidade_id in sorted({unidade_origem.pk, unidade_destino.pk}):
        Estoque.objects.select_for_update().get_or_create(
            produto=produto,
            unidade_id=unidade_id,
            defaults={"quantidade_minima": 0},
        )

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


STATUS_RESERVAVEIS = frozenset(
    {"rascunho", "aguardando_pagamento", "pagamento_pendente"}
)


def _quantidade_devida(pedido_id, produto_id) -> Decimal:
    """Soma dos itens do pedido para o produto (fonte da reserva)."""
    from sales.models import ItemPedido

    total = ItemPedido.objects.filter(
        pedido_id=pedido_id, produto_id=produto_id
    ).aggregate(total=Sum("quantidade"))["total"]
    return total or Decimal("0.00")


@transaction.atomic
def reservar(
    *, produto, unidade, quantidade, pedido=None, item_pedido=None
) -> ReservaEstoque:
    """Cria reserva identificada pelo pedido, validando o contrato do item."""
    from sales.models import Pedido

    quantidade = _quantidade_positiva(quantidade)
    if pedido is None:
        raise ValidationError(
            "Reserva de estoque exige pedido identificado; "
            "reservas órfãs não são permitidas."
        )
    if item_pedido is None:
        raise ValidationError("Reserva de estoque exige item do pedido.")

    pedido = Pedido.objects.select_for_update().get(pk=pedido.pk)
    if pedido.status not in STATUS_RESERVAVEIS:
        raise ValidationError(
            f"Pedido em '{pedido.status}' não pode receber reserva."
        )
    if pedido.status_financeiro != Pedido.StatusFinanceiro.PENDENTE:
        raise ValidationError(
            "Pedido com financeiro não pendente não pode receber reserva."
        )
    if unidade.pk != pedido.unidade_id:
        raise ValidationError("Unidade da reserva difere da unidade do pedido.")
    if item_pedido.pedido_id != pedido.pk:
        raise ValidationError("Item do pedido não pertence ao pedido informado.")
    if item_pedido.produto_id != produto.pk:
        raise ValidationError("Produto da reserva difere do produto do item.")

    devido = _quantidade_devida(pedido.pk, produto.pk)
    from sales.models import ObrigacaoEstoquePedido

    obrigacao = ObrigacaoEstoquePedido.objects.filter(
        pedido=pedido, produto=produto, unidade=unidade
    ).first()
    if obrigacao is not None:
        devido = obrigacao.quantidade_devida
    ja_consumido = ReservaEstoque.objects.filter(
        pedido_id=pedido.pk,
        produto_id=produto.pk,
        unidade_id=unidade.pk,
        status=ReservaEstoque.Status.CONSUMIDA,
    ).aggregate(total=Sum("quantidade"))["total"] or Decimal("0.00")
    if obrigacao is not None:
        ja_consumido = max(ja_consumido, obrigacao.quantidade_baixada)
    devido_restante = devido - ja_consumido
    if devido_restante <= 0:
        raise ValidationError(
            "A obrigação de estoque deste produto já foi consumida."
        )
    if devido_restante != quantidade:
        raise ValidationError(
            "Quantidade da reserva difere da obrigação restante do pedido "
            f"({quantidade} != {devido_restante})."
        )

    existente = (
        ReservaEstoque.objects.select_for_update()
        .filter(
            pedido=pedido,
            produto=produto,
            unidade=unidade,
            status=ReservaEstoque.Status.ATIVA,
        )
        .first()
    )
    if existente is not None:
        if existente.quantidade == quantidade:
            return existente
        raise ValidationError(
            "Já existe reserva ativa com quantidade divergente."
        )

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


def _travar_reserva(queryset):
    from django.db import connection

    if connection.features.has_select_for_update_of:
        return queryset.select_for_update(of=("self",))
    return queryset.select_for_update()


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
    reserva = _travar_reserva(
        ReservaEstoque.objects.select_related("pedido")
    ).get(pk=reserva.pk)
    if reserva.status != ReservaEstoque.Status.ATIVA:
        _sincronizar_reserva(original, reserva)
        return reserva

    if reserva.unidade_id != reserva.pedido.unidade_id:
        raise ValidationError(
            "Reserva inconsistente: unidade difere da unidade do pedido."
        )
    devido = _quantidade_devida(reserva.pedido_id, reserva.produto_id)
    ja_consumido = ReservaEstoque.objects.filter(
        pedido_id=reserva.pedido_id,
        produto_id=reserva.produto_id,
        unidade_id=reserva.unidade_id,
        status=ReservaEstoque.Status.CONSUMIDA,
    ).aggregate(total=Sum("quantidade"))["total"] or Decimal("0.00")
    if ja_consumido + reserva.quantidade > devido:
        raise ValidationError(
            "Reserva excede a quantidade devida do pedido; "
            "baixa cancelada para revisão."
        )

    estoque = _estoque_bloqueado(reserva.produto, reserva.unidade)
    _desbloquear(estoque, reserva.quantidade)

    from sales.services import obter_obrigacao, registrar_baixa_obrigacao

    obrigacao = obter_obrigacao(
        reserva.pedido, reserva.produto, reserva.unidade
    )
    movimento = registrar_movimento(
        produto=reserva.produto,
        unidade=reserva.unidade,
        tipo=MovimentoEstoque.Tipo.BAIXA_DEFINITIVA,
        delta=-reserva.quantidade,
        motivo=f"Consumo da reserva do pedido {reserva.pedido.numero}",
        usuario=usuario,
        request=request,
        obrigacao=obrigacao,
    )
    registrar_baixa_obrigacao(
        reserva.pedido,
        produto=reserva.produto,
        unidade=reserva.unidade,
        quantidade=reserva.quantidade,
        usuario=usuario,
        movimento=movimento,
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


@transaction.atomic
def resolver_bloqueio_legado(
    bloqueio: BloqueioLegado,
    *,
    usuario=None,
    justificativa: str,
    request=None,
) -> BloqueioLegado:
    """Resolve manualmente um bloqueio em quarentena, com cobertura provada."""
    if not justificativa.strip():
        raise ValidationError("Justificativa é obrigatória.")
    bloqueio = BloqueioLegado.objects.select_for_update().get(pk=bloqueio.pk)
    if not bloqueio.ativo:
        return bloqueio
    estoque = _estoque_bloqueado(bloqueio.produto, bloqueio.unidade)
    outros = saldo_comprometido(
        bloqueio.produto, bloqueio.unidade
    ) - bloqueio.quantidade
    if estoque.quantidade_bloqueada - bloqueio.quantidade < outros:
        raise ValidationError(
            "Reconciliação recusada: o bloqueio agregado não cobre as "
            "reservas e demais bloqueios ativos."
        )
    _desbloquear(estoque, bloqueio.quantidade)
    bloqueio.resolvido_em = timezone.now()
    bloqueio.resolvido_por = usuario
    bloqueio.observacao_resolucao = justificativa.strip()[:1000]
    bloqueio.save(
        update_fields=[
            "resolvido_em",
            "resolvido_por",
            "observacao_resolucao",
        ]
    )
    from core.auditoria import registrar_auditoria

    registrar_auditoria(
        acao="estoque.bloqueio_legado_resolvido",
        instancia=bloqueio,
        request=request,
        usuario=usuario,
        antes={"quantidade_bloqueada": str(estoque.quantidade_bloqueada)},
        depois={
            "quantidade_bloqueada": str(
                estoque.quantidade_bloqueada - bloqueio.quantidade
            ),
            "quantidade_resolvida": str(bloqueio.quantidade),
            "justificativa": justificativa.strip()[:500],
        },
    )
    return bloqueio


def saldo_comprometido(produto, unidade) -> Decimal:
    """Soma reservas ativas + bloqueios legados ativos."""
    reservas = ReservaEstoque.objects.filter(
        produto=produto,
        unidade=unidade,
        status=ReservaEstoque.Status.ATIVA,
    ).aggregate(total=Sum("quantidade"))["total"] or Decimal("0.00")
    legados = BloqueioLegado.objects.filter(
        produto=produto,
        unidade=unidade,
        resolvido_em__isnull=True,
    ).aggregate(total=Sum("quantidade"))["total"] or Decimal("0.00")
    return reservas + legados


@transaction.atomic
def baixar_saldo_livre(
    *, produto, unidade, quantidade, pedido=None, usuario=None, request=None
) -> None:
    """Baixa apenas saldo livre; nunca reduz bloqueio de terceiros."""
    quantidade = _quantidade_positiva(quantidade)
    estoque = (
        Estoque.objects.select_for_update()
        .filter(produto=produto, unidade=unidade)
        .first()
    )
    if estoque is None:
        raise ValidationError("Estoque inexistente para baixa.")
    livre = estoque.quantidade - estoque.quantidade_bloqueada
    if livre < quantidade:
        raise ValidationError(
            "Saldo livre insuficiente para baixa; "
            "o bloqueio de terceiros não será alterado."
        )
    obrigacao = None
    if pedido is not None and hasattr(pedido, "pk"):
        from sales.services import obter_obrigacao

        obrigacao = obter_obrigacao(pedido, produto, unidade)
    movimento = registrar_movimento(
        produto=produto,
        unidade=unidade,
        tipo=MovimentoEstoque.Tipo.BAIXA_DEFINITIVA,
        delta=-quantidade,
        usuario=usuario,
        motivo=f"Baixa definitiva por pedido {pedido}",
        request=request,
        obrigacao=obrigacao,
    )
    if obrigacao is not None:
        from sales.services import registrar_baixa_obrigacao

        registrar_baixa_obrigacao(
            pedido,
            produto=produto,
            unidade=unidade,
            quantidade=quantidade,
            usuario=usuario,
            movimento=movimento,
        )
