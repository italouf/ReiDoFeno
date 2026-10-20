"""Conciliação humana e auditada de pedido legado sem prova financeira."""

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from sales.models import Pedido
from sales.services import reconciliar_pedido_financeiro


class Command(BaseCommand):
    help = (
        "Marca financeiro_conciliado=True para um pedido pago legado, "
        "exigindo justificativa. Não cria Pagamento aprovado fictício."
    )

    def add_arguments(self, parser):
        parser.add_argument("numero", help="Número do pedido (ex.: PF000123).")
        parser.add_argument(
            "--justificativa",
            required=True,
            help="Evidência/procedimento usado na conciliação.",
        )

    def handle(self, *args, **options):
        pedido = Pedido.objects.filter(numero=options["numero"]).first()
        if pedido is None:
            raise CommandError("Pedido não encontrado.")
        try:
            pedido = reconciliar_pedido_financeiro(
                pedido,
                justificativa=options["justificativa"],
                origem="comando",
            )
        except ValidationError as erro:
            raise CommandError(str(erro)) from erro
        self.stdout.write(
            self.style.SUCCESS(
                f"Pedido {pedido.numero} reconciliado financeiramente."
            )
        )
