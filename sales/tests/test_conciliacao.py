"""Conciliação financeira manual (CONCILIACAO)."""

import uuid
from decimal import Decimal

from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Usuario
from catalog.factories import ProdutoFactory
from core.factories import UnidadeFactory
from core.models import LogAuditoria
from customers.factories import ClienteFactory
from sales.factories import ItemPedidoFactory, PedidoFactory
from sales.models import ComprovantePagamento, Pagamento, Pedido
from sales.services import cancelar_pedido, registrar_pagamento_manual
from stock.factories import EstoqueFactory
from stock.models import Estoque, MovimentoEstoque
from stock.services import reservar


class ConciliacaoBaseTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_groups", verbosity=0)
        cls.senha = "senha-forte-123"
        cls.vendedor = Usuario.objects.create_user(
            username="vendedor", password=cls.senha
        )
        cls.vendedor.groups.add(Group.objects.get(name="Vendedor"))
        cls.financeiro = Usuario.objects.create_user(
            username="financeiro", password=cls.senha
        )
        cls.financeiro.groups.add(Group.objects.get(name="Financeiro"))
        cls.outro_financeiro = Usuario.objects.create_user(
            username="outro-financeiro", password=cls.senha
        )
        cls.outro_financeiro.groups.add(Group.objects.get(name="Financeiro"))

    def criar_pedido(self, *, total="100.00", usuario_criador=None):
        cliente = ClienteFactory()
        unidade = UnidadeFactory()
        produto = ProdutoFactory(preco_online="10.00", custo="5.00")
        EstoqueFactory(
            produto=produto,
            unidade=unidade,
            quantidade="100.00",
            quantidade_bloqueada="0.00",
        )
        pedido = PedidoFactory(
            cliente=cliente,
            unidade=unidade,
            usuario_criador=usuario_criador or self.vendedor,
            status=Pedido.Status.AGUARDANDO_PAGAMENTO,
            status_financeiro=Pedido.StatusFinanceiro.PENDENTE,
        )
        item = ItemPedidoFactory(
            pedido=pedido,
            produto=produto,
            quantidade=Decimal(total) / Decimal("10.00"),
            preco_unitario=Decimal("10.00"),
            custo_unitario=Decimal("5.00"),
        )
        pedido.recalcular_totais()
        reservar(
            produto=produto,
            unidade=unidade,
            quantidade=item.quantidade,
            pedido=pedido,
            item_pedido=item,
        )
        return pedido

    def registrar_pagamento(self, pedido, *, valor=None, usuario=None):
        return registrar_pagamento_manual(
            pedido,
            metodo=ComprovantePagamento.Metodo.PIX,
            valor=valor or pedido.total,
            data_pagamento=timezone.now(),
            referencia=f"E{uuid.uuid4().hex}",
            usuario=usuario or self.vendedor,
        )

    def criar_pedido_pago_manual(self, **kwargs):
        pedido = self.criar_pedido(**kwargs)
        self.registrar_pagamento(pedido)
        pedido.refresh_from_db()
        return pedido


