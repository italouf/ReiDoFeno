from django.conf import settings
from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views.generic import FormView, View

from core.rate_limit import limitar_com_429
from customers.services import (
    confirmar_vinculo_cliente,
    obter_token_vinculo,
    solicitar_vinculo_cliente,
)

from .forms import LoginForm, VinculoClienteForm


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
