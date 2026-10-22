from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from .views import (
    ConfirmarVinculoClienteView,
    LoginView,
    PosLoginView,
    VincularClienteView,
)

app_name = "accounts"

urlpatterns = [
    path("login/", LoginView.as_view(), name="login"),
    path("pos-login/", PosLoginView.as_view(), name="pos_login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path(
        "vincular-cliente/",
        VincularClienteView.as_view(),
        name="vincular_cliente",
    ),
    path(
        "vincular-cliente/confirmar/<str:token>/",
        ConfirmarVinculoClienteView.as_view(),
        name="confirmar_vinculo_cliente",
    ),
    path(
        "senha/recuperar/",
        auth_views.PasswordResetView.as_view(
            success_url=reverse_lazy("accounts:password_reset_done"),
        ),
        name="password_reset",
    ),
    path(
        "senha/recuperar/enviada/",
        auth_views.PasswordResetDoneView.as_view(),
        name="password_reset_done",
    ),
    path(
        "senha/redefinir/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            success_url=reverse_lazy("accounts:password_reset_complete"),
        ),
        name="password_reset_confirm",
    ),
    path(
        "senha/redefinir/concluida/",
        auth_views.PasswordResetCompleteView.as_view(),
        name="password_reset_complete",
    ),
]
