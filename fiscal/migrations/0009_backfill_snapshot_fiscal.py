"""Backfill do snapshot fiscal e da retenção para notas existentes."""

from datetime import date

from django.db import migrations
from django.utils import timezone


def _cinco_anos(data: date) -> date:
    try:
        return data.replace(year=data.year + 5)
    except ValueError:
        return data.replace(year=data.year + 5, day=28)


def _endereco(pedido) -> str:
    cliente = pedido.cliente
    partes = [
        pedido.logradouro or cliente.logradouro,
        pedido.numero_endereco or cliente.numero,
        pedido.bairro or cliente.bairro,
        pedido.cidade or cliente.cidade,
    ]
    texto = ", ".join(parte for parte in partes if parte)
    uf = pedido.uf or cliente.uf
    cep = pedido.cep or cliente.cep
    if uf:
        texto = f"{texto}/{uf}" if texto else uf
    if cep:
        texto = f"{texto} - CEP {cep}"
    return texto


def backfill(apps, schema_editor):
    NotaFiscal = apps.get_model("fiscal", "NotaFiscal")
    for nota in NotaFiscal.objects.select_related(
        "pedido", "pedido__cliente"
    ).all():
        pedido = nota.pedido
        cliente = pedido.cliente
        campos = []
        if not nota.itens_json:
            nota.cliente_nome = cliente.nome[:120]
            nota.cliente_documento = cliente.documento[:18]
            nota.cliente_tipo_pessoa = cliente.tipo_pessoa[:10]
            nota.cliente_endereco = _endereco(pedido)
            nota.valor_total = pedido.total
            nota.itens_json = [
                {
                    "produto": item.produto_nome,
                    "ncm": item.produto.ncm if item.produto_id else "",
                    "quantidade": str(item.quantidade),
                    "preco_unitario": str(item.preco_unitario),
                    "subtotal": str(item.quantidade * item.preco_unitario),
                }
                for item in pedido.itens.select_related("produto")
            ]
            campos += [
                "cliente_nome",
                "cliente_documento",
                "cliente_tipo_pessoa",
                "cliente_endereco",
                "valor_total",
                "itens_json",
            ]
        if nota.data_emissao is None:
            nota.data_emissao = nota.criado_em
            campos.append("data_emissao")
        if nota.data_emissao is not None:
            data_local = nota.data_emissao
            if timezone.is_aware(data_local):
                data_local = timezone.localtime(data_local)
            nota.retido_ate = _cinco_anos(data_local.date())
            campos.append("retido_ate")
        if campos:
            nota.save(update_fields=list(set(campos)))


class Migration(migrations.Migration):

    dependencies = [
        ("fiscal", "0008_notafiscal_retido_ate"),
    ]

    operations = [
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
