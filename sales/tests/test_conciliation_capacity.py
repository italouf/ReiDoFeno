"""C01: uma saída histórica não pode cumprir dois pedidos."""

import threading
import unittest
from decimal import Decimal
from io import StringIO

import pytest
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import close_old_connections, connection, connections
from django.test import TestCase, TransactionTestCase

from accounts.models import Usuario
from catalog.factories import ProdutoFactory
from core.factories import UnidadeFactory
from sales.factories import ItemPedidoFactory, PedidoFactory
from sales.models import ObrigacaoEstoquePedido, Pedido
from sales.services import (
    conciliar_obrigacao_historica,
    resolver_pendencia_estoque,
)
from stock.factories import EstoqueFactory
from stock.models import Estoque, MovimentoEstoque
from stock.services import registrar_movimento


class ConciliationCapacityTests(TestCase):
    def setUp(self):
        self.usuario = Usuario.objects.create_user(
            username="gestor-c01",
            password="senha-forte-123",
            is_superuser=True,
        )
        self.produto = ProdutoFactory(preco_online="10.00")
        self.unidade = UnidadeFactory(nome="Unidade C01")
        EstoqueFactory(
            produto=self.produto,
            unidade=self.unidade,
            quantidade="10.00",
        )

    def _pedido(self):
        pedido = PedidoFactory(
            status=Pedido.Status.AGUARDANDO_PAGAMENTO,
            status_financeiro=Pedido.StatusFinanceiro.PAGO,
            financeiro_conciliado=True,
            unidade=self.unidade,
            subtotal="30.00",
            frete="0.00",
            total="30.00",
        )
        ItemPedidoFactory(
            pedido=pedido,
            produto=self.produto,
            quantidade=Decimal("3.00"),
            preco_unitario=Decimal("10.00"),
        )
        obrigacao = ObrigacaoEstoquePedido.objects.create(
            pedido=pedido,
            produto=self.produto,
            unidade=self.unidade,
            quantidade_devida=Decimal("3.00"),
            status=ObrigacaoEstoquePedido.Status.PENDENTE,
            tipo_pendencia=ObrigacaoEstoquePedido.TipoPendencia.FALTA,
        )
        return pedido, obrigacao

    def _movimento_ambiguo(self, pedido_a, pedido_b):
        return registrar_movimento(
            produto=self.produto,
            unidade=self.unidade,
            tipo=MovimentoEstoque.Tipo.BAIXA_DEFINITIVA,
            delta=Decimal("-3.00"),
            motivo=(
                f"Baixa manual pedidos {pedido_a.numero} e {pedido_b.numero}"
            ),
        )

    def _reconstruir(self):
        call_command(
            "reconstruir_obrigacoes_estoque",
            "--aplicar",
            stdout=StringIO(),
        )

    def _comando(self, obrigacao, movimento, decisao="atribuir"):
        call_command(
            "conciliar_obrigacao_historica",
            str(obrigacao.pk),
            "--decisao",
            decisao,
            "--movimento",
            str(movimento.pk),
            "--usuario",
            self.usuario.username,
            "--justificativa",
            "conferência C01",
            "--confirmar",
            stdout=StringIO(),
        )

    def test_one_historical_exit_cannot_fulfill_two_orders(self):
        pedido_a, obrigacao_a = self._pedido()
        pedido_b, obrigacao_b = self._pedido()
        movimento = self._movimento_ambiguo(pedido_a, pedido_b)
        self._reconstruir()

        self._comando(obrigacao_a, movimento)
        with pytest.raises(ValidationError, match="aloc|evid"):
            self._comando(obrigacao_b, movimento)

        self._reconstruir()
        obrigacao_a.refresh_from_db()
        obrigacao_b.refresh_from_db()
        movimento.refresh_from_db()
        estoque = Estoque.objects.get(
            produto=self.produto, unidade=self.unidade
        )
        self.assertEqual(
            obrigacao_a.status, ObrigacaoEstoquePedido.Status.RESOLVIDA
        )
        self.assertEqual(
            obrigacao_b.status, ObrigacaoEstoquePedido.Status.PENDENTE
        )
        self.assertEqual(obrigacao_b.evidencia_baixada, Decimal("0.00"))
        self.assertEqual(estoque.quantidade, Decimal("7.00"))
        self.assertIsNone(movimento.obrigacao_id)

        from stock.models import AlocacaoEvidenciaEstoque

        alocacoes = AlocacaoEvidenciaEstoque.objects.filter(
            movimento=movimento
        )
        self.assertEqual(alocacoes.count(), 1)
        self.assertEqual(alocacoes.get().obrigacao_id, obrigacao_a.pk)

    def _json_atribuicao(self, obrigacao, movimento):
        detalhe = dict(obrigacao.evidencia_detalhe or {})
        conciliacoes = list(detalhe.get("conciliacoes", []))
        conciliacoes.append(
            {
                "decisao": "atribuir",
                "movimento_id": movimento.pk,
                "quantidade": "3.00",
                "usuario_id": self.usuario.pk,
                "justificativa": "decisão JSON legada",
            }
        )
        detalhe["conciliacoes"] = conciliacoes
        obrigacao.evidencia_detalhe = detalhe
        obrigacao.status = ObrigacaoEstoquePedido.Status.RESOLVIDA
        obrigacao.quantidade_baixada = Decimal("3.00")
        obrigacao.evidencia_baixada = Decimal("3.00")
        obrigacao.save()

    @staticmethod
    def _converter_json_legado():
        from importlib import import_module

        from django.apps import apps

        modulo = import_module(
            "stock.migrations.0011_alocacao_evidencia"
        )
        modulo.converter_decisoes_json(apps, None)

    def test_json_conversion_creates_one_global_allocation(self):
        pedido_a, obrigacao = self._pedido()
        pedido_b, _obrigacao_b = self._pedido()
        self._json_atribuicao(
            obrigacao, self._movimento_ambiguo(pedido_a, pedido_b)
        )
        self._converter_json_legado()
        self._converter_json_legado()
        from stock.models import AlocacaoEvidenciaEstoque

        self.assertEqual(
            AlocacaoEvidenciaEstoque.objects.filter(
                obrigacao=obrigacao
            ).count(),
            1,
        )

    def test_json_conflict_is_diagnosed_and_not_silently_owned(self):
        pedido_a, obrigacao_a = self._pedido()
        pedido_b, obrigacao_b = self._pedido()
        movimento = self._movimento_ambiguo(pedido_a, pedido_b)
        self._json_atribuicao(obrigacao_a, movimento)
        self._json_atribuicao(obrigacao_b, movimento)
        self._converter_json_legado()

        from stock.models import AlocacaoEvidenciaEstoque

        self.assertFalse(
            AlocacaoEvidenciaEstoque.objects.filter(
                movimento=movimento
            ).exists()
        )
        for obrigacao in (obrigacao_a, obrigacao_b):
            obrigacao.refresh_from_db()
            self.assertEqual(
                obrigacao.status, ObrigacaoEstoquePedido.Status.PENDENTE
            )
            self.assertEqual(obrigacao.tipo_pendencia, "ambigua")
            self.assertIn(
                movimento.pk,
                obrigacao.evidencia_detalhe["conflitos_alocacao"],
            )
            self.assertEqual(
                obrigacao.quantidade_baixada, Decimal("0.00")
            )

    def test_conciliation_audit_failure_rolls_back_allocation(self):
        from unittest import mock

        pedido_a, obrigacao = self._pedido()
        pedido_b, _obrigacao_b = self._pedido()
        movimento = self._movimento_ambiguo(pedido_a, pedido_b)
        self._reconstruir()

        with mock.patch(
            "core.auditoria.registrar_auditoria",
            side_effect=RuntimeError("auditoria indisponível"),
        ):
            with pytest.raises(RuntimeError):
                conciliar_obrigacao_historica(
                    obrigacao,
                    decisao="atribuir",
                    movimento_id=movimento.pk,
                    usuario=self.usuario,
                    justificativa="tentativa com falha de auditoria",
                )

        from stock.models import AlocacaoEvidenciaEstoque

        self.assertFalse(
            AlocacaoEvidenciaEstoque.objects.filter(
                movimento=movimento
            ).exists()
        )
        obrigacao.refresh_from_db()
        self.assertEqual(
            obrigacao.status, ObrigacaoEstoquePedido.Status.PENDENTE
        )
        self.assertEqual(obrigacao.quantidade_baixada, Decimal("0.00"))

    def test_reject_for_one_order_then_assign_other_is_valid(self):
        pedido_a, obrigacao_a = self._pedido()
        pedido_b, obrigacao_b = self._pedido()
        movimento = self._movimento_ambiguo(pedido_a, pedido_b)
        self._reconstruir()

        self._comando(obrigacao_a, movimento, decisao="descartar")
        self._comando(obrigacao_b, movimento, decisao="atribuir")
        obrigacao_a.refresh_from_db()
        self.assertEqual(
            obrigacao_a.status, ObrigacaoEstoquePedido.Status.PENDENTE
        )
        self.assertEqual(obrigacao_a.tipo_pendencia, "falta")

        resolver_pendencia_estoque(
            obrigacao_a,
            usuario=self.usuario,
            justificativa="nova saída física conferida",
        )

        obrigacao_a.refresh_from_db()
        obrigacao_b.refresh_from_db()
        estoque = Estoque.objects.get(
            produto=self.produto, unidade=self.unidade
        )
        self.assertEqual(
            obrigacao_a.status, ObrigacaoEstoquePedido.Status.RESOLVIDA
        )
        self.assertEqual(
            obrigacao_b.status, ObrigacaoEstoquePedido.Status.RESOLVIDA
        )
        self.assertEqual(estoque.quantidade, Decimal("4.00"))
        self.assertEqual(
            MovimentoEstoque.objects.filter(
                produto=self.produto, unidade=self.unidade
            ).count(),
            2,
        )