class ConciliacaoTests(ConciliacaoBaseTests):
    def test_responsavel_financeiro_concilia_pedido(self):
        pedido = self.criar_pedido_pago_manual()
        self.assertFalse(pedido.financeiro_conciliado)
        self.client.force_login(self.financeiro)

        resposta = self.client.post(
            reverse("sales:conciliar_pedido", args=[pedido.pk])
        )

        self.assertEqual(resposta.status_code, 302)
        pedido.refresh_from_db()
        self.assertTrue(pedido.financeiro_conciliado)
        comprovante = pedido.comprovantes.get()
        self.assertEqual(
            comprovante.status, ComprovantePagamento.Status.CONCILIADO
        )
        log = LogAuditoria.objects.filter(
            acao="pedido_conciliado",
            objeto_id=str(pedido.pk),
        ).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.usuario, self.financeiro)
        self.assertEqual(
            log.depois["comprovantes_conciliados"], [comprovante.pk]
        )

    def test_responsavel_financeiro_rejeita_pedido(self):
        pedido = self.criar_pedido_pago_manual()
        self.client.force_login(self.financeiro)

        resposta = self.client.post(
            reverse("sales:rejeitar_pedido", args=[pedido.pk]),
            {"justificativa": "Comprovante inválido"},
        )

        self.assertEqual(resposta.status_code, 302)
        pedido.refresh_from_db()
        self.assertEqual(
            pedido.status_financeiro, Pedido.StatusFinanceiro.PENDENTE
        )
        self.assertFalse(pedido.financeiro_conciliado)
        comprovante = pedido.comprovantes.get()
        self.assertEqual(
            comprovante.status, ComprovantePagamento.Status.REJEITADO
        )
        pagamento = Pagamento.objects.get(pedido=pedido)
        self.assertEqual(pagamento.status, Pagamento.Status.CANCELADO)
        self.assertIsNone(pagamento.aprovado_em)
        self.assertIsNone(pagamento.estornado_em)
        log = LogAuditoria.objects.filter(
            acao="pedido_rejeitado_conciliacao",
            objeto_id=str(pedido.pk),
        ).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.usuario, self.financeiro)
        self.assertEqual(log.depois["justificativa"], "Comprovante inválido")

    def test_rejeicao_remove_receita_provisoria_sem_gerar_estorno(self):
        from analytics.services import (
            pagamentos_estornados,
            receita_do_periodo,
        )

        pedido = self.criar_pedido_pago_manual()
        self.client.force_login(self.financeiro)
        self.client.post(
            reverse("sales:rejeitar_pedido", args=[pedido.pk]),
            {"justificativa": "PIX não identificado no extrato"},
        )

        hoje = timezone.localdate()
        self.assertEqual(receita_do_periodo(hoje, hoje), Decimal("0.00"))
        self.assertFalse(
            pagamentos_estornados(hoje, hoje)
            .filter(pedido=pedido)
            .exists()
        )

    def test_cancelamento_apos_rejeicao_devolve_estoque(self):
        pedido = self.criar_pedido_pago_manual()
        self.client.force_login(self.financeiro)
        self.client.post(
            reverse("sales:rejeitar_pedido", args=[pedido.pk]),
            {"justificativa": "Comprovante inválido"},
        )
        pedido.refresh_from_db()
        item = pedido.itens.select_related("produto").first()
        estoque = Estoque.objects.get(
            produto=item.produto, unidade=pedido.unidade
        )
        self.assertEqual(estoque.quantidade, Decimal("90.00"))

        cancelar_pedido(pedido, usuario=self.financeiro)

        pedido.refresh_from_db()
        estoque.refresh_from_db()
        self.assertEqual(pedido.status, Pedido.Status.CANCELADO)
        self.assertEqual(estoque.quantidade, Decimal("100.00"))
        self.assertEqual(estoque.quantidade_bloqueada, Decimal("0.00"))
        self.assertTrue(
            MovimentoEstoque.objects.filter(
                obrigacao__pedido=pedido,
                tipo=MovimentoEstoque.Tipo.ENTRADA_DEVOLUCAO,
            ).exists()
        )

    def test_rejeicao_sem_justificativa_e_rejeitada(self):
        pedido = self.criar_pedido_pago_manual()
        self.client.force_login(self.financeiro)

        resposta = self.client.post(
            reverse("sales:rejeitar_pedido", args=[pedido.pk]),
            {"justificativa": "  "},
        )

        self.assertEqual(resposta.status_code, 400)
        pedido.refresh_from_db()
        self.assertEqual(
            pedido.status_financeiro, Pedido.StatusFinanceiro.PAGO
        )
        self.assertEqual(
            pedido.comprovantes.get().status,
            ComprovantePagamento.Status.PENDENTE,
        )

    def test_vendedor_nao_acessa_conciliacao(self):
        pedido = self.criar_pedido_pago_manual()
        self.client.force_login(self.vendedor)

        self.assertEqual(
            self.client.get(reverse("sales:conciliacao_list")).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                reverse("sales:conciliar_pedido", args=[pedido.pk])
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                reverse("sales:rejeitar_pedido", args=[pedido.pk]),
                {"justificativa": "tentativa"},
            ).status_code,
            403,
        )

    def test_criador_nao_concilia_proprio_pedido(self):
        pedido = self.criar_pedido_pago_manual(usuario_criador=self.financeiro)
        self.client.force_login(self.financeiro)

        resposta = self.client.post(
            reverse("sales:conciliar_pedido", args=[pedido.pk])
        )

        self.assertEqual(resposta.status_code, 403)
        pedido.refresh_from_db()
        self.assertFalse(pedido.financeiro_conciliado)

    def test_listagem_mostra_apenas_pendentes(self):
        pedido_pendente = self.criar_pedido_pago_manual()
        pedido_conciliado = self.criar_pedido_pago_manual()
        pedido_conciliado.financeiro_conciliado = True
        pedido_conciliado.save(update_fields=["financeiro_conciliado"])
        pedido_nao_pago = self.criar_pedido()

        self.client.force_login(self.financeiro)
        resposta = self.client.get(reverse("sales:conciliacao_list"))

        pedidos = list(resposta.context["pedidos"])
        self.assertIn(pedido_pendente, pedidos)
        self.assertNotIn(pedido_conciliado, pedidos)
        self.assertNotIn(pedido_nao_pago, pedidos)

    def test_conciliar_sem_comprovante_suficiente_e_rejeitado(self):
        pedido = PedidoFactory(
            status_financeiro=Pedido.StatusFinanceiro.PAGO,
            financeiro_conciliado=False,
            subtotal="100.00",
            total="100.00",
        )
        self.client.force_login(self.financeiro)

        resposta = self.client.post(
            reverse("sales:conciliar_pedido", args=[pedido.pk])
        )

        self.assertEqual(resposta.status_code, 400)
        pedido.refresh_from_db()
        self.assertFalse(pedido.financeiro_conciliado)

    def test_rejeitar_pedido_ja_conciliado_e_rejeitado(self):
        pedido = self.criar_pedido_pago_manual()
        pedido.financeiro_conciliado = True
        pedido.save(update_fields=["financeiro_conciliado"])
        self.client.force_login(self.financeiro)

        resposta = self.client.post(
            reverse("sales:rejeitar_pedido", args=[pedido.pk]),
            {"justificativa": "Tentativa tardia"},
        )

        self.assertEqual(resposta.status_code, 400)
        pedido.refresh_from_db()
        self.assertEqual(
            pedido.status_financeiro, Pedido.StatusFinanceiro.PAGO
        )

    def test_conciliacao_idempotente(self):
        pedido = self.criar_pedido_pago_manual()
        self.client.force_login(self.financeiro)

        self.client.post(reverse("sales:conciliar_pedido", args=[pedido.pk]))
        resposta = self.client.post(
            reverse("sales:conciliar_pedido", args=[pedido.pk])
        )

        self.assertEqual(resposta.status_code, 302)
        pedido.refresh_from_db()
        self.assertTrue(pedido.financeiro_conciliado)
        self.assertEqual(
            LogAuditoria.objects.filter(
                acao="pedido_conciliado", objeto_id=str(pedido.pk)
            ).count(),
            1,
        )

    def test_comprovante_rejeitado_nao_conta_para_novo_pagamento(self):
        pedido = self.criar_pedido_pago_manual()
        self.client.force_login(self.financeiro)
        self.client.post(
            reverse("sales:rejeitar_pedido", args=[pedido.pk]),
            {"justificativa": "Comprovante inválido"},
        )

        pedido.refresh_from_db()
        self.assertEqual(pedido.saldo_devedor, Decimal("100.00"))

        self.registrar_pagamento(pedido, valor=Decimal("50.00"))
        pedido.refresh_from_db()
        self.assertEqual(
            pedido.status_financeiro, Pedido.StatusFinanceiro.PENDENTE
        )
        self.assertEqual(pedido.saldo_devedor, Decimal("50.00"))

        self.registrar_pagamento(pedido, valor=Decimal("50.00"))
        pedido.refresh_from_db()
        self.assertEqual(pedido.status_financeiro, Pedido.StatusFinanceiro.PAGO)
        self.assertEqual(pedido.saldo_devedor, Decimal("0.00"))
