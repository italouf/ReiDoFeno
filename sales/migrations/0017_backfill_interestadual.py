"""Preenche UF de entrega e interestadual em pedidos legados."""
from decimal import Decimal

from django.db import migrations


def calcular_uf(uf_origem, uf_destino):
    origem = (uf_origem or "").strip().upper()
    destino = (uf_destino or "").strip().upper()
    interestadual = bool(origem and destino and origem != destino)
    return (
        interestadual,
        Decimal("0.1200") if interestadual else Decimal("0.0000"),
    )


def preencher_interestadual(apps, schema_editor):
    Pedido = apps.get_model("sales", "Pedido")
    Unidade = apps.get_model("core", "Unidade")
    unidades = {
        unidade.pk: unidade.uf
        for unidade in Unidade.objects.all().only("pk", "uf")
    }
    for pedido in Pedido.objects.all().iterator():
        uf_entrega = (pedido.uf_entrega or pedido.uf or "").upper()
        interestadual, aliquota = calcular_uf(
            unidades.get(pedido.unidade_id), uf_entrega
        )
        if (
            pedido.uf_entrega != uf_entrega
            or pedido.interestadual != interestadual
            or pedido.aliquota_icms != aliquota
        ):
            Pedido.objects.filter(pk=pedido.pk).update(
                uf_entrega=uf_entrega,
                interestadual=interestadual,
                aliquota_icms=aliquota,
            )


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0003_unidade_uf"),
        ("sales", "0016_pedido_aliquota_icms_pedido_interestadual_and_more"),
    ]

    operations = [
        migrations.RunPython(preencher_interestadual, migrations.RunPython.noop),
    ]
