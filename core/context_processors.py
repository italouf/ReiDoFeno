"""Flags de navegação por grupo, sem esconder a autoridade do servidor."""
from django.urls import reverse


def papeis(request):
    usuario = getattr(request, "user", None)
    if usuario is None or not usuario.is_authenticated:
        return {
            "pode_painel_global": False,
            "pode_fiscal": False,
            "pode_metricas": False,
            "pode_operacao": False,
            "pode_catalogo": False,
            "pode_clientes": False,
            "url_inicio": "/",
        }

    if usuario.is_superuser:
        grupos = {"Administrador"}
    else:
        grupos = set(usuario.groups.values_list("name", flat=True))

    gestao = bool(grupos & {"Administrador", "Gestor"})
    fiscal = bool(
        grupos & {"Administrador", "Gestor", "Emissor Fiscal"}
    )
    metricas = bool(grupos & {"Administrador", "Gestor", "Vendedor"})
    if gestao:
        url_inicio = reverse("core:painel")
    elif fiscal:
        url_inicio = reverse("fiscal:relatorio_fiscal")
    elif metricas:
        url_inicio = reverse("sales:minhas_metricas")
    else:
        url_inicio = "/"

    return {
        "pode_painel_global": gestao,
        "pode_fiscal": fiscal,
        "pode_metricas": metricas,
        "pode_operacao": gestao,
        "pode_catalogo": gestao,
        "pode_clientes": bool(
            grupos & {"Administrador", "Gestor", "Vendedor"}
        ),
        "url_inicio": url_inicio,
    }
