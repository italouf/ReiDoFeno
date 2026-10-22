from django.contrib import admin

from .models import Despesa


@admin.register(Despesa)
class DespesaAdmin(admin.ModelAdmin):
    list_display = (
        "categoria",
        "fornecedor",
        "valor",
        "data",
        "usuario_responsavel",
    )
    list_filter = ("categoria", "recorrencia", "usuario_responsavel")
    search_fields = ("tipo", "fornecedor", "fornecedor_cnpj")
