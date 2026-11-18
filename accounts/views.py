import base64
from io import BytesIO

import qrcode
import qrcode.image.svg
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.generic import FormView, TemplateView, View
from django_otp import login as otp_login
from django_otp.plugins.otp_static.models import StaticDevice
from django_otp.plugins.otp_totp.models import TOTPDevice

from accounts.models import Usuario
from accounts.permissions import GRUPO_ADMINISTRADOR
from core.auditoria import auditar_atomicamente
from core.mixins import GrupoRequiredMixin
from core.rate_limit import limitar_com_429
from customers.services import (
    confirmar_vinculo_cliente,
    obter_token_vinculo,
    solicitar_vinculo_cliente,
)

from .forms import LoginForm, TwoFactorVerifyForm, VinculoClienteForm
from .services import (
    gerar_backup_codes,
    resetar_2fa_usuario,
    usuario_exige_2fa,
    usuario_tem_2fa_ativo,
    usuario_verificado_otp,
)


def _destino_seguro(request, fallback: str) -> str:
    proximo = request.POST.get("next") or request.GET.get("next") or ""
    if proximo and url_has_allowed_host_and_scheme(
        proximo,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return proximo
    return fallback


@method_decorator(
    limitar_com_429(
        key="ip",
        rate=settings.RATELIMIT_LOGIN,
        retry_after=60,
    ),
    name="dispatch",
)
class LoginView(auth_views.LoginView):
    form_class = LoginForm
    template_name = "registration/login.html"
    redirect_authenticated_user = True

    def get_success_url(self):
        usuario = self.request.user
        if (
            usuario.is_authenticated
            and usuario_exige_2fa(usuario)
            and not usuario_verificado_otp(usuario)
        ):
            if usuario_tem_2fa_ativo(usuario):
                return reverse("accounts:2fa_verify")
            return reverse("accounts:2fa_setup")
        return super().get_success_url()


class PosLoginView(LoginRequiredMixin, View):
    """Landing por papel, evitando mandar perfis para uma rota 403."""

    def get(self, request):
        usuario = request.user
        grupos = set(usuario.groups.values_list("name", flat=True))
        if usuario.is_superuser or grupos & {"Administrador", "Gestor"}:
            return redirect("core:painel")
        if "Financeiro" in grupos:
            return redirect("sales:conciliacao_list")
        if "Emissor Fiscal" in grupos:
            return redirect("fiscal:relatorio_fiscal")
        if "Vendedor" in grupos:
            return redirect("sales:minhas_metricas")
        return redirect("/")


class TwoFactorSetupView(LoginRequiredMixin, TemplateView):
    """Configuração inicial de 2FA TOTP com QR code e códigos de backup."""

    template_name = "accounts/2fa_setup.html"

    def _obter_dispositivo_pendente(self, usuario):
        device, _ = TOTPDevice.objects.get_or_create(
            user=usuario,
            confirmed=False,
            defaults={"name": "default"},
        )
        return device

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        usuario = self.request.user
        if usuario_tem_2fa_ativo(usuario) and usuario_verificado_otp(usuario):
            context["already_configured"] = True
            return context

        if usuario_tem_2fa_ativo(usuario):
            context["already_configured"] = True
            context["needs_verification"] = True
            return context

        device = self._obter_dispositivo_pendente(usuario)
        img = qrcode.make(
            device.config_url, image_factory=qrcode.image.svg.SvgPathImage
        )
        buffer = BytesIO()
        img.save(buffer)
        context["qr_code_svg"] = base64.b64encode(buffer.getvalue()).decode()
        context["secret_key"] = base64.b32encode(device.bin_key).decode()
        context["next_url"] = _destino_seguro(
            self.request, reverse("accounts:pos_login")
        )
        return context

    def post(self, request, *args, **kwargs):
        usuario = request.user
        if usuario_tem_2fa_ativo(usuario):
            return redirect("accounts:2fa_verify")

        token = (request.POST.get("otp_token") or "").strip().replace(" ", "")
        device = self._obter_dispositivo_pendente(usuario)
        if token and device.verify_token(token):
            with transaction.atomic():
                device.confirmed = True
                device.save(update_fields=["confirmed"])
                backup_codes = gerar_backup_codes(usuario)
                auditar_atomicamente(
                    acao="accounts.2fa_ativado",
                    instancia=usuario,
                    usuario=usuario,
                    request=request,
                    depois={"totp_ativo": True},
                )
            otp_login(request, device)
            return render(
                request,
                "accounts/2fa_backup_codes.html",
                {
                    "backup_codes": backup_codes,
                    "next_url": _destino_seguro(
                        request, reverse("accounts:pos_login")
                    ),
                },
            )

        messages.error(request, "Código inválido. Tente novamente.")
        return self.get(request, *args, **kwargs)


@method_decorator(
    limitar_com_429(
        key="user",
        rate="10/m",
        retry_after=60,
    ),
    name="dispatch",
)
class TwoFactorVerifyView(LoginRequiredMixin, FormView):
    """Verificação de token TOTP ou código de backup após login primário."""

    template_name = "accounts/2fa_verify.html"
    form_class = TwoFactorVerifyForm

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            if usuario_verificado_otp(request.user):
                return redirect(
                    _destino_seguro(request, reverse("accounts:pos_login"))
                )
            if not usuario_tem_2fa_ativo(request.user):
                return redirect("accounts:2fa_setup")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["next_url"] = _destino_seguro(
            self.request, reverse("accounts:pos_login")
        )
        return context

    def form_valid(self, form):
        usuario = self.request.user
        token = form.cleaned_data["otp_token"]
        use_backup = form.cleaned_data["use_backup"]

        dispositivo_valido = None
        if use_backup:
            for device in StaticDevice.objects.filter(
                user=usuario, confirmed=True
            ):
                if device.verify_token(token):
                    dispositivo_valido = device
                    break
        else:
            for device in TOTPDevice.objects.filter(
                user=usuario, confirmed=True
            ):
                if device.verify_token(token):
                    dispositivo_valido = device
                    break

        if dispositivo_valido is not None:
            otp_login(self.request, dispositivo_valido)
            return redirect(
                _destino_seguro(self.request, reverse("accounts:pos_login"))
            )

        form.add_error(
            "otp_token",
            "Token recusado: código inválido. Tente novamente.",
        )
        return self.form_invalid(form)


class TwoFactorResetView(LoginRequiredMixin, GrupoRequiredMixin, View):
    """Permite que outro Administrador resete o 2FA de um usuário."""

    grupos_permitidos = (GRUPO_ADMINISTRADOR,)

    def post(self, request, user_id):
        usuario_alvo = get_object_or_404(Usuario, pk=user_id)
        justificativa = request.POST.get("justificativa", "")
        try:
            resetar_2fa_usuario(
                usuario_alvo,
                ator=request.user,
                justificativa=justificativa,
                request=request,
            )
        except PermissionDenied:
            raise
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
            return redirect("core:painel")

        messages.success(
            request, f"2FA de {usuario_alvo.username} resetado com sucesso."
        )
        return redirect("core:painel")


@method_decorator(
    limitar_com_429(
        key="user",
        rate=settings.RATELIMIT_VINCULO_EMISSAO,
        retry_after=3600,
    ),
    name="dispatch",
)
class VincularClienteView(LoginRequiredMixin, FormView):
    """Solicita o link de comprovação de vínculo ao e-mail já cadastrado."""

    form_class = VinculoClienteForm
    template_name = "registration/vincular_cliente.html"

    def get_success_url(self):
        return reverse("sales:meus_pedidos")

    def form_valid(self, form):
        solicitar_vinculo_cliente(
            usuario=self.request.user,
            documento=form.cleaned_data["documento"],
            request=self.request,
        )
        messages.info(
            self.request,
            "Se os dados conferirem com um cadastro ainda não vinculado, "
            "enviaremos um link de confirmação para o e-mail cadastrado.",
        )
        return redirect(self.get_success_url())


@method_decorator(
    limitar_com_429(
        key="ip",
        rate=settings.RATELIMIT_VINCULO_CONSUMO,
        retry_after=3600,
    ),
    name="dispatch",
)
class ConfirmarVinculoClienteView(LoginRequiredMixin, View):
    """GET apresenta a confirmação; POST consome a prova de uso único."""

    template_name = "registration/confirmar_vinculo.html"

    def get(self, request, token):
        prova = obter_token_vinculo(token, request.user)
        return render(
            request,
            self.template_name,
            {"token": token, "prova": prova},
        )

    def post(self, request, token):
        confirmar_vinculo_cliente(
            token=token,
            usuario=request.user,
            request=request,
        )
        messages.success(request, "Cadastro vinculado à sua conta.")
        return redirect("sales:meus_pedidos")
