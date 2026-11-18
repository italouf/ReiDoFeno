"""Validação de consistência pós-restore (STO-01, ADR-003, ADR-008)."""

from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db.models import Sum
from django.test import TransactionTestCase

from catalog.factories import ProdutoFactory
from core.factories import UnidadeFactory
from customers.factories import ClienteFactory
from sales.factories import ItemPedidoFactory, PedidoFactory
from stock.factories import EstoqueFactory
from stock.models import Estoque, MovimentoEstoque, ReservaEstoque
from stock.services import registrar_movimento


class RestoreValidationTests(TransactionTestCase):
    """Validação de consistência pós-restore."""

    def test_ledger_reconcilia_apos_restore(self):
        """Após restore, SUM(deltas) == saldo em todos os estoques."""
        produto = ProdutoFactory()
        unidade = UnidadeFactory()
        EstoqueFactory(produto=produto, unidade=unidade, quantidade="0.00")
        registrar_movimento(
            produto=produto,
            unidade=unidade,
            tipo=MovimentoEstoque.Tipo.ENTRADA,
            quantidade=Decimal("25.00"),
            motivo="Carga inicial restore",
        )
        registrar_movimento(
            produto=produto,
            unidade=unidade,
            tipo=MovimentoEstoque.Tipo.SAIDA,
            quantidade=Decimal("5.00"),
            motivo="Saida restore",
        )

        for estoque in Estoque.objects.all():
            soma_deltas = MovimentoEstoque.objects.filter(
                produto=estoque.produto,
                unidade=estoque.unidade,
            ).aggregate(total=Sum("delta"))["total"] or Decimal("0.00")
            self.assertEqual(
                estoque.quantidade,
                soma_deltas,
                f"Ledger inconsistente para {estoque.produto}/{estoque.unidade}",
            )

    def test_reservas_reconciliam_apos_restore(self):
        """SUM(reservas ativas) == Estoque.quantidade_bloqueada."""
        produto = ProdutoFactory()
        unidade = UnidadeFactory()
        estoque = EstoqueFactory(
            produto=produto,
            unidade=unidade,
            quantidade="20.00",
            quantidade_bloqueada="4.00",
        )
        pedido = PedidoFactory(unidade=unidade)
        ReservaEstoque.objects.create(
            pedido=pedido,
            produto=produto,
            unidade=unidade,
            quantidade=Decimal("4.00"),
            status=ReservaEstoque.Status.ATIVA,
        )

        for est in Estoque.objects.filter(pk=estoque.pk):
            reservas_ativas = ReservaEstoque.objects.filter(
                produto=est.produto,
                unidade=est.unidade,
                status="ativa",
            ).aggregate(total=Sum("quantidade"))["total"] or Decimal("0.00")
            self.assertEqual(est.quantidade_bloqueada, reservas_ativas)

    def test_itens_tem_custo_snapshot(self):
        """Todos os ItemPedido têm custo_unitario preenchido."""
        from sales.models import ItemPedido

        pedido = PedidoFactory()
        ItemPedidoFactory(pedido=pedido, custo_unitario=Decimal("12.50"))
        itens_sem_custo = ItemPedido.objects.filter(
            custo_unitario__isnull=True
        ).count()
        self.assertEqual(itens_sem_custo, 0)

    def test_comando_validar_restore_passa_e_falha_em_divergencia(self):
        """Management command validar_restore detecta consistência e divergência."""
        produto = ProdutoFactory()
        unidade = UnidadeFactory()
        cliente = ClienteFactory(documento="00000000E08G12", tipo_pessoa="juridica")
        pedido = PedidoFactory(cliente=cliente, unidade=unidade)
        ItemPedidoFactory(pedido=pedido, produto=produto, custo_unitario=Decimal("8.00"))
        EstoqueFactory(produto=produto, unidade=unidade, quantidade="0.00")
        registrar_movimento(
            produto=produto,
            unidade=unidade,
            tipo=MovimentoEstoque.Tipo.ENTRADA,
            quantidade=Decimal("10.00"),
            motivo="Entrada valida",
        )

        out = StringIO()
        call_command("validar_restore", stdout=out)
        self.assertIn("RESTORE_VALIDADO_OK", out.getvalue())

        # Corrompe saldo via QuerySet.update para simular inconsistência pós-restore
        Estoque.objects.filter(produto=produto, unidade=unidade).update(
            quantidade=Decimal("99.00")
        )
        with self.assertRaises(CommandError):
            call_command("validar_restore")
