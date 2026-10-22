"""Semeadura de catálogo demo coerente no banco de desenvolvimento (descartável)."""
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")
django.setup()

from django.db.models.deletion import ProtectedError  # noqa: E402

if os.environ.get("ALLOW_DEMO_SEED") != "1":
    raise SystemExit(
        "Recusando semear demo sem confirmação explícita. "
        "Defina ALLOW_DEMO_SEED=1 apenas em ambiente demo descartável."
    )

# Limpa dados de debug
# (cadeia: pedidos/pagamentos → itens → movimentos → estoque → produto → unidade)
from django.db import models, transaction  # noqa: E402

from catalog.models import Categoria, Produto  # noqa: E402
from core.models import Unidade  # noqa: E402
from sales.models import (  # noqa: E402
    ItemPedido,
    ObrigacaoEstoquePedido,
    Pagamento,
    Pedido,
)
from stock.models import Estoque  # noqa: E402

debug_prods = list(Produto.objects.filter(nome__startswith="Debug"))
ids_debug = {produto.pk for produto in debug_prods}


def _classificar_pedidos_debug():
    pedidos = list(
        Pedido.objects.filter(itens__produto__in=debug_prods).distinct()
    )
    remover, preservar = [], []
    for pedido in pedidos:
        itens = list(pedido.itens.values_list("produto_id", flat=True))
        if (
            itens
            and set(itens).issubset(ids_debug)
            and not pedido.reservas.exists()
        ):
            remover.append(pedido)
        else:
            preservar.append(pedido)
    return remover, preservar


remover, preservar = _classificar_pedidos_debug()
for pedido in remover:
    try:
        with transaction.atomic():
            ObrigacaoEstoquePedido.objects.filter(pedido=pedido).delete()
            Pagamento.objects.filter(pedido=pedido).delete()
            ItemPedido.objects.filter(pedido=pedido).delete()
            pedido.delete()
    except ProtectedError:
        # Nada foi apagado: pagamento/item/pedido permanecem juntos.
        preservar.append(pedido)
        print(f"pedido protegido preservado: {pedido.numero}")

# O ledger é imutável (STO-01): não excluímos movimentos. Produtos de debug
# com movimentos/reservas/pedidos preservados são apenas desativados.
preservados = list(
    Produto.objects.filter(pk__in=ids_debug)
    .filter(
        models.Q(movimentos__isnull=False) | models.Q(reservas__isnull=False)
    )
    .distinct()
)
if preservar:
    preservados += list(
        Produto.objects.filter(
            pk__in=ids_debug, itens_pedido__pedido__in=preservar
        ).distinct()
    )
ids_preservados = {produto.pk for produto in preservados}
removidos = 0
for produto in debug_prods:
    if produto.pk in ids_preservados:
        continue
    try:
        with transaction.atomic():
            Estoque.objects.filter(produto=produto).delete()
            produto.delete()
        removidos += 1
    except ProtectedError:
        preservados.append(produto)
        print(f"produto debug protegido preservado: {produto.nome}")
preservados = list({produto.pk: produto for produto in preservados}.values())
if preservados:
    Produto.objects.filter(
        pk__in=[produto.pk for produto in preservados]
    ).update(ativo=False)
    print(
        "debug protegido desativado:",
        [produto.nome for produto in preservados],
    )
try:
    Categoria.objects.filter(nome__startswith="Categoria").delete()
    Unidade.objects.filter(nome__startswith="Debug").delete()
except ProtectedError:
    print("categorias/unidades de debug protegidas preservadas")
print("debug removido:", removidos)

cats = {n: Categoria.objects.get_or_create(nome=n, defaults={"ativa": True})[0]
        for n in ("Fenos", "Ração", "Suplementos")}

for nome, cidade, tipo, ativa in (
    ("Feira de Santana", "Feira de Santana", "matriz", True),
    ("Iaçu", "Iaçu", "filial", True),
):
    Unidade.objects.get_or_create(
        nome=nome, defaults={"cidade": cidade, "tipo": tipo, "ativa": ativa}
    )

# nome, categoria, NCM, unidade, custo, preço balcão, preço online
CATALOGO = [
    ("Feno Tifton 85 — Fardo 20kg", "Fenos", "12149000", "fardo", "20.00", "32.00", "35.90"),
    ("Feno Coastcross — Fardo 15kg", "Fenos", "12149000", "fardo", "16.00", "25.00", "27.50"),
    ("Feno de Alfafa — Fardo 10kg", "Fenos", "12149000", "fardo", "22.00", "38.00", "41.00"),
    ("Ração para Equinos — Saco 25kg", "Ração", "23099090", "saco", "85.00", "129.90", "134.90"),
    ("Farelo de Soja — Saco 40kg", "Suplementos", "23040010", "saco", "98.00", "148.00", "154.00"),
    ("Sal Mineral Bovino — Saco 30kg", "Suplementos", "25010090",
     "saco", "60.00", "89.90", "94.90"),
]
for nome, cat, ncm, unid, custo, balcao, online in CATALOGO:
    obj, criado = Produto.objects.get_or_create(
        nome=nome,
        defaults={
            "categoria": cats[cat], "ncm": ncm, "unidade_medida": unid,
            "custo": custo, "preco_balcao": balcao, "preco_online": online, "ativo": True,
        },
    )
    print(("criado " if criado else "existe ") + nome)

print("total ativos:", Produto.objects.filter(ativo=True).count())
