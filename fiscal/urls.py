from django.urls import path

from . import views

app_name = "fiscal"

urlpatterns = [
    path(
        "pedidos/<int:pedido_pk>/nota-manual/",
        views.RegistrarNotaManualView.as_view(),
        name="nota_manual",
    ),
]
