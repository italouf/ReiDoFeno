"""Semeia grupos e permissões de forma idempotente."""
from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand

from accounts.permissions import (
    GRUPO_ADMINISTRADOR,
    GRUPOS,
    PERMISSOES_POR_GRUPO,
)


class Command(BaseCommand):
    help = "Cria os grupos do sistema e atribui as permissões declaradas."

    def handle(self, *args, **options):
        avisos = []
        criados = 0

        for nome in GRUPOS:
            grupo, criado = Group.objects.get_or_create(name=nome)
            criados += int(criado)

            if nome == GRUPO_ADMINISTRADOR:
                permissoes = list(Permission.objects.all())
            else:
                permissoes, pendentes = self._resolver(
                    PERMISSOES_POR_GRUPO.get(nome, [])
                )
                avisos.extend(f"{nome}: {nk}" for nk in pendentes)

            grupo.permissions.set(permissoes)
            self.stdout.write(f"Grupo '{nome}': {len(permissoes)} permissões.")

        for aviso in avisos:
            self.stdout.write(
                self.style.WARNING(
                    f"Permissão ausente ({aviso}); aplicada quando o modelo existir."
                )
            )

        resumo = "Grupos semeados com sucesso." if not criados else f"{criados} grupo(s) criado(s)."
        self.stdout.write(self.style.SUCCESS(resumo))

    def _resolver(self, natural_keys):
        encontradas, pendentes = [], []
        for natural_key in natural_keys:
            app_label, codename = natural_key.split(".", 1)
            permissao = Permission.objects.filter(
                content_type__app_label=app_label, codename=codename
            ).first()
            (encontradas.append if permissao else pendentes.append)(permissao or natural_key)
        return encontradas, pendentes
