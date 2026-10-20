"""Serviços de identidade do cliente.

SEC-02: o vínculo entre ``Cliente`` e ``Usuario`` nunca é inferido pelo
documento informado no checkout. Ele só é criado após comprovação de posse
do e-mail cadastrado (link assinado e expirável) ou por ato administrativo
auditado.
"""

import logging

from django.conf import settings
from django.core import signing
from django.core.exceptions import PermissionDenied
from django.core.mail import send_mail
from django.db import transaction
from django.http import Http404
from django.urls import reverse

from core.auditoria import registrar_auditoria

from .models import Cliente, normalizar_documento

logger = logging.getLogger(__name__)

SALT_VINCULO = "reidofeno.cliente.vinculo"
VALIDADE_VINCULO_SEGUNDOS = 60 * 60


def _email_normalizado(email: str) -> str:
    return (email or "").strip().casefold()


def _usuario_ja_vinculado(usuario) -> bool:
    return Cliente.objects.filter(usuario=usuario).exists()


def solicitar_vinculo_cliente(*, usuario, documento: str, request) -> bool:
    """Envia o link de comprovação quando documento e e-mail conferem.

    Retorna ``True`` somente quando o e-mail foi disparado. A view deve
    responder de forma genérica para não revelar a existência do cadastro.
    """
    if not getattr(usuario, "is_authenticated", False) or not usuario.email:
        return False
    if _usuario_ja_vinculado(usuario):
        return False

    documento = normalizar_documento(documento)
    cliente = Cliente.objects.filter(
        documento=documento, usuario__isnull=True
    ).first()
    if cliente is None or not cliente.email:
        return False
    if _email_normalizado(cliente.email) != _email_normalizado(usuario.email):
        return False

    token = signing.dumps(
        {"cliente": cliente.pk, "usuario": usuario.pk},
        salt=SALT_VINCULO,
    )
    caminho = reverse("accounts:confirmar_vinculo_cliente", args=[token])
    url = request.build_absolute_uri(caminho)
    send_mail(
        subject="Confirme o vínculo da sua conta — Rei do Feno",
        message=(
            "Recebemos uma solicitação para vincular este e-mail ao cadastro "
            "de cliente da Rei do Feno.\n\n"
            f"Para confirmar, acesse: {url}\n\n"
            f"O link expira em {VALIDADE_VINCULO_SEGUNDOS // 60} minutos. "
            "Se você não fez esta solicitação, ignore esta mensagem."
        ),
        from_email=settings.DEFAULT_FROM_EMAIL or None,
        recipient_list=[cliente.email],
    )
    return True


def confirmar_vinculo_cliente(*, token: str, usuario, request) -> Cliente:
    """Confirma o vínculo assinado, de forma atômica e auditada."""
    try:
        dados = signing.loads(
            token,
            salt=SALT_VINCULO,
            max_age=VALIDADE_VINCULO_SEGUNDOS,
        )
    except signing.BadSignature as erro:
        raise Http404 from erro

    if dados.get("usuario") != usuario.pk:
        raise PermissionDenied("Este link não pertence ao usuário autenticado.")

    with transaction.atomic():
        cliente = (
            Cliente.objects.select_for_update()
            .filter(pk=dados.get("cliente"))
            .first()
        )
        if cliente is None:
            raise Http404
        if cliente.usuario_id == usuario.pk:
            return cliente
        if cliente.usuario_id is not None:
            raise PermissionDenied("Este cadastro já está vinculado.")
        if _usuario_ja_vinculado(usuario):
            raise PermissionDenied("Este usuário já possui um cadastro vinculado.")

        antes = {"usuario": None}
        cliente.usuario = usuario
        cliente.save(update_fields=["usuario"])
        registrar_auditoria(
            acao="cliente.vinculo_confirmado",
            instancia=cliente,
            request=request,
            antes=antes,
            depois={"usuario": usuario.pk, "origem": "email"},
        )
    return cliente
