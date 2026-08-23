from django.contrib.auth.models import Group, Permission
from django.core.management import call_command
from django.test import TestCase

from accounts.permissions import GRUPO_ADMINISTRADOR, GRUPOS


class SeedGroupsCommandTest(TestCase):
    def test_cria_todos_os_grupos(self):
        call_command("seed_groups", verbosity=0)

        nomes = set(Group.objects.values_list("name", flat=True))
        self.assertTrue(set(GRUPOS).issubset(nomes))

    def test_administrador_recebe_todas_as_permissoes(self):
        call_command("seed_groups", verbosity=0)

        admin = Group.objects.get(name=GRUPO_ADMINISTRADOR)
        total = Permission.objects.count()
        self.assertGreater(total, 0)
        self.assertEqual(admin.permissions.count(), total)

    def test_execucao_repetida_e_idempotente(self):
        call_command("seed_groups", verbosity=0)
        permissoes_antes = {
            g.name: set(g.permissions.all()) for g in Group.objects.all()
        }

        call_command("seed_groups", verbosity=0)

        for grupo in Group.objects.all():
            self.assertEqual(
                set(grupo.permissions.all()), permissoes_antes[grupo.name]
            )
        self.assertEqual(Group.objects.count(), len(GRUPOS))
