from django.urls import path

from . import views

app_name = "customers"

urlpatterns = [
    path("clientes/", views.ClienteListView.as_view(), name="cliente_lista"),
    path("clientes/novo/", views.ClienteCreateView.as_view(), name="cliente_novo"),
    path("clientes/<int:pk>/", views.ClienteDetailView.as_view(), name="cliente_detalhe"),
    path(
        "clientes/<int:pk>/editar/",
        views.ClienteUpdateView.as_view(),
        name="cliente_editar",
    ),
    path(
        "clientes/<int:cliente_pk>/interacoes/novo/",
        views.RegistrarInteracaoView.as_view(),
        name="interacao_novo",
    ),
]
