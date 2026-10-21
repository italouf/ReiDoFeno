"""B04: semeadura de estoque via ledger e guarda de ambiente."""

from decimal import Decimal

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db.models import Sum
from django.test import TestCase

from catalog.factories import ProdutoFactory
from core.factories import UnidadeFactory
from sales.factories import ItemPedidoFactory, PedidoFactory
from sales.models import Pedido
from stock.factories import EstoqueFactory
from stock.models import Estoque, MovimentoEstoque, ReservaEstoque
from stock.services import registrar_movimento, reservar


class SemearEstoqueDemoTests(TestCase):
    def setUp(self):
        self.produto = ProdutoFactory(nome="Demo Ledger")
        self.feira = UnidadeFactory(nome="Feira de Santana")
        self.iacu = UnidadeFactory(nome="Iaçu")
        self.estoque = EstoqueFactory(
            produto=self.produto,
            unidade=self.feira,
            quantidade="0.00",
            quantidade_minima="0.00",
        )
        registrar_movimento(
            produto=self.produto,
            unidade=self.feira,
            tipo=MovimentoEstoque.Tipo.ENTRADA,
            delta=Decimal("10.00"),
            motivo="carga inicial do teste",
        )
        self.pedido = PedidoFactory(
            unidade=self.feira,
            status=Pedido.Status.AGUARDANDO_PAGAMENTO,
            status_financeiro=Pedido.StatusFinanceiro.PENDENTE,
        )
        item = ItemPedidoFactory(
            pedido=self.pedido,
            produto=self.produto,
            quantidade=Decimal("2.00"),
        )
        self.reserva = reservar(
            produto=self.produto,
            unidade=self.feira,
            quantidade=Decimal("2.00"),
            pedido=self.pedido,
            item_pedido=item,
        )

    def test_seed_usa_ledger_e_preserva_bloqueio(self):
        call_command("semear_estoque_demo", verbosity=0)

        estoque = Estoque.objects.get(
            produto=self.produto, unidade=self.feira
        )
        total = MovimentoEstoque.objects.filter(
            produto=self.produto, unidade=self.feira
        ).aggregate(total=Sum("delta"))["total"]
        self.assertEqual(estoque.quantidade, Decimal("60.00"))
        self.assertEqual(total, Decimal("60.00"))
        self.assertEqual(estoque.quantidade_bloqueada, Decimal("2.00"))
        self.reserva.refresh_from_db()
        self.assertEqual(
            self.reserva.status, ReservaEstoque.Status.ATIVA
        )
        self.assertTrue(
            Estoque.objects.filter(
                produto=self.produto, unidade=self.iacu
            ).exists()
        )

    def test_seed_e_idempotente(self):
        call_command("semear_estoque_demo", verbosity=0)
        movimentos = MovimentoEstoque.objects.count()
        call_command("semear_estoque_demo", verbosity=0)
        self.assertEqual(MovimentoEstoque.objects.count(), movimentos)

    def test_seed_recusa_banco_nao_sqlite_sem_autorizacao(self):
        import os
        from unittest import mock

        os.environ.pop("ALLOW_DEMO_SEED", None)
        with mock.patch(
            "stock.management.commands.semear_estoque_demo.settings"
        ) as settings_fake:
            settings_fake.DATABASES = {
                "default": {"ENGINE": "django.db.backends.postgresql"}
            }
            with pytest.raises(CommandError):
                call_command("semear_estoque_demo", verbosity=0)
