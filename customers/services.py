"""Serviços de identidade do cliente.

SEC-02/R4/R5/R10: o checkout nunca vincula ``Cliente.usuario``. O vínculo
só é criado/confirmado por prova de uso único enviada ao e-mail cadastrado
ou por revisão administrativa auditada. O token enviado é opaco e não
contém PII; o banco guarda apenas hashes do nonce e do e-mail.
"""

import hashlib
import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.http import Http404
from django.urls import reverse
from django.utils import timezone

from core.auditoria import registrar_auditoria

from .models import Cliente, VinculoClienteToken, normalizar_documento

logger = logging.getLogger(__name__)

SALT_VINCULO = "reidofeno.cliente.vinculo"
VALIDADE_VINCULO_SEGUNDOS = 60 * 60


def _hash(valor: str) -> str:
    return hashlib.sha256((valor or "").strip().casefold().encode()).hexdigest()


def _email_normalizado(email: str) -> str:
    return (email or "").strip().casefold()


def _revogar_tokens_ativos(*, cliente=None, usuario=None):
    filtro = {
        "usado_em__isnull": True,
        "revogado_em__isnull": True,
    }
    if cliente is not None:
        filtro["cliente"] = cliente
    if usuario is not None:
        filtro["usuario"] = usuario
    VinculoClienteToken.objects.filter(**filtro).update(
        revogado_em=timezone.now()
    )


def solicitar_vinculo_cliente(*, usuario, documento: str, request) -> bool:
    """Envia prova opaca, de uso único, ao e-mail já cadastrado.

    Retorna ``True`` somente quando o e-mail foi disparado. A view responde
    de forma genérica para não revelar a existência do cadastro.
    """
    if not getattr(usuario, "is_authenticated", False) or not usuario.email:
        return False

    documento = normalizar_documento(documento)
    cliente = Cliente.objects.filter(documento=documento).first()
    if cliente is None or not cliente.email:
        return False
    if cliente.vinculo_verificado:
        return False
    if cliente.usuario_id not in (None, usuario.pk):
        return False
    if _email_normalizado(cliente.email) != _email_normalizado(usuario.email):
        return False
    outro_cliente = (
        Cliente.objects.filter(usuario=usuario)
        .exclude(pk=cliente.pk)
        .exists()
    )
    if outro_cliente:
        return False

    _revogar_tokens_ativos(cliente=cliente, usuario=usuario)

    nonce = secrets.token_urlsafe(32)
    VinculoClienteToken.objects.create(
        cliente=cliente,
        usuario=usuario,
        nonce_hash=_hash(nonce),
        email_hash=_hash(cliente.email),
        expira_em=timezone.now() + timedelta(
            seconds=VALIDADE_VINCULO_SEGUNDOS
        ),
    )
    assinado = signing.dumps({"nonce": nonce}, salt=SALT_VINCULO)
    caminho = reverse(
        "accounts:confirmar_vinculo_cliente", args=[assinado]
    )
    url = request.build_absolute_uri(caminho)
    send_mail(
        subject="Confirme o vínculo da sua conta — Rei do Feno",
        message=(
            "Recebemos uma solicitação para vincular este e-mail ao cadastro "
            "de cliente da Rei do Feno.\n\n"
            f"Para confirmar, acesse: {url}\n\n"
            f"O link expira em {VALIDADE_VINCULO_SEGUNDOS // 60} minutos e "
            "só pode ser usado uma vez. Se você não fez esta solicitação, "
            "ignore esta mensagem."
        ),
        from_email=settings.DEFAULT_FROM_EMAIL or None,
        recipient_list=[cliente.email],
    )
    logger.info("Prova de vínculo emitida para cliente=%s", cliente.pk)
    return True


