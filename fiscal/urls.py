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
        "pedidos/<int:pedido_pk>/nota-anexar/",
        views.AnexarNotaFiscalView.as_view(),
        name="nota_anexar",
    ),
    path(
        "pedidos/<int:pedido_pk>/exportar-iob/",
        views.ExportarIOBPedidoView.as_view(),
        name="exportar_iob",
    ),
    path(
        "notas/",
        views.NotaFiscalListView.as_view(),
        name="nota_lista",
    ),
    path(
        "notas/<int:pk>/autorizar/",
        views.ConfirmarNotaAutorizadaView.as_view(),
        name="nota_autorizar",
    ),
    path(
        "notas/<int:pk>/cancelar/",
        views.CancelarNotaView.as_view(),
        name="nota_cancelar",
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