class ConcurrentConciliationCapacityTests(TransactionTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if connection.vendor != "postgresql":
            raise unittest.SkipTest("Concorrência exige PostgreSQL.")

    def setUp(self):
        self.usuario = Usuario.objects.create_user(
            username="gestor-c01-concorrente",
            password="senha-forte-123",
            is_superuser=True,
        )
        self.produto = ProdutoFactory(preco_online="10.00")
        self.unidade = UnidadeFactory(nome="Unidade C01 concorrente")
        EstoqueFactory(
            produto=self.produto,
            unidade=self.unidade,
            quantidade="10.00",
        )
        self.pedido_a = PedidoFactory(
            status=Pedido.Status.AGUARDANDO_PAGAMENTO,
            status_financeiro=Pedido.StatusFinanceiro.PAGO,
            financeiro_conciliado=True,
            unidade=self.unidade,
            subtotal="30.00",
            frete="0.00",
            total="30.00",
        )
        self.pedido_b = PedidoFactory(
            status=Pedido.Status.AGUARDANDO_PAGAMENTO,
            status_financeiro=Pedido.StatusFinanceiro.PAGO,
            financeiro_conciliado=True,
            unidade=self.unidade,
            subtotal="30.00",
            frete="0.00",
            total="30.00",
        )
        for pedido in (self.pedido_a, self.pedido_b):
            ItemPedidoFactory(
                pedido=pedido,
                produto=self.produto,
                quantidade=Decimal("3.00"),
                preco_unitario=Decimal("10.00"),
            )
        self.obrigacao_a = ObrigacaoEstoquePedido.objects.create(
            pedido=self.pedido_a,
            produto=self.produto,
            unidade=self.unidade,
            quantidade_devida=Decimal("3.00"),
            status=ObrigacaoEstoquePedido.Status.PENDENTE,
            tipo_pendencia=ObrigacaoEstoquePedido.TipoPendencia.FALTA,
        )
        self.obrigacao_b = ObrigacaoEstoquePedido.objects.create(
            pedido=self.pedido_b,
            produto=self.produto,
            unidade=self.unidade,
            quantidade_devida=Decimal("3.00"),
            status=ObrigacaoEstoquePedido.Status.PENDENTE,
            tipo_pendencia=ObrigacaoEstoquePedido.TipoPendencia.FALTA,
        )
        self.movimento = registrar_movimento(
            produto=self.produto,
            unidade=self.unidade,
            tipo=MovimentoEstoque.Tipo.BAIXA_DEFINITIVA,
            delta=Decimal("-3.00"),
            motivo=(
                f"Baixa manual pedidos {self.pedido_a.numero} "
                f"e {self.pedido_b.numero}"
            ),
        )
        call_command(
            "reconstruir_obrigacoes_estoque",
            "--aplicar",
            stdout=StringIO(),
        )

    def test_concurrent_attribution_cannot_reuse_the_same_exit(self):
        barreira = threading.Barrier(2)
        erros = []
        sucessos = []

        def atribuir(obrigacao):
            close_old_connections()
            try:
                barreira.wait(timeout=10)
                conciliar_obrigacao_historica(
                    obrigacao,
                    decisao="atribuir",
                    movimento_id=self.movimento.pk,
                    usuario=self.usuario,
                    justificativa="conferência concorrente C01",
                )
                sucessos.append(obrigacao.pk)
            except Exception as erro:  # pragma: no cover - diagnóstico
                erros.append(erro)
            finally:
                close_old_connections()
                connections.close_all()

        threads = [
            threading.Thread(target=atribuir, args=(self.obrigacao_a,)),
            threading.Thread(target=atribuir, args=(self.obrigacao_b,)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=20)
            self.assertFalse(thread.is_alive())
        self.assertEqual(len(sucessos), 1, (sucessos, erros))
        self.assertEqual(len(erros), 1, (sucessos, erros))
        self.assertIsInstance(erros[0], ValidationError)

        self.obrigacao_a.refresh_from_db()
        self.obrigacao_b.refresh_from_db()
        self.movimento.refresh_from_db()
        estoque = Estoque.objects.get(
            produto=self.produto, unidade=self.unidade
        )
        resolvidas = [
            obrigacao
            for obrigacao in (self.obrigacao_a, self.obrigacao_b)
            if obrigacao.status == ObrigacaoEstoquePedido.Status.RESOLVIDA
        ]
        self.assertEqual(len(resolvidas), 1)
        self.assertEqual(estoque.quantidade, Decimal("7.00"))
        self.assertIsNone(self.movimento.obrigacao_id)

        from stock.models import AlocacaoEvidenciaEstoque

        self.assertEqual(
            AlocacaoEvidenciaEstoque.objects.filter(
                movimento=self.movimento
            ).count(),
            1,
        )
