"""Mixins e decorators de autorização por grupo.

A autorização real é feita por grupos (ver accounts.permissions);
o campo ``perfil`` é apenas exibição.
"""
from functools import wraps

from django.contrib.auth.mixins import AccessMixin
from django.core.exceptions import PermissionDenied

GRUPOS_INTERNOS = ("Administrador", "Gestor", "Vendedor")


class GrupoRequiredMixin(AccessMixin):
    """Exige que o usuário autenticado pertença a um dos grupos informados.

    Superusuários sempre passam. Usuário autenticado sem permissão recebe 403.
    """

    grupos_permitidos: tuple[str, ...] = ()

    def dispatch(self, request, *args, **kwargs):
        usuario = request.user
        if not usuario.is_authenticated:
            return self.handle_no_permission()
        if not self.tem_acesso(usuario):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def tem_acesso(self, usuario) -> bool:
        if usuario.is_superuser:
            return True
        return usuario.groups.filter(name__in=self.grupos_permitidos).exists()


def grupo_required(*nomes_grupos):
    """Decorator equivalente a GrupoRequiredMixin para function-based views."""

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                from django.contrib.auth.views import redirect_to_login

                return redirect_to_login(request.get_full_path())
            if not (
                request.user.is_superuser
                or request.user.groups.filter(name__in=nomes_grupos).exists()
            ):
                raise PermissionDenied
            return view_func(request, *args, **kwargs)

        return _wrapped

    return decorator


def interno_required(view_func=None):
    """Atalho para áreas internas: Administrador, Gestor ou Vendedor."""
    return grupo_required(*GRUPOS_INTERNOS)(view_func)
