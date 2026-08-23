"""E-mails transacionais do fluxo de pedido.

Falhas de envio NUNCA quebram o fluxo do pedido — apenas são registradas.
"""
import logging

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string

from .models import Pedido

logger = logging.getLogger(__name__)


def _enviar(pedido: Pedido, assunto: str, template: str) -> None:
    try:
        corpo = render_to_string(template, {"pedido": pedido})
        send_mail(
            subject=assunto,
            message=corpo,
            from_email=settings.DEFAULT_FROM_EMAIL or None,
            recipient_list=[pedido.contato_email],
            fail_silently=False,
        )
    except Exception:
        logger.exception("Falha ao enviar e-mail '%s' do pedido %s.",
                         assunto, pedido.numero)


def email_pedido_criado(pedido: Pedido) -> None:
    _enviar(
        pedido,
        f"Pedido {pedido.numero} recebido",
        "sales/emails/pedido_criado.txt",
    )


def email_pagamento_aprovado(pedido: Pedido) -> None:
    _enviar(
        pedido,
        f"Pagamento aprovado — pedido {pedido.numero}",
        "sales/emails/pagamento_aprovado.txt",
    )


def email_pedido_cancelado(pedido: Pedido) -> None:
    _enviar(
        pedido,
        f"Pedido {pedido.numero} cancelado",
        "sales/emails/pedido_cancelado.txt",
    )
