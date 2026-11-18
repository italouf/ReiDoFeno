"""Serviços de autenticação 2FA (TOTP e códigos de backup)."""

import secrets
import string

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django_otp.plugins.otp_static.models import StaticDevice, StaticToken
from django_otp.plugins.otp_totp.models import TOTPDevice

from accounts.permissions import GRUPO_ADMINISTRADOR
from core.auditoria import auditar_atomicamente

_ALFABETO_BACKUP = string.ascii_uppercase + string.digits


def usuario_exige_2fa(usuario) -> bool:
    """Retorna True se o usuário pertence a grupo com 2FA obrigatório."""
    if not usuario or not getattr(usuario, "is_authenticated", False):
        return False
    if getattr(usuario, "is_superuser", False):
        return True
    grupos_obrigatorios = getattr(settings, "OTP_REQUIRED_GROUPS", ())
    if not grupos_obrigatorios:
        return False
    return usuario.groups.filter(name__in=grupos_obrigatorios).exists()


def usuario_tem_2fa_ativo(usuario) -> bool:
    """Retorna True se o usuário possui ao menos um TOTPDevice confirmado."""
    if not usuario or not getattr(usuario, "is_authenticated", False):
        return False
    return TOTPDevice.objects.filter(user=usuario, confirmed=True).exists()


def usuario_verificado_otp(usuario) -> bool:
    """Retorna True se o usuário já concluiu verificação OTP na sessão."""
    verificador = getattr(usuario, "is_verified", None)
    return bool(callable(verificador) and verificador())


def _gerar_codigo_backup() -> str:
    return "".join(secrets.choice(_ALFABETO_BACKUP) for _ in range(8))


@transaction.atomic
def gerar_backup_codes(usuario, quantidade: int = 10) -> list[str]:
    """Substitui o StaticDevice de backup e gera novos códigos de uso único."""
    StaticDevice.objects.filter(user=usuario, name="backup").delete()
    device = StaticDevice.objects.create(user=usuario, name="backup", confirmed=True)
    codigos: list[str] = []
    usados: set[str] = set()
    while len(codigos) < quantidade:
        codigo = _gerar_codigo_backup()
        if codigo in usados:
            continue
        usados.add(codigo)
        StaticToken.objects.create(device=device, token=codigo)
        codigos.append(codigo)
    return codigos


@transaction.atomic
def resetar_2fa_usuario(
    usuario_alvo,
    *,
    ator,
    justificativa: str = "",
    request=None,
) -> None:
    """Permite que outro Administrador remova dispositivos 2FA de um usuário."""
    if not ator or not getattr(ator, "is_authenticated", False) or not ator.is_active:
        raise PermissionDenied("Ator sem permissão para resetar 2FA.")
    eh_admin = ator.is_superuser or ator.groups.filter(
        name=GRUPO_ADMINISTRADOR
    ).exists()
    if not eh_admin:
        raise PermissionDenied(
            "Apenas um Administrador pode resetar o 2FA de outro usuário."
        )
    if ator.pk == usuario_alvo.pk:
        raise ValidationError(
            "Auto-reset de 2FA não é permitido; solicite a outro Administrador."
        )
    motivo = (justificativa or "").strip()
    if not motivo:
        raise ValidationError("Informe a justificativa do reset de 2FA.")

    tinha_totp = TOTPDevice.objects.filter(user=usuario_alvo, confirmed=True).exists()
    TOTPDevice.objects.filter(user=usuario_alvo).delete()
    StaticDevice.objects.filter(user=usuario_alvo).delete()

    auditar_atomicamente(
        acao="accounts.2fa_resetado",
        instancia=usuario_alvo,
        usuario=ator,
        request=request,
        antes={"totp_ativo": tinha_totp},
        depois={"totp_ativo": False, "justificativa": motivo},
    )
