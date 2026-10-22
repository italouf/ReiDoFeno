"""ADR-007: cancelamento padrão (24h) e devolução fiscal."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from accounts.models import Usuario
from catalog.factories import ProdutoFactory
from core.factories import UnidadeFactory
from fiscal.models import NotaFiscal
from sales.factories import ItemPedidoFactory, PagamentoFactory, PedidoFactory
from sales.models import Pagamento, Pedido
from sales.services import cancelar_pedido_padrao, registrar_devolucao
from stock.factories import EstoqueFactory
from stock.models import MovimentoEstoque


class BaseCancelamentoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_groups", verbosity=0)
        cls.admin = Usuario.objects.create_user(
            username="admin_cancel", password="senha-forte-123"
        )
        cls.admin.groups.add(Group.objects.get(name="Administrador"))

    def criar_pedido_pago(
        self, *, valor=Decimal("100.00"), aprovado_em=None,
        status=Pedido.Status.PAGO,
    ):
        pedido = PedidoFactory(
            status=status,
            subtotal=valor,
            total=valor,
        )
        PagamentoFactory(
            pedido=pedido,
            valor=valor,
            status=Pagamento.Status.APROVADO,
            aprovado_em=aprovado_em or timezone.now(),
        )
        return pedido


class CancelamentoPadraoTests(BaseCancelamentoTests):
    def test_cancelamento_padrao_dentro_24h(self):
        pedido = self.criar_pedido_pago(
            aprovado_em=timezone.now() - timedelta(hours=23)
        )

        cancelar_pedido_padrao(
            pedido=pedido,
            justificativa="Erro de digitação",
            usuario=self.admin,
        )

        pedido.refresh_from_db()
        self.assertEqual(pedido.status, Pedido.Status.CANCELADO)
        self.assertEqual(
            pedido.status_financeiro, Pedido.StatusFinanceiro.CANCELADO
        )
        self.assertEqual(pedido.tipo_cancelamento, "padrao")
        self.assertEqual(
            pedido.justificativa_cancelamento, "Erro de digitação"
        )
        self.assertEqual(pedido.cancelado_por, self.admin)
        self.assertIsNotNone(pedido.cancelado_em)

        pagamento = Pagamento.objects.get(pedido=pedido)
        self.assertEqual(pagamento.status, Pagamento.Status.CANCELADO)
        self.assertIsNotNone(pagamento.estornado_em)

    def test_cancelamento_padrao_bloqueado_apos_24h(self):
        pedido = self.criar_pedido_pago(
            aprovado_em=timezone.now() - timedelta(hours=25)
        )

        with pytest.raises(ValidationError, match="24 horas"):
            cancelar_pedido_padrao(
                pedido=pedido,
                justificativa="Cliente desistiu",
                usuario=self.admin,
            )

    def test_cancelamento_padrao_bloqueado_se_enviado(self):
        pedido = self.criar_pedido_pago(status=Pedido.Status.ENVIADO)

        with pytest.raises(ValidationError, match="enviado"):
            cancelar_pedido_padrao(
                pedido=pedido,
                justificativa="Erro",
                usuario=self.admin,
            )

    def test_cancelamento_padrao_exige_justificativa(self):
        pedido = self.criar_pedido_pago()

        with pytest.raises(ValidationError, match="Justificativa"):
            cancelar_pedido_padrao(
                pedido=pedido,
                justificativa="   ",
                usuario=self.admin,
            )

    def test_cancelamento_padrao_devolve_estoque_baixado(self):
        produto = ProdutoFactory(custo=Decimal("10.00"))
        unidade = UnidadeFactory()
        estoque = EstoqueFactory(
            produto=produto, unidade=unidade, quantidade=Decimal("10.00")
        )
        pedido = self.criar_pedido_pago()
        pedido.unidade = unidade
        pedido.save(update_fields=["unidade"])
        ItemPedidoFactory(
            pedido=pedido, produto=produto, quantidade=5,
            preco_unitario=Decimal("20.00"),
        )

        cancelar_pedido_padrao(
            pedido=pedido,
            justificativa="Mercadoria não saiu",
            usuario=self.admin,
        )

        estoque.refresh_from_db()
        self.assertEqual(estoque.quantidade, Decimal("15.00"))
        self.assertTrue(
            MovimentoEstoque.objects.filter(
                produto=produto,
                unidade=unidade,
                tipo=MovimentoEstoque.Tipo.ENTRADA_DEVOLUCAO,
                delta=Decimal("5.00"),
            ).exists()
        )


class DevolucaoTests(BaseCancelamentoTests):
    def _pedido_com_nfe(self):
        pedido = self.criar_pedido_pago(
            aprovado_em=timezone.now() - timedelta(days=5)
        )
        NotaFiscal.objects.create(
            pedido=pedido,
            tipo=NotaFiscal.Tipo.SAIDA,
            status=NotaFiscal.Status.AUTORIZADA,
            cfop="5.102",
            chave_acesso="29260812345678901234567890123456789012345678",
        )
        return pedido

    def test_devolucao_gera_nfe_entrada(self):
        pedido = self._pedido_com_nfe()

        nfe_entrada = registrar_devolucao(
            pedido=pedido,
            justificativa="Produto com defeito",
            usuario=self.admin,
        )

        self.assertEqual(nfe_entrada.tipo, NotaFiscal.Tipo.ENTRADA)
        self.assertEqual(nfe_entrada.cfop, "1.202")
        self.assertEqual(
            nfe_entrada.chave_referenciada,
            "29260812345678901234567890123456789012345678",
        )
        pedido.refresh_from_db()
        self.assertEqual(pedido.tipo_cancelamento, "devolucao")
        self.assertEqual(
            pedido.justificativa_cancelamento, "Produto com defeito"
        )

    def test_devolucao_retorna_estoque(self):
        produto = ProdutoFactory(custo=Decimal("10.00"))
        unidade = UnidadeFactory()
        estoque = EstoqueFactory(
            produto=produto, unidade=unidade, quantidade=Decimal("10.00")
        )
        pedido = self._pedido_com_nfe()
        pedido.unidade = unidade
        pedido.save(update_fields=["unidade"])
        ItemPedidoFactory(
            pedido=pedido, produto=produto, quantidade=5,
            preco_unitario=Decimal("20.00"),
        )

        registrar_devolucao(
            pedido=pedido,
            justificativa="Devolução",
            usuario=self.admin,
        )

        estoque.refresh_from_db()
        self.assertEqual(estoque.quantidade, Decimal("15.00"))

    def test_devolucao_exige_nfe_saida(self):
        pedido = self.criar_pedido_pago(
            aprovado_em=timezone.now() - timedelta(days=2)
        )

        with pytest.raises(ValidationError, match="NF-e de saída"):
            registrar_devolucao(
                pedido=pedido,
                justificativa="Devolução",
                usuario=self.admin,
            )

    def test_devolucao_estorna_pagamento(self):
        pedido = self._pedido_com_nfe()

        registrar_devolucao(
            pedido=pedido,
            justificativa="Devolução",
            usuario=self.admin,
        )

        pagamento = Pagamento.objects.get(pedido=pedido)
        self.assertEqual(pagamento.status, Pagamento.Status.CANCELADO)
        self.assertIsNotNone(pagamento.estornado_em)
        pedido.refresh_from_db()
        self.assertEqual(
            pedido.status_financeiro, Pedido.StatusFinanceiro.ESTORNADO
        )
