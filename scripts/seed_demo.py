"""Semeadura de catálogo demo coerente no banco de desenvolvimento (descartável)."""
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")
django.setup()

from django.conf import settings  # noqa: E402
from django.db.models.deletion import ProtectedError  # noqa: E402

if (
    settings.DATABASES["default"]["ENGINE"]
    != "django.db.backends.sqlite3"
    and os.environ.get("ALLOW_DEMO_SEED") != "1"
):
    raise SystemExit(
        "Recusando semear demo em banco não descartável. "
        "Defina ALLOW_DEMO_SEED=1 apenas em ambiente demo."
    )

from catalog.models import Categoria, Produto  # noqa: E402
from core.models import Unidade  # noqa: E402

# Limpa dados de debug
# (cadeia: pedidos/pagamentos → itens → movimentos → estoque → produto → unidade)
from sales.models import ItemPedido, Pagamento, Pedido  # noqa: E402
from stock.models import Estoque  # noqa: E402

debug_prods = Produto.objects.filter(nome__startswith="Debug")
itens_debug = ItemPedido.objects.filter(produto__in=debug_prods)
itens_com_reserva = itens_debug.filter(reservas__isnull=False).distinct()
pedido_ids = list(
    itens_debug.exclude(pk__in=itens_com_reserva.values("pk")).values_list(
        "pedido_id", flat=True
    )
)
Pagamento.objects.filter(pedido_id__in=pedido_ids).delete()
ItemPedido.objects.filter(pedido_id__in=pedido_ids).delete()
try:
    Pedido.objects.filter(id__in=pedido_ids).delete()
except ProtectedError:
    print("pedidos com reservas ou financeiro preservados")
# O ledger é imutável (STO-01): não excluímos movimentos. Produtos de debug
# com movimentos/reservas são apenas desativados.
com_movimentos = debug_prods.filter(movimentos__isnull=False).distinct()
com_reservas = debug_prods.filter(reservas__isnull=False).distinct()
preservados = (com_movimentos | com_reservas).distinct()
sem_movimentos = debug_prods.exclude(pk__in=preservados.values("pk"))
Estoque.objects.filter(produto__in=sem_movimentos).delete()
removidos, _ = sem_movimentos.delete()
if preservados.exists():
    preservados.update(ativo=False)
    print(
        "debug com movimentos/reservas desativado:",
        list(preservados.values_list("nome", flat=True)),
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
