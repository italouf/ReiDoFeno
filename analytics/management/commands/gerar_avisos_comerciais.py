"""Gera avisos comerciais: recompra e pagamento pendente antigo.

Agendado diariamente via cron da plataforma.
"""
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from analytics.models import Aviso
from analytics.services import clientes_para_recompra
from sales.models import Pedido


class Command(BaseCommand):
    help = (
        "Sinaliza possíveis recompras (clientes sem compra há X dias) e "
        "pagamentos pendentes há muito tempo."
    )

    def handle(self, *args, **options):
        dias_recompra = getattr(settings, "RECOMPRA_DIAS", 30)
        total_recompras = 0

        for cliente in clientes_para_recompra(dias_recompra):
            Aviso.registrar(
                tipo=Aviso.Tipo.POSSIVEL_RECOMPRA,
                mensagem=(
                    f"{cliente.nome} não compra há {dias_recompra}+ dias; "
                    "bom momento para contato de reposição."
                ),
                objeto=cliente,
                severidade=Aviso.Severidade.INFO,
            )
            total_recompras += 1

        meia_vida = timezone.now() - timedelta(
            minutes=settings.PEDIDO_TIMEOUT_MINUTOS // 2
        )
        pendentes = Pedido.objects.filter(
            status__in=(
                Pedido.Status.AGUARDANDO_PAGAMENTO,
                Pedido.Status.PAGAMENTO_PENDENTE,
            ),
            criado_em__lt=meia_vida,
        ).select_related("cliente")

        total_pendentes = 0
        for pedido in pendentes:
            Aviso.registrar(
                tipo=Aviso.Tipo.PAGAMENTO_PENDENTE,
                mensagem=(
                    f"Pedido {pedido.numero} aguarda pagamento há muito tempo."
                ),
                objeto=pedido,
            )
            total_pendentes += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Recompras sinalizadas: {total_recompras}; "
                f"pendências antigas avisadas: {total_pendentes}."
            )
        )
