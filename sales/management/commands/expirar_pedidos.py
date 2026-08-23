"""Cancela pedidos que aguardam pagamento além do tempo configurado.

Agendado via cron da plataforma (ex.: a cada 15 minutos).
"""
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from sales.models import Pedido
from sales.services import cancelar_pedido


class Command(BaseCommand):
    help = (
        "Expira (cancela) pedidos em aguardando_pagamento/pagamento_pendente "
        "há mais de PEDIDO_TIMEOUT_MINUTOS minutos, liberando reservas."
    )

    def handle(self, *args, **options):
        limite = timezone.now() - timedelta(
            minutes=settings.PEDIDO_TIMEOUT_MINUTOS
        )
        expiraveis = Pedido.objects.filter(
            status__in=(
                Pedido.Status.AGUARDANDO_PAGAMENTO,
                Pedido.Status.PAGAMENTO_PENDENTE,
            ),
            criado_em__lt=limite,
        )

        total = 0
        for pedido in expiraveis.iterator():
            cancelar_pedido(pedido)
            total += 1
            self.stdout.write(f"Pedido {pedido.numero} expirado e cancelado.")

        self.stdout.write(
            self.style.SUCCESS(f"{total} pedido(s) expirado(s).")
        )
