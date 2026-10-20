from django.contrib import admin

from .models import LogAuditoria


@admin.register(LogAuditoria)
class LogAuditoriaAdmin(admin.ModelAdmin):
    list_display = (
        "criado_em",
        "acao",
        "usuario",
        "objeto_tipo",
        "objeto_id",
        "ip",
    )
    list_filter = ("acao",)
    search_fields = ("objeto_tipo", "objeto_id", "acao")
    readonly_fields = (
        "usuario",
        "acao",
        "objeto_tipo",
        "objeto_id",
        "antes",
        "depois",
        "ip",
        "criado_em",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
