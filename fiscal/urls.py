from django.urls import path

from . import views

app_name = "fiscal"

urlpatterns = [
    path(
        "pedidos/<int:pedido_pk>/nota-manual/",
        views.RegistrarNotaManualView.as_view(),
        name="nota_manual",
    ),
    path(
        "notas-entrada/",
        views.NotaEntradaListView.as_view(),
        name="nota_entrada_lista",
    ),
    path(
        "notas-entrada/<int:pk>/registrar/",
        views.RegistrarNotaEntradaView.as_view(),
        name="nota_entrada_registrar",
    ),
    path(
        "relatorios/",
        views.RelatorioFiscalView.as_view(),
        name="relatorio_fiscal",
    ),
]
