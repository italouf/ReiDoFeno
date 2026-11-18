"""Middleware de enforcement de 2FA para perfis internos."""

from urllib.parse import urlencode

from django.shortcuts import redirect

from .services import (
    usuario_exige_2fa,
    usuario_tem_2fa_ativo,
    usuario_verificado_otp,
)


class OTPRequiredMiddleware:
    """Exige verificação OTP na sessão para usuários dos grupos obrigatórios."""

    PREFIXOS_ISENTOS = (
        "/accounts/2fa/",
        "/accounts/logout/",
        "/static/",
        "/healthz/",
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        usuario = getattr(request, "user", None)
        if (
            usuario is not None
            and usuario.is_authenticated
            and usuario_exige_2fa(usuario)
            and not usuario_verificado_otp(usuario)
            and not any(
                request.path.startswith(prefixo) for prefixo in self.PREFIXOS_ISENTOS
            )
        ):
            destino = (
                "/accounts/2fa/verify/"
                if usuario_tem_2fa_ativo(usuario)
                else "/accounts/2fa/setup/"
            )
            if request.path not in ("/", "/accounts/pos-login/"):
                destino = f"{destino}?{urlencode({'next': request.get_full_path()})}"
            return redirect(destino)
        return self.get_response(request)
