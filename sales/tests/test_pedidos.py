from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from catalog.factories import ProdutoFactory
from sales.factories import PedidoFactory
from sales.models import ItemPedido, Pagamento, Pedido


class MaquinaStatusTests(TestCase):
    def test_transicao_valida_e_aplicada(self):
        pedido = PedidoFactory(status=Pedido.Status.AGUARDANDO_PAGAMENTO)
        pedido.transicionar(Pedido.Status.PAGO)
        self.assertEqual(pedido.status, Pedido.Status.PAGO)

    def test_fluxo_completo_ate_concluido(self):
        pedido = PedidoFactory()
        caminho = [
            Pedido.Status.PAGAMENTO_PENDENTE,
            Pedido.Status.PAGO,
            Pedido.Status.EM_SEPARACAO,
            Pedido.Status.PRONTO_PARA_ENTREGA,
            Pedido.Status.ENVIADO,
            Pedido.Status.CONCLUIDO,
        ]
        for status in caminho:
            pedido.transicionar(status)
        self.assertEqual(pedido.status, Pedido.Status.CONCLUIDO)

    def test_transicao_invalida_e_rejeitada(self):
        pedido = PedidoFactory(status=Pedido.Status.RASCUNHO)
        with self.assertRaises(ValidationError) as contexto:
            pedido.transicionar(Pedido.Status.CONCLUIDO)
        self.assertIn("Transição inválida", str(contexto.exception))

    def test_estados_finais_nao_permitem_nada(self):
        for final in (Pedido.Status.CANCELADO, Pedido.Status.CONCLUIDO):
            with self.subTest(final=final):
                pedido = PedidoFactory(status=final)
                with self.assertRaises(ValidationError):
                    pedido.transicionar(Pedido.Status.PAGO)

    def test_falhou_permite_reiniciar_pagamento(self):
        pedido = PedidoFactory(status=Pedido.Status.AGUARDANDO_PAGAMENTO)
        pedido.transicionar(Pedido.Status.FALHOU)
        pedido.transicionar(Pedido.Status.AGUARDANDO_PAGAMENTO)
        self.assertEqual(pedido.status, Pedido.Status.AGUARDANDO_PAGAMENTO)


class PedidoModelTests(TestCase):
    def test_numero_gerado_automaticamente_e_unico(self):
        pedido_a = PedidoFactory()
        pedido_b = PedidoFactory()
        self.assertTrue(pedido_a.numero)
        self.assertNotEqual(pedido_a.numero, pedido_b.numero)

    def test_token_de_acesso_unico_por_pedido(self):
        pedido_a = PedidoFactory()
        pedido_b = PedidoFactory()
        self.assertNotEqual(pedido_a.token_acesso, pedido_b.token_acesso)


class ItensTotaisTests(TestCase):
    def test_subtotal_do_item_usa_preco_capturado(self):
        produto = ProdutoFactory(preco_online="25.00")
        item = ItemPedido(produto=produto, quantidade=Decimal("3"),
                          preco_unitario=Decimal("25.00"))
        self.assertEqual(item.subtotal, Decimal("75.00"))

    def test_recalcular_totais_soma_itens_e_frete(self):
        pedido = PedidoFactory(frete="10.00")
        ItemPedido.objects.create(
            pedido=pedido,
            produto=ProdutoFactory(preco_online="20.00"),
            produto_nome="X",
            quantidade=2,
            preco_unitario=Decimal("20.00"),
        )
        pedido.recalcular_totais()
        self.assertEqual(pedido.subtotal, Decimal("40.00"))
        self.assertEqual(pedido.total, Decimal("50.00"))


class PagamentoModelTests(TestCase):
    def test_pagamento_padrao_pendente_vinculado_ao_pedido(self):
        pagamento_factory_pedido = PedidoFactory()
        pagamento = Pagamento.objects.create(
            pedido=pagamento_factory_pedido, valor=Decimal("99.90")
        )
        self.assertEqual(pagamento.status, Pagamento.Status.PENDENTE)
        self.assertEqual(pagamento.pedido.numero, pagamento_factory_pedido.numero)
