"""Valida integridade de domínio pós-restore (ledger, reservas, CMV e contagens)."""

from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Sum

from customers.models import Cliente
from fiscal.models import NotaFiscal
from sales.models import ItemPedido, Pedido
from stock.models import Estoque, MovimentoEstoque, ReservaEstoque


class Command(BaseCommand):
    help = "Valida integridade de ledger, reservas, CMV e contagens após restore."

    def handle(self, *args, **options):
        erros: list[str] = []

        for estoque in Estoque.objects.select_related("produto", "unidade"):
            soma_deltas = MovimentoEstoque.objects.filter(
                produto=estoque.produto,
                unidade=estoque.unidade,
            ).aggregate(total=Sum("delta"))["total"] or Decimal("0.00")
            if estoque.quantidade != soma_deltas:
                erros.append(
                    f"Ledger divergente em {estoque.produto_id}/{estoque.unidade_id}: "
                    f"saldo={estoque.quantidade} soma_deltas={soma_deltas}"
                )

            reservas_ativas = ReservaEstoque.objects.filter(
                produto=estoque.produto,
                unidade=estoque.unidade,
                status=ReservaEstoque.Status.ATIVA,
            ).aggregate(total=Sum("quantidade"))["total"] or Decimal("0.00")
            if estoque.quantidade_bloqueada != reservas_ativas:
                erros.append(
                    f"Reservas divergentes em {estoque.produto_id}/{estoque.unidade_id}: "
                    f"bloqueada={estoque.quantidade_bloqueada} ativas={reservas_ativas}"
                )

        itens_sem_custo = ItemPedido.objects.filter(custo_unitario__isnull=True).count()
        if itens_sem_custo:
            erros.append(f"ItemPedido sem custo_unitario: {itens_sem_custo}")

        if erros:
            raise CommandError("Falha na validação pós-restore:\n- " + "\n- ".join(erros))

        self.stdout.write(
            f"Pedidos={Pedido.objects.count()} "
            f"Clientes={Cliente.objects.count()} "
            f"Movimentos={MovimentoEstoque.objects.count()} "
            f"Notas={NotaFiscal.objects.count()}"
        )
        self.stdout.write(self.style.SUCCESS("RESTORE_VALIDADO_OK"))
