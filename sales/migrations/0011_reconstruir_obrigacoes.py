"""Reconstrói obrigações de estoque a partir de evidência atribuível.

Corrige tanto a 0009 recém-aplicada quanto bases que já receberam seus dados
inferidos. Não cria, altera ou remove movimentos; apenas recalcula a obrigação.
"""

from django.db import migrations

from sales.obrigacoes import reconstruir_obrigacao_evidencia


def reconstruir_obrigacoes(apps, schema_editor):
    Obrigacao = apps.get_model("sales", "ObrigacaoEstoquePedido")
    Pedido = apps.get_model("sales", "Pedido")
    Movimento = apps.get_model("stock", "MovimentoEstoque")

    for obrigacao in Obrigacao.objects.all().iterator():
        dados = reconstruir_obrigacao_evidencia(
            obrigacao, Pedido=Pedido, Movimento=Movimento
        )
        obrigacao.quantidade_baixada = dados["quantidade_baixada"]
        obrigacao.evidencia_baixada = dados["evidencia_baixada"]
        obrigacao.evidencia_detalhe = dados["evidencia_detalhe"]
        obrigacao.status = dados["status"]
        obrigacao.motivo_pendencia = dados["motivo_pendencia"]
        update_fields = [
            "quantidade_baixada",
            "evidencia_baixada",
            "evidencia_detalhe",
            "status",
            "motivo_pendencia",
            "atualizado_em",
        ]
        if dados["status"] == "pendente":
            obrigacao.resolvido_em = None
            obrigacao.resolvido_por = None
            update_fields += ["resolvido_em", "resolvido_por"]
        obrigacao.save(update_fields=update_fields)


class Migration(migrations.Migration):

    dependencies = [
        ("sales", "0010_movimento_obrigacao"),
        ("stock", "0009_movimento_obrigacao"),
    ]

    operations = [
        migrations.RunPython(
            reconstruir_obrigacoes, migrations.RunPython.noop
        ),
    ]
