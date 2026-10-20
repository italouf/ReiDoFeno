"""Inventário read-only de dados legados que exigem conciliação/revisão."""

import json

from django.core.management.base import BaseCommand
from django.db.models import Exists, OuterRef

from customers.models import Cliente
from sales.models import Pagamento, Pedido


class Command(BaseCommand):
    help = (
        "Lista pedidos pagos sem Pagamento aprovado e vínculos de cliente "
        "ainda não verificados. Não altera dados."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--json",
            action="store_true",
            help="Emite JSON em vez de texto.",
        )

    def handle(self, *args, **options):
        aprovados = Pagamento.objects.filter(
            pedido=OuterRef("pk"), status=Pagamento.Status.APROVADO
        )
        pagos_sem_prova = (
            Pedido.objects.filter(status_financeiro="pago")
            .exclude(Exists(aprovados))
            .order_by("numero")
        )
        vinculos_pendentes = Cliente.objects.filter(
            usuario__isnull=False, vinculo_verificado=False
        ).order_by("nome")

        dados = {
            "pedidos_pagos_sem_pagamento_aprovado": [
                {
                    "numero": pedido.numero,
                    "status": pedido.status,
                    "status_financeiro": pedido.status_financeiro,
                }
                for pedido in pagos_sem_prova
            ],
            "vinculos_nao_verificados": [
                {
                    "cliente_id": cliente.pk,
                    "nome": cliente.nome,
                    "usuario_id": cliente.usuario_id,
                }
                for cliente in vinculos_pendentes
            ],
        }

        if options["json"]:
            self.stdout.write(json.dumps(dados, ensure_ascii=False, indent=2))
        else:
            self.stdout.write(
                "Pedidos pagos sem Pagamento aprovado: "
                f"{len(dados['pedidos_pagos_sem_pagamento_aprovado'])}"
            )
            for item in dados["pedidos_pagos_sem_pagamento_aprovado"]:
                self.stdout.write(
                    f"  {item['numero']} status={item['status']} "
                    f"financeiro={item['status_financeiro']}"
                )
            self.stdout.write(
                f"Vínculos não verificados: "
                f"{len(dados['vinculos_nao_verificados'])}"
            )
            for item in dados["vinculos_nao_verificados"]:
                self.stdout.write(
                    f"  cliente={item['cliente_id']} usuario={item['usuario_id']} "
                    f"{item['nome']}"
                )
        self.stdout.write(
            self.style.SUCCESS("Inventário concluído; nenhum dado foi alterado.")
        )
