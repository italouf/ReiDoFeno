"""Cria o grupo Emissor Fiscal e atribui ao usuário Caio, se existir."""
from django.db import migrations


def criar_grupo_emissor_fiscal(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Usuario = apps.get_model("accounts", "Usuario")

    grupo, _ = Group.objects.get_or_create(name="Emissor Fiscal")
    for usuario in Usuario.objects.filter(username__iexact="caio"):
        usuario.groups.add(grupo)


def remover_grupo_emissor_fiscal(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name="Emissor Fiscal").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0001_initial"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("fiscal", "0002_notafiscal_cfop_notafiscal_chave_referenciada_and_more"),
    ]

    operations = [
        migrations.RunPython(
            criar_grupo_emissor_fiscal,
            remover_grupo_emissor_fiscal,
        ),
    ]
