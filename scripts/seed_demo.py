"""Semeadura de catálogo demo coerente no banco de desenvolvimento (descartável)."""
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")
django.setup()

from catalog.models import Categoria, Produto  # noqa: E402
from core.models import Unidade  # noqa: E402

# Limpa dados de debug
# (cadeia: pedidos/pagamentos → itens → movimentos → estoque → produto → unidade)
from sales.models import ItemPedido, Pagamento, Pedido  # noqa: E402
from stock.models import Estoque, MovimentoEstoque  # noqa: E402

debug_prods = Produto.objects.filter(nome__startswith="Debug")
pedido_ids = list(
    ItemPedido.objects.filter(produto__in=debug_prods).values_list("pedido_id", flat=True)
)
Pagamento.objects.filter(pedido_id__in=pedido_ids).delete()
ItemPedido.objects.filter(pedido_id__in=pedido_ids).delete()
Pedido.objects.filter(id__in=pedido_ids).delete()
MovimentoEstoque.objects.filter(produto__in=debug_prods).delete()
Estoque.objects.filter(produto__in=debug_prods).delete()
removidos, _ = debug_prods.delete()
Categoria.objects.filter(nome__startswith="Categoria").delete()
Unidade.objects.filter(nome__startswith="Debug").delete()
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
