"""R01: obrigação persistente impede avanço sem baixa de estoque."""

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.test import TestCase

from accounts.models import Usuario
from catalog.factories import ProdutoFactory
from core.factories import UnidadeFactory
from sales.factories import ItemPedidoFactory, PedidoFactory
from sales.models import ObrigacaoEstoquePedido, Pedido
from sales.services import (
    marcar_pagamento_aprovado,
    resolver_pendencia_estoque,
)
from stock.factories import EstoqueFactory
from stock.models import Estoque, MovimentoEstoque, ReservaEstoque
from stock.services import registrar_movimento, reservar


class ObrigacaoEstoqueTests(TestCase):
    def setUp(self):
        self.usuario = Usuario.objects.create_user(
            username="gestor-r01", password="senha-forte-123"
        )
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

    def _obrigacao(self, pedido):
        return ObrigacaoEstoquePedido.objects.get(
            pedido=pedido, produto=self.produto, unidade=self.unidade
        )

    def test_pendencia_bloqueia_avanco_e_resolucao_libera(self):
        pedido_a, _item = self._pedido_legado("3.00")

        marcar_pagamento_aprovado(pedido_a, id_externo="pay-r01")

        pedido_a.refresh_from_db()
        obrigacao = self._obrigacao(pedido_a)
        self.assertEqual(obrigacao.status, ObrigacaoEstoquePedido.Status.PENDENTE)
        self.assertEqual(obrigacao.quantidade_devida, Decimal("3.00"))
        self.assertEqual(obrigacao.quantidade_baixada, Decimal("0.00"))
        with pytest.raises(ValidationError):
            pedido_a.transicionar(Pedido.Status.EM_SEPARACAO)

        registrar_movimento(
            produto=self.produto,
            unidade=self.unidade,
            tipo=MovimentoEstoque.Tipo.ENTRADA,
            delta=Decimal("3.00"),
            motivo="reposição para resolver pendência",
        )
        resolver_pendencia_estoque(
            pedido_a,
            produto=self.produto,
            unidade=self.unidade,
            usuario=self.usuario,
            justificativa="estoque reposto e conferido",
        )

        obrigacao.refresh_from_db()
        pedido_a.refresh_from_db()
        self.assertEqual(
            obrigacao.status, ObrigacaoEstoquePedido.Status.RESOLVIDA
        )
        self.assertEqual(obrigacao.quantidade_baixada, Decimal("3.00"))
        estoque = Estoque.objects.get(produto=self.produto, unidade=self.unidade)
        self.assertEqual(estoque.quantidade, Decimal("10.00"))
        self.assertEqual(estoque.quantidade_bloqueada, Decimal("10.00"))
        self.reserva_b.refresh_from_db()
        self.assertEqual(
            self.reserva_b.status, ReservaEstoque.Status.ATIVA
        )
        pedido_a.transicionar(Pedido.Status.EM_SEPARACAO)

    def test_resolucao_e_idempotente(self):
        pedido_a, _item = self._pedido_legado("3.00")
        marcar_pagamento_aprovado(pedido_a, id_externo="pay-r01-idem")
        registrar_movimento(
            produto=self.produto,
            unidade=self.unidade,
            tipo=MovimentoEstoque.Tipo.ENTRADA,
            delta=Decimal("3.00"),
            motivo="reposição",
        )
        resolver_pendencia_estoque(
            pedido_a,
            produto=self.produto,
            unidade=self.unidade,
            usuario=self.usuario,
            justificativa="primeira resolução",
        )
        movimentos = MovimentoEstoque.objects.count()
        resolver_pendencia_estoque(
            pedido_a,
            produto=self.produto,
            unidade=self.unidade,
            usuario=self.usuario,
            justificativa="segunda resolução",
        )
        self.assertEqual(MovimentoEstoque.objects.count(), movimentos)

    def test_multiplos_produtos_bloqueiam_ate_todos_resolverem(self):
        produto1 = ProdutoFactory()
        EstoqueFactory(
            produto=produto1, unidade=self.unidade, quantidade="5.00"
        )
        produto2 = ProdutoFactory()
        EstoqueFactory(
            produto=produto2, unidade=self.unidade, quantidade="0.00"
        )
        pedido = PedidoFactory(
            unidade=self.unidade,
            status=Pedido.Status.AGUARDANDO_PAGAMENTO,
            status_financeiro=Pedido.StatusFinanceiro.PENDENTE,
        )
        ItemPedidoFactory(
            pedido=pedido,
            produto=produto1,
            quantidade=Decimal("1.00"),
        )
        ItemPedidoFactory(
            pedido=pedido,
            produto=produto2,
            quantidade=Decimal("2.00"),
        )
        marcar_pagamento_aprovado(pedido, id_externo="pay-r01-multi")
        with pytest.raises(ValidationError):
            pedido.transicionar(Pedido.Status.EM_SEPARACAO)

        registrar_movimento(
            produto=produto2,
            unidade=self.unidade,
            tipo=MovimentoEstoque.Tipo.ENTRADA,
            delta=Decimal("2.00"),
            motivo="reposição produto 2",
        )
        resolver_pendencia_estoque(
            pedido,
            produto=produto2,
            unidade=self.unidade,
            usuario=self.usuario,
            justificativa="reposição do segundo produto",
        )
        pedido.refresh_from_db()
        pedido.transicionar(Pedido.Status.EM_SEPARACAO)

    def test_cancelamento_cancela_obrigacao_pendente(self):
        from sales.services import cancelar_pedido

        pedido_a, _item = self._pedido_legado("3.00")
        ObrigacaoEstoquePedido.objects.create(
            pedido=pedido_a,
            produto=self.produto,
            unidade=self.unidade,
            quantidade_devida=Decimal("3.00"),
            status=ObrigacaoEstoquePedido.Status.PENDENTE,
        )
        cancelar_pedido(pedido_a, permitir_pago=True)
        obrigacao = self._obrigacao(pedido_a)
        self.assertEqual(
            obrigacao.status, ObrigacaoEstoquePedido.Status.CANCELADA
        )
