from django.urls import path

from . import views

app_name = "catalog"

urlpatterns = [
    path("produtos/", views.ProdutoListView.as_view(), name="produto_lista"),
    path("produtos/novo/", views.ProdutoCreateView.as_view(), name="produto_novo"),
    path(
        "produtos/<int:pk>/editar/",
        views.ProdutoUpdateView.as_view(),
        name="produto_editar",
    ),
    path(
        "categorias/", views.CategoriaListView.as_view(), name="categoria_lista"
    ),
    path(
        "categorias/novo/",
        views.CategoriaCreateView.as_view(),
        name="categoria_novo",
    ),
    path(
        "categorias/<int:pk>/editar/",
        views.CategoriaUpdateView.as_view(),
        name="categoria_editar",
    ),
]
