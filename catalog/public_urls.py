from django.urls import path

from . import views

app_name = "loja"

urlpatterns = [
    path("", views.CatalogoLojaView.as_view(), name="catalogo"),
    path(
        "produto/<int:pk>/",
        views.ProdutoLojaDetailView.as_view(),
        name="produto",
    ),
]
