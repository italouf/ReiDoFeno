"""Semeadura de estoque demo via ledger, restrita a banco descartável."""

import os
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from catalog.models import Produto
from core.models import Unidade
from stock.models import Estoque
from stock.services import registrar_ajuste

ALVOS = (
    ("Feira de Santana", Decimal("60.00"), Decimal("10.00")),
    ("Iaçu", Decimal("35.00"), Decimal("8.00")),
)


class Command(BaseCommand):
    help = (
        "Ajusta o estoque demo para 60/35 usando o ledger. Exige "
        "ALLOW_DEMO_SEED=1 fora do SQLite."
    )

    def handle(self, *args, **options):
        if os.environ.get("ALLOW_DEMO_SEED") != "1":
            raise CommandError(
                "Recusando semear estoque sem confirmação explícita. "
                "Defina ALLOW_DEMO_SEED=1 apenas em ambiente demo descartável."
            )

        unidades = {unidade.nome: unidade for unidade in Unidade.objects.all()}
        for nome, alvo, minimo in ALVOS:
            unidade = unidades.get(nome)
            if unidade is None:
                self.stderr.write(f"Unidade ausente: {nome}")
                continue
            for produto in Produto.objects.filter(ativo=True):
                estoque, _ = Estoque.objects.get_or_create(
                    produto=produto,
                    unidade=unidade,
                    defaults={
                        "quantidade": Decimal("0.00"),
                        "quantidade_minima": minimo,
                    },
                )
                if estoque.quantidade_minima != minimo:
                    Estoque.objects.filter(pk=estoque.pk).update(
                        quantidade_minima=minimo
                    )
                delta = alvo - estoque.quantidade
                if delta == 0:
                    continue
                try:
                    registrar_ajuste(
                        produto=produto,
                        unidade=unidade,
                        delta=delta,
                        motivo="Semeadura demo (via ledger)",
                    )
                except ValidationError as erro:
                    self.stderr.write(
                        f"{produto.nome} @ {nome}: ajuste ignorado ({erro})"
                    )
                    continue
                print(f"estoque ok (ledger): {produto.nome} @ {nome}")
