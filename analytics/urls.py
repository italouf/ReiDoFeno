from django.urls import path

from . import views

app_name = "analytics"

urlpatterns = [
    path("avisos/", views.AvisoListView.as_view(), name="aviso_lista"),
    path(
        "avisos/<int:pk>/ler/",
        views.MarcarAvisoLidoView.as_view(),
        name="aviso_ler",
    ),
    path(
        "relatorios/vendas-por-produto/",
        views.RelatorioVendasProdutoView.as_view(),
        name="relatorio_vendas_produto",
    ),
]
