from django.urls import path

from . import views

app_name = "privacy"

urlpatterns = [
    path("privacidade/", views.PoliticaPrivacidadeView.as_view(), name="politica"),
    path("termos/", views.TermosUsoView.as_view(), name="termos"),
    path(
        "minha-privacidade/",
        views.MinhaPrivacidadeView.as_view(),
        name="minha_privacidade",
    ),
    path(
        "minha-privacidade/consentimento/<str:finalidade>/revogar/",
        views.RevogarConsentimentoView.as_view(),
        name="revogar_consentimento",
    ),
    path(
        "minha-privacidade/solicitacao/",
        views.NovaSolicitacaoView.as_view(),
        name="nova_solicitacao",
    ),
]
