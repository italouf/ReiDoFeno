"""Semeadura de estoque demo nas duas unidades (descartável)."""
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")
django.setup()

from catalog.models import Produto  # noqa: E402
from core.models import Unidade  # noqa: E402
from stock.models import Estoque  # noqa: E402

feira = Unidade.objects.get(nome="Feira de Santana")
iacu = Unidade.objects.get(nome="Iaçu")

for produto in Produto.objects.filter(ativo=True):
    Estoque.objects.update_or_create(
        produto=produto, unidade=feira,
        defaults={"quantidade": 60, "quantidade_minima": 10, "quantidade_bloqueada": 0},
    )
    Estoque.objects.update_or_create(
        produto=produto, unidade=iacu,
        defaults={"quantidade": 35, "quantidade_minima": 8, "quantidade_bloqueada": 0},
    )
    print("estoque ok:", produto.nome)

print("total:", Estoque.objects.count())
