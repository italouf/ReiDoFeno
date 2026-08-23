from django.urls import path

from . import views

app_name = "sales"

urlpatterns = [
    path("carrinho/", views.CarrinhoView.as_view(), name="carrinho"),
    path(
        "carrinho/adicionar/",
        views.AdicionarAoCarrinhoView.as_view(),
        name="adicionar",
    ),
    path(
        "carrinho/item/<int:produto_id>/alterar/",
        views.AlterarItemCarrinhoView.as_view(),
        name="alterar_item",
    ),
    path(
        "carrinho/item/<int:produto_id>/remover/",
        views.RemoverItemCarrinhoView.as_view(),
        name="remover_item",
    ),
    path("checkout/", views.CheckoutView.as_view(), name="checkout"),
    path(
        "pedido/<uuid:token>/",
        views.PedidoStatusPublicoView.as_view(),
        name="pedido_token",
    ),
    path(
        "pagamento/<uuid:token>/iniciar/",
        views.PagamentoIniciarView.as_view(),
        name="pagamento_iniciar",
    ),
    path(
        "pagamento/<uuid:token>/simular/",
        views.SimuladorPagamentoView.as_view(),
        name="simular_pagamento",
    ),
    path(
        "pagamento/<uuid:token>/simular/resultado/",
        views.SimularResultadoView.as_view(),
        name="simular_resultado",
    ),
    path("webhook/pagamentos/", views.MercadoPagoWebhookView.as_view(), name="webhook"),
    path("meus-pedidos/", views.MeusPedidosView.as_view(), name="meus_pedidos"),
    path(
        "gestao/minhas-metricas/",
        views.MinhasMetricasView.as_view(),
        name="minhas_metricas",
    ),
    path(
        "gestao/pedidos/",
        views.PedidosInternosListView.as_view(),
        name="pedidos_internos",
    ),
    path(
        "gestao/pedidos/<int:pk>/",
        views.PedidoInternoDetailView.as_view(),
        name="pedido_interno_detail",
    ),
    path(
        "gestao/pedidos/<int:pk>/status/",
        views.PedidoAtualizarStatusView.as_view(),
        name="pedido_atualizar_status",
    ),
]
