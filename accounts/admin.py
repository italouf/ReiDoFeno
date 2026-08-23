from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Usuario


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
