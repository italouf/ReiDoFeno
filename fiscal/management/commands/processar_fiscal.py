"""Varre pedidos pagos: emite NF-e e gera avisos de pendência fiscal."""
from django.conf import settings
from django.core.management.base import BaseCommand

from fiscal.services import avisar_pagos_sem_nfe, processar_fila_fiscal


class Command(BaseCommand):
    help = (
        "Tenta emitir NF-e para pedidos pagos elegíveis (com retry das "
        "falhas) e avisa sobre pagos sem nota além do limite de horas."
    )

    def handle(self, *args, **options):
        enviadas = processar_fila_fiscal()
        horas = settings.FISCAL_ALERTA_HORAS_SEM_NFE
        avisos = avisar_pagos_sem_nfe(horas_limite=horas)

        self.stdout.write(
            self.style.SUCCESS(
                f"NF-e emitidas: {enviadas}; avisos 'pago sem NF-e': {avisos}."
            )
        )
