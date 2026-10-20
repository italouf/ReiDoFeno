"""Cria/verifica fixtures da migração histórica 0001 → HEAD (CI PostgreSQL)."""

import uuid

from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

CASOS = {
    "PF900001": ("pago", None, "pago"),
    "PF900002": ("aguardando_pagamento", "aprovado", "pago"),
    "PF900003": ("cancelado", None, "cancelado"),
    "PF900004": ("falhou", None, "cancelado"),
    "PF900005": ("aguardando_pagamento", "recusado", "cancelado"),
    "PF900006": ("em_separacao", None, "pago"),
    "PF900007": ("concluido", "recusado", "pago"),
}


class Command(BaseCommand):
    help = "Cria fixtures no schema 0001 ou verifica o resultado após migrar."

    def add_arguments(self, parser):
        grupo = parser.add_mutually_exclusive_group(required=True)
        grupo.add_argument("--criar", action="store_true")
        grupo.add_argument("--verificar", action="store_true")

    def handle(self, *args, **options):
        if options["criar"]:
            self._criar()
        else:
            self._verificar()

    def _criar(self):
        executor = MigrationExecutor(connection)
        state = executor.loader.project_state([("sales", "0001_initial")])
        apps = state.apps
        Cliente = apps.get_model("customers", "Cliente")
        Unidade = apps.get_model("core", "Unidade")
        Pedido = apps.get_model("sales", "Pedido")
        Pagamento = apps.get_model("sales", "Pagamento")

        cliente, _ = Cliente.objects.get_or_create(
            documento="52998224725",
            defaults={
                "nome": "Cliente Migração",
                "tipo_pessoa": "fisica",
                "categoria": "varejo",
            },
        )
        unidade, _ = Unidade.objects.get_or_create(
            nome="Unidade Migração",
            defaults={"cidade": "Feira de Santana", "tipo": "loja"},
        )
        for numero, (status, pagamento_status, _esperado) in CASOS.items():
            pedido, criado = Pedido.objects.get_or_create(
                numero=numero,
                defaults={
                    "token_acesso": uuid.uuid4(),
                    "cliente_id": cliente.pk,
                    "unidade_id": unidade.pk,
                    "canal": "loja",
                    "modalidade": "retirada",
                    "subtotal": "10.00",
                    "frete": "0.00",
                    "total": "10.00",
                    "status": status,
                },
            )
            if criado and pagamento_status:
                Pagamento.objects.create(
                    pedido_id=pedido.pk,
                    provedor="mercadopago",
                    status=pagamento_status,
                    valor="10.00",
                )
        self.stdout.write(
            self.style.SUCCESS("Fixtures históricas criadas no schema 0001.")
        )

    def _verificar(self):
        from sales.models import Pedido

        encontrados = {
            pedido.numero: (pedido.status, pedido.status_financeiro)
            for pedido in Pedido.objects.filter(
                numero__in=CASOS.keys()
            )
        }
        falhas = []
        for numero, (_status, _pagamento, esperado) in CASOS.items():
            atual = encontrados.get(numero)
            if atual is None or atual[1] != esperado:
                falhas.append(
                    f"{numero}: esperado financeiro={esperado}, atual={atual}"
                )
        if falhas:
            raise CommandError("; ".join(falhas))
        self.stdout.write(
            self.style.SUCCESS(
                f"Migração validada para {len(CASOS)} cenários."
            )
        )
