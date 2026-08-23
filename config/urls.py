from django.contrib import admin
from django.urls import include, path

from core.views import healthz

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),
    path("healthz/", healthz),
    path("", include("catalog.public_urls")),
    path("", include("sales.urls")),
    path("painel/", include("core.urls")),
    path("catalogo/", include("catalog.urls")),
    path("", include("customers.urls")),
    path("estoque/", include("stock.urls")),
    path("custos/", include("costs.urls")),
    path("fiscal/", include("fiscal.urls")),
    path("gestao/", include("analytics.urls")),
    path("", include("privacy.urls")),
]
