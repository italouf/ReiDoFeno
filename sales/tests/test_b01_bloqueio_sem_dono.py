"""B01: operações de um pedido nunca reduzem reserva/bloqueio de outro."""

from datetime import timedelta
from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from analytics.models import Aviso
from catalog.factories import ProdutoFactory
from core.factories import UnidadeFactory
from core.models import LogAuditoria
from sales.factories import ItemPedidoFactory, PedidoFactory
from sales.models import Pedido
from sales.services import cancelar_pedido, marcar_pagamento_aprovado
from stock.factories import EstoqueFactory
from stock.models import Estoque, ReservaEstoque
from stock.services import reservar


class BloqueioSemDonoTests(TestCase):
    def setUp(self):
        self.produto = ProdutoFactory()
        self.unidade = UnidadeFactory()
        self.estoque = EstoqueFactory(
            produto=self.produto, unidade=self.unidade, quantidade="10.00"
        )
        self.pedido_b = PedidoFactory(
            unidade=self.unidade,
            status=Pedido.Status.AGUARDANDO_PAGAMENTO,
            status_financeiro=Pedido.StatusFinanceiro.PENDENTE,
        )
        self.item_b = ItemPedidoFactory(
            pedido=self.pedido_b,
            produto=self.produto,
            quantidade=Decimal("10.00"),
        )
        self.reserva_b = reservar(
            produto=self.produto,
            unidade=self.unidade,
            quantidade=Decimal("10.00"),
            pedido=self.pedido_b,
            item_pedido=self.item_b,
        )

    def _pedido_legado(self, quantidade="3.00"):
        pedido = PedidoFactory(
            unidade=self.unidade,
            status=Pedido.Status.AGUARDANDO_PAGAMENTO,
            status_financeiro=Pedido.StatusFinanceiro.PENDENTE,
        )
        item = ItemPedidoFactory(
            pedido=pedido,
            produto=self.produto,
            quantidade=Decimal(quantidade),
        )
        return pedido, item

    def _assert_reserva_b_intacta(self):
        self.reserva_b.refresh_from_db()
        self.pedido_b.refresh_from_db()
        estoque = Estoque.objects.get(
            produto=self.produto, unidade=self.unidade
        )
        self.assertEqual(estoque.quantidade, Decimal("10.00"))
        self.assertEqual(estoque.quantidade_bloqueada, Decimal("10.00"))
        self.assertEqual(
            self.reserva_b.status, ReservaEstoque.Status.ATIVA
        )

    def test_cancelar_legado_nao_libera_reserva_de_terceiro(self):
        pedido_a, _item = self._pedido_legado()

        cancelar_pedido(pedido_a)

        self._assert_reserva_b_intacta()

    def test_expiracao_legado_nao_libera_reserva_de_terceiro(self):
        pedido_a, _item = self._pedido_legado()
        antigo = timezone.now() - timedelta(hours=10)
        Pedido.objects.filter(pk=pedido_a.pk).update(criado_em=antigo)

        call_command("expirar_pedidos", verbosity=0)

        pedido_a.refresh_from_db()
        self.assertEqual(pedido_a.status, Pedido.Status.CANCELADO)
        self._assert_reserva_b_intacta()

    def test_aprovar_legado_nao_consome_estoque_de_terceiro(self):
        pedido_a, _item = self._pedido_legado()

        marcar_pagamento_aprovado(pedido_a, id_externo="pay-b01")

        pedido_a.refresh_from_db()
        self.assertEqual(
            pedido_a.status_financeiro, Pedido.StatusFinanceiro.PAGO
        )
        self._assert_reserva_b_intacta()
        self.assertTrue(
            Aviso.objects.filter(
                tipo=Aviso.Tipo.ESTOQUE_PENDENTE, objeto_id=str(pedido_a.pk)
            ).exists()
        )
        self.assertTrue(
            LogAuditoria.objects.filter(
                acao="pedido.estoque_pendente",
                objeto_id=str(pedido_a.pk),
            ).exists()
        )

    def test_aprovacao_parcial_com_livre_insuficiente_nao_toca_terceiro(self):
        # B reserva 8; A tem item 10 e reserva parcial de 2 (total bloqueado 10).
        self.reserva_b.quantidade = Decimal("8.00")
        self.reserva_b.save(update_fields=["quantidade"])
        Estoque.objects.filter(pk=self.estoque.pk).update(
            quantidade_bloqueada=Decimal("8.00")
        )
        pedido_a, item_a = self._pedido_legado(quantidade="10.00")
        reserva_a = ReservaEstoque.objects.create(
            pedido=pedido_a,
            item_pedido=item_a,
            produto=self.produto,
            unidade=self.unidade,
            quantidade=Decimal("2.00"),
            status=ReservaEstoque.Status.ATIVA,
        )
        Estoque.objects.filter(pk=self.estoque.pk).update(
            quantidade_bloqueada=Decimal("10.00")
        )

        marcar_pagamento_aprovado(pedido_a, id_externo="pay-parcial-b01")

        reserva_a.refresh_from_db()
        estoque = Estoque.objects.get(
            produto=self.produto, unidade=self.unidade
        )
        self.assertEqual(reserva_a.status, ReservaEstoque.Status.CONSUMIDA)
        # Consumiu os 2 reservados; os 8 restantes ficaram pendentes porque
        # o livre é zero (tudo comprometido com B).
        self.assertEqual(estoque.quantidade, Decimal("8.00"))
        self.assertEqual(estoque.quantidade_bloqueada, Decimal("8.00"))
        self.reserva_b.refresh_from_db()
        self.assertEqual(
            self.reserva_b.status, ReservaEstoque.Status.ATIVA
        )
        self.assertTrue(
            Aviso.objects.filter(
                tipo=Aviso.Tipo.ESTOQUE_PENDENTE, objeto_id=str(pedido_a.pk)
            ).exists()
        )
