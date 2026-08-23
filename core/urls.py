from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("healthz/", views.healthz, name="healthz"),
    path("painel/", views.PainelView.as_view(), name="painel"),
    path("unidades/", views.UnidadeListView.as_view(), name="unidade_lista"),
    path("unidades/novo/", views.UnidadeCreateView.as_view(), name="unidade_novo"),
    path(
        "unidades/<int:pk>/editar/",
        views.UnidadeUpdateView.as_view(),
        name="unidade_editar",
    ),
]
