"""Serviço fiscal: elegibilidade, envio ao ERP e reprocessamento."""
import logging

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from analytics.models import Aviso
from customers.validators import DocumentoValidator, _apenas_digitos

from .client import ErroFiscal, obter_client
from .models import NotaFiscal

logger = logging.getLogger(__name__)


def pedido_elegivel(pedido) -> bool:
    """Pedido pago com documento válido do cliente."""
    if pedido.status != "pago":
        return False
    documento = _apenas_digitos(pedido.cliente.documento)
    try:
        DocumentoValidator()(documento)
    except ValidationError:
        return False
    return True


def _aviso_documento_invalido(pedido) -> None:
    Aviso.registrar(
        tipo=Aviso.Tipo.FISCAL_DOCUMENTO,
        mensagem=(
            f"Pedido {pedido.numero} pago com CPF/CNPJ inválido "
            f"({pedido.cliente.nome}); corrija para emitir a NF-e."
        ),
        objeto=pedido,
        severidade=Aviso.Severidade.ERRO,
    )


@transaction.atomic
def enviar_para_emissao(pedido, client=None) -> NotaFiscal | None:
    """Tenta emitir a NF-e do pedido pago; erro gera aviso e permite retry."""
    if pedido.status != "pago":
        return None

    if not pedido_elegivel(pedido):
        _aviso_documento_invalido(pedido)
        return None

    nota, criada = NotaFiscal.objects.get_or_create(pedido=pedido)
    if nota.status == NotaFiscal.Status.AUTORIZADA and not criada:
        return nota  # já emitida: nunca duplica

    client = client or obter_client()
    nota.tentativas += 1
    try:
        resultado = client.criar_nfe(pedido)
    except ErroFiscal as erro:
        nota.status = NotaFiscal.Status.ERRO
        nota.ultimo_erro = str(erro)[:500]
        nota.save()
        Aviso.registrar(
            tipo=Aviso.Tipo.FISCAL_ERRO,
            mensagem=f"Falha ao emitir NF-e do pedido {pedido.numero}: {erro}",
            objeto=nota,
            severidade=Aviso.Severidade.ERRO,
        )
        logger.warning("Falha fiscal no pedido %s: %s", pedido.numero, erro)
        return nota

    nota.status = NotaFiscal.Status.AUTORIZADA
    nota.numero = resultado.get("numero", "")
    nota.chave_acesso = resultado.get("chave", "")
    nota.link_documento = resultado.get("link", "")
    nota.ultimo_erro = ""
    nota.save()
    return nota


def processar_fila_fiscal() -> int:
    """Varre pedidos pagos sem NF-e autorizada e tenta emitir (idempotente)."""
    from sales.models import Pedido

    pedidos = (
        Pedido.objects.filter(status="pago")
        .exclude(nota_fiscal__status=NotaFiscal.Status.AUTORIZADA)
        .select_related("cliente")
    )
    enviados = 0
    for pedido in pedidos:
        resultado = enviar_para_emissao(pedido)
        if resultado is not None and resultado.status == NotaFiscal.Status.AUTORIZADA:
            enviados += 1
    return enviados


def avisar_pagos_sem_nfe(horas_limite: int = 24) -> int:
    """Avisa sobre pedidos pagos há mais de X horas sem NF-e autorizada."""
    from datetime import timedelta

    limite = timezone.now() - timedelta(hours=horas_limite)
    from sales.models import Pedido

    pendentes = Pedido.objects.filter(
        status="pago",
        atualizado_em__lt=limite,
    ).exclude(nota_fiscal__status=NotaFiscal.Status.AUTORIZADA)
    total = 0
    for pedido in pendentes.select_related("cliente"):
        Aviso.registrar(
            tipo=Aviso.Tipo.PAGO_SEM_NFE,
            mensagem=(
                f"Pedido {pedido.numero} segue pago sem NF-e emitida."
            ),
            objeto=pedido,
        )
        total += 1
    return total
