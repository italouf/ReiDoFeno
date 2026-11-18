from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin
from django.core.exceptions import PermissionDenied, ValidationError

from .models import Usuario
from .services import resetar_2fa_usuario


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    list_display = ("username", "email", "first_name", "perfil", "is_active")
    list_filter = UserAdmin.list_filter + ("perfil",)
    fieldsets = UserAdmin.fieldsets + (
        ("Dados adicionais", {"fields": ("telefone", "perfil")}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("Dados adicionais", {"fields": ("telefone", "perfil")}),
    )
    actions = ("acao_resetar_2fa",)

    @admin.action(description="Resetar 2FA (TOTP e códigos de backup) dos selecionados")
    def acao_resetar_2fa(self, request, queryset):
        resetados = 0
        for usuario_alvo in queryset:
            try:
                resetar_2fa_usuario(
                    usuario_alvo,
                    ator=request.user,
                    justificativa="Reset administrativo via Django Admin",
                    request=request,
                )
                resetados += 1
            except (PermissionDenied, ValidationError) as exc:
                self.message_user(
                    request,
                    f"Não foi possível resetar {usuario_alvo.username}: {exc}",
                    level=messages.WARNING,
                )
        if resetados:
            self.message_user(
                request,
                f"2FA resetado para {resetados} usuário(s).",
                level=messages.SUCCESS,
            )
