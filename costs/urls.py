from django.urls import path

from . import views

app_name = "costs"

urlpatterns = [
    path("despesas/", views.DespesaListView.as_view(), name="despesa_lista"),
    path("despesas/novo/", views.DespesaCreateView.as_view(), name="despesa_novo"),
    path(
        "despesas/<int:pk>/editar/",
        views.DespesaUpdateView.as_view(),
        name="despesa_editar",
    ),
]