@transaction.atomic
def obter_token_vinculo(token: str, usuario):
    """Valida a prova e retorna o registro; não consome."""
    try:
        dados = signing.loads(
            token,
            salt=SALT_VINCULO,
            max_age=VALIDADE_VINCULO_SEGUNDOS,
        )
    except signing.BadSignature as erro:
        raise Http404 from erro

    nonce = str(dados.get("nonce") or "")
    if not nonce:
        raise Http404
    prova = (
        VinculoClienteToken.objects.select_for_update()
        .select_related("cliente", "usuario")
        .filter(nonce_hash=_hash(nonce))
        .first()
    )
    if prova is None or not prova.ativo:
        raise Http404
    if prova.usuario_id != usuario.pk:
        raise PermissionDenied("Esta prova não pertence ao usuário autenticado.")

    cliente = prova.cliente
    email_atual = _email_normalizado(cliente.email)
    if (
        _hash(email_atual) != prova.email_hash
        or _hash(usuario.email) != prova.email_hash
    ):
        prova.revogado_em = timezone.now()
        prova.save(update_fields=["revogado_em"])
        raise PermissionDenied(
            "O e-mail do cadastro mudou; solicite uma nova prova."
        )

    if cliente.usuario_id not in (None, usuario.pk):
        raise PermissionDenied("Este cadastro já está vinculado.")
    outro_cliente = (
        Cliente.objects.filter(usuario=usuario)
        .exclude(pk=cliente.pk)
        .exists()
    )
    if outro_cliente:
        raise PermissionDenied("Este usuário já possui um cadastro vinculado.")
    return prova


@transaction.atomic
def confirmar_vinculo_cliente(*, token: str, usuario, request):
    """Consome a prova e cria o vínculo em transação auditada."""
    prova = obter_token_vinculo(token, usuario)
    cliente = prova.cliente
    antes = {
        "usuario_id": cliente.usuario_id,
        "vinculo_verificado": cliente.vinculo_verificado,
    }
    cliente.usuario = usuario
    cliente.vinculo_verificado = True
    cliente.save(update_fields=["usuario", "vinculo_verificado"])
    prova.usado_em = timezone.now()
    prova.save(update_fields=["usado_em"])
    _revogar_tokens_ativos(cliente=cliente, usuario=usuario)

    from sales.models import Pedido

    pedidos_marcados = Pedido.objects.filter(
        cliente=cliente, usuario_criador=usuario
    ).update(identidade_verificada=True)

    registrar_auditoria(
        acao="cliente.vinculo_confirmado",
        instancia=cliente,
        request=request,
        antes=antes,
        depois={
            "usuario_id": usuario.pk,
            "vinculo_verificado": True,
            "origem": "email",
            "pedidos_marcados": pedidos_marcados,
        },
    )
    return cliente


@transaction.atomic
def revisar_vinculo_cliente(
    *, cliente: Cliente, verificado: bool, justificativa: str, request
) -> Cliente:
    """Revisão administrativa explícita com justificativa e auditoria."""
    if not justificativa.strip():
        raise ValidationError("Justificativa é obrigatória.")
    cliente = Cliente.objects.select_for_update().get(pk=cliente.pk)
    antes = {
        "usuario_id": cliente.usuario_id,
        "vinculo_verificado": cliente.vinculo_verificado,
    }
    if verificado and cliente.usuario_id is None:
        raise ValidationError("Não há usuário vinculado para verificar.")
    cliente.vinculo_verificado = verificado
    if not verificado:
        cliente.usuario = None
    cliente.save(update_fields=["usuario", "vinculo_verificado"])
    if not verificado:
        _revogar_tokens_ativos(cliente=cliente)
    from sales.models import Pedido

    if verificado and cliente.usuario_id:
        pedidos_marcados = Pedido.objects.filter(
            cliente=cliente, usuario_criador_id=cliente.usuario_id
        ).update(identidade_verificada=True)
    elif not verificado:
        pedidos_marcados = Pedido.objects.filter(cliente=cliente).update(
            identidade_verificada=False
        )
    else:
        pedidos_marcados = 0
    registrar_auditoria(
        acao="cliente.vinculo_revisado_admin",
        instancia=cliente,
        request=request,
        antes=antes,
        depois={
            "usuario_id": cliente.usuario_id,
            "vinculo_verificado": cliente.vinculo_verificado,
            "justificativa": justificativa.strip()[:500],
            "origem": "admin",
            "pedidos_ajustados": pedidos_marcados,
        },
    )
    return cliente
