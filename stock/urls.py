from django.urls import path

from stock.models import MovimentoEstoque

from . import views

app_name = "stock"

urlpatterns = [
    path("estoque/", views.EstoqueListView.as_view(), name="estoque_lista"),
    path(
        "movimentos/",
        views.MovimentoListView.as_view(),
        name="movimento_lista",
    ),
    path(
        f"movimentos/{MovimentoEstoque.Tipo.ENTRADA}/",
        views.MovimentoEntradaSaidaView.as_view(),
        kwargs={"tipo": MovimentoEstoque.Tipo.ENTRADA},
        name="movimento_entrada",
    ),
    path(
        f"movimentos/{MovimentoEstoque.Tipo.SAIDA}/",
        views.MovimentoEntradaSaidaView.as_view(),
        kwargs={"tipo": MovimentoEstoque.Tipo.SAIDA},
        name="movimento_saida",
    ),
    path(
        "movimentos/ajuste/",
        views.MovimentoAjusteView.as_view(),
        name="movimento_ajuste",
    ),
    path(
        "movimentos/transferencia/",
        views.MovimentoTransferenciaView.as_view(),
        name="movimento_transferencia",
    ),
]
