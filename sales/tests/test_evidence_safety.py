"""U01-U03: evidência, concorrência e conciliação histórica."""

import threading
import time
import unittest
from decimal import Decimal
from io import StringIO
from unittest import mock

import pytest
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import (
    DatabaseError,
    close_old_connections,
    connection,
    connections,
    transaction,
)
from django.db.models.deletion import ProtectedError
from django.test import TestCase, TransactionTestCase

from accounts.models import Usuario
from catalog.factories import ProdutoFactory
from core.factories import UnidadeFactory
from sales.factories import ItemPedidoFactory, PedidoFactory
from sales.models import ObrigacaoEstoquePedido, Pagamento, Pedido
from sales.obrigacoes import reconstruir_obrigacao_evidencia
from sales.services import (
    marcar_pagamento_aprovado,
    resolver_pendencia_estoque,
)
from stock.factories import EstoqueFactory
from stock.models import Estoque, MovimentoEstoque
from stock.services import registrar_movimento


def _aplicar_reconstrucao(obrigacao):
    dados = reconstruir_obrigacao_evidencia(
        obrigacao, Pedido=Pedido, Movimento=MovimentoEstoque
    )
    for campo, valor in dados.items():
        setattr(obrigacao, campo, valor)
    obrigacao.save()
    obrigacao.refresh_from_db()
    return dados


class RebuildRaceTests(TransactionTestCase):
    """U01: reparo concorrente não pode sobrescrever baixa confirmada."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if connection.vendor != "postgresql":
            raise unittest.SkipTest("Concorrência exige PostgreSQL.")

    def setUp(self):
        self.produto = ProdutoFactory(preco_online="10.00")
        self.unidade = UnidadeFactory(nome="Unidade U01")
        EstoqueFactory(
            produto=self.produto,
            unidade=self.unidade,
            quantidade="10.00",
            quantidade_bloqueada="0.00",
        )
        self.pedido = PedidoFactory(
            status=Pedido.Status.AGUARDANDO_PAGAMENTO,
            status_financeiro=Pedido.StatusFinanceiro.PENDENTE,
            financeiro_conciliado=False,
            unidade=self.unidade,
            subtotal="30.00",
            frete="0.00",
            total="30.00",
        )
        ItemPedidoFactory(
            pedido=self.pedido,
            produto=self.produto,
            quantidade=Decimal("3.00"),
            preco_unitario=Decimal("10.00"),
        )
        Pagamento.objects.create(
            pedido=self.pedido,
            valor=Decimal("30.00"),
            status=Pagamento.Status.PENDENTE,
            id_externo="pay-u01",
        )
        self.obrigacao = ObrigacaoEstoquePedido.objects.create(
            pedido=self.pedido,
            produto=self.produto,
            unidade=self.unidade,
            quantidade_devida=Decimal("3.00"),
            status=ObrigacaoEstoquePedido.Status.PENDENTE,
        )

    def test_rebuild_does_not_overwrite_concurrent_payment(self):
        comando_calculou = threading.Event()
        liberar_comando = threading.Event()
        aprovacao_tentou_lock = threading.Event()
        erros = []

        original_rebuild = (
            reconstruir_obrigacao_evidencia
        )

        def rebuild_pausado(*args, **kwargs):
            dados = original_rebuild(*args, **kwargs)
            comando_calculou.set()
            if not liberar_comando.wait(timeout=15):
                raise AssertionError("comando não foi liberado")
            return dados

        original_obter = __import__(
            "sales.services", fromlist=["_obter_obrigacao"]
        )._obter_obrigacao

        def obter_pausado(*args, **kwargs):
            aprovacao_tentou_lock.set()
            return original_obter(*args, **kwargs)

        def executar_comando():
            close_old_connections()
            try:
                with mock.patch(
                    "sales.management.commands."
                    "reconstruir_obrigacoes_estoque."
                    "reconstruir_obrigacao_evidencia",
                    side_effect=rebuild_pausado,
                ):
                    call_command(
                        "reconstruir_obrigacoes_estoque",
                        "--aplicar",
                        stdout=StringIO(),
                    )
            except Exception as erro:  # pragma: no cover - diagnóstico
                erros.append(erro)
            finally:
                close_old_connections()
                connections.close_all()

        def executar_aprovacao():
            close_old_connections()
            try:
                with mock.patch(
                    "sales.services._obter_obrigacao",
                    side_effect=obter_pausado,
                ):
                    marcar_pagamento_aprovado(
                        self.pedido, id_externo="pay-u01"
                    )
            except Exception as erro:  # pragma: no cover - diagnóstico
                erros.append(erro)
            finally:
                close_old_connections()
                connections.close_all()

        thread_comando = threading.Thread(target=executar_comando)
        thread_aprovacao = threading.Thread(target=executar_aprovacao)
        thread_comando.start()
        self.assertTrue(
            comando_calculou.wait(timeout=15),
            "o comando não chegou ao cálculo",
        )
        thread_aprovacao.start()
        self.assertTrue(
            aprovacao_tentou_lock.wait(timeout=15),
            "a aprovação não chegou ao lock da obrigação",
        )
        # Dá tempo para a aprovação terminar no código antigo, sem lock.
        time.sleep(0.5)
        liberar_comando.set()
        thread_comando.join(timeout=20)
        thread_aprovacao.join(timeout=20)
        self.assertFalse(thread_comando.is_alive())
        self.assertFalse(thread_aprovacao.is_alive())
        self.assertFalse(erros, erros)

        self.obrigacao.refresh_from_db()
        pedido = Pedido.objects.get(pk=self.pedido.pk)
        estoque = Estoque.objects.get(
            produto=self.produto, unidade=self.unidade
        )
        self.assertEqual(
            pedido.status_financeiro, Pedido.StatusFinanceiro.PAGO
        )
        self.assertEqual(
            self.obrigacao.status, ObrigacaoEstoquePedido.Status.RESOLVIDA
        )
        self.assertEqual(
            self.obrigacao.quantidade_baixada, Decimal("3.00")
        )
        self.assertEqual(self.obrigacao.evidencia_baixada, Decimal("3.00"))
        self.assertEqual(estoque.quantidade, Decimal("7.00"))
        self.assertEqual(
            MovimentoEstoque.objects.filter(
                produto=self.produto, unidade=self.unidade
            ).count(),
            1,
        )


class ImmutableAssignmentTests(TransactionTestCase):
    """U02: a FK de atribuição é parte da evidência imutável."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if connection.vendor != "postgresql":
            raise unittest.SkipTest("Trigger SQL exige PostgreSQL.")

    def setUp(self):
        self.produto = ProdutoFactory(preco_online="10.00")
        self.unidade = UnidadeFactory(nome="Unidade U02")
        EstoqueFactory(
            produto=self.produto,
            unidade=self.unidade,
            quantidade="10.00",
        )
        self.pedido_a = PedidoFactory(
            status=Pedido.Status.AGUARDANDO_PAGAMENTO,
            status_financeiro=Pedido.StatusFinanceiro.PENDENTE,
            financeiro_conciliado=False,
            unidade=self.unidade,
            subtotal="30.00",
            frete="0.00",
            total="30.00",
        )
        ItemPedidoFactory(
            pedido=self.pedido_a,
            produto=self.produto,
            quantidade=Decimal("3.00"),
            preco_unitario=Decimal("10.00"),
        )
        Pagamento.objects.create(
            pedido=self.pedido_a,
            valor=Decimal("30.00"),
            status=Pagamento.Status.PENDENTE,
            id_externo="pay-u02-a",
        )
        marcar_pagamento_aprovado(self.pedido_a, id_externo="pay-u02-a")
        self.obrigacao_a = ObrigacaoEstoquePedido.objects.get(
            pedido=self.pedido_a, produto=self.produto, unidade=self.unidade
        )
        self.movimento = MovimentoEstoque.objects.get(
            obrigacao=self.obrigacao_a
        )
        self.pedido_b = PedidoFactory(
            status=Pedido.Status.AGUARDANDO_PAGAMENTO,
            status_financeiro=Pedido.StatusFinanceiro.PENDENTE,
            financeiro_conciliado=False,
            unidade=self.unidade,
            subtotal="30.00",
            frete="0.00",
            total="30.00",
        )
        ItemPedidoFactory(
            pedido=self.pedido_b,
            produto=self.produto,
            quantidade=Decimal("3.00"),
            preco_unitario=Decimal("10.00"),
        )
        self.obrigacao_b = ObrigacaoEstoquePedido.objects.create(
            pedido=self.pedido_b,
            produto=self.produto,
            unidade=self.unidade,
            quantidade_devida=Decimal("3.00"),
            status=ObrigacaoEstoquePedido.Status.PENDENTE,
        )

    def test_movement_assignment_cannot_be_reassigned_or_removed_by_sql(self):
        with transaction.atomic():
            with pytest.raises(DatabaseError):
                with connection.cursor() as cursor:
                    cursor.execute(
                        "UPDATE stock_movimentoestoque "
                        "SET obrigacao_id = %s WHERE id = %s",
                        [self.obrigacao_b.pk, self.movimento.pk],
                    )
        self.movimento.refresh_from_db()
        self.assertEqual(self.movimento.obrigacao_id, self.obrigacao_a.pk)

        with transaction.atomic():
            with pytest.raises(DatabaseError):
                with connection.cursor() as cursor:
                    cursor.execute(
                        "UPDATE stock_movimentoestoque "
                        "SET obrigacao_id = NULL WHERE id = %s",
                        [self.movimento.pk],
                    )
        self.movimento.refresh_from_db()
        self.assertEqual(self.movimento.obrigacao_id, self.obrigacao_a.pk)

        with pytest.raises(ProtectedError):
            self.obrigacao_a.delete()

        dados_b = reconstruir_obrigacao_evidencia(
            self.obrigacao_b,
            Pedido=Pedido,
            Movimento=MovimentoEstoque,
        )
        self.assertEqual(
            dados_b["status"], ObrigacaoEstoquePedido.Status.PENDENTE
        )
        self.assertEqual(dados_b["quantidade_baixada"], Decimal("0.00"))


class EvidenceSemanticsTests(TestCase):
    """U03: falta, ambiguidade e excesso são estados diferentes."""

    def setUp(self):
        self.usuario = Usuario.objects.create_user(
            username="gestor-u03",
            password="senha-forte-123",
            is_superuser=True,
        )
        self.produto = ProdutoFactory(preco_online="10.00")
        self.unidade = UnidadeFactory(nome="Unidade U03")
        EstoqueFactory(
            produto=self.produto,
            unidade=self.unidade,
            quantidade="10.00",
        )

    def _pedido(self, status=Pedido.Status.AGUARDANDO_PAGAMENTO):
        pedido = PedidoFactory(
            status=status,
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
        return pedido

    def _obrigacao(self, pedido, quantidade="3.00"):
        return ObrigacaoEstoquePedido.objects.create(
            pedido=pedido,
            produto=self.produto,
            unidade=self.unidade,
            quantidade_devida=Decimal(quantidade),
            status=ObrigacaoEstoquePedido.Status.PENDENTE,
        )

    def _movimento(self, motivo, delta="-3.00"):
        return registrar_movimento(
            produto=self.produto,
            unidade=self.unidade,
            tipo=MovimentoEstoque.Tipo.BAIXA_DEFINITIVA,
            delta=Decimal(delta),
            motivo=motivo,
        )

    def test_pertinent_ambiguity_blocks_resolver(self):
        pedido = self._pedido()
        obrigacao = self._obrigacao(pedido)
        movimento = self._movimento(
            f"Baixa manual pedido {pedido.numero} e pedido PF999999"
        )
        dados = _aplicar_reconstrucao(obrigacao)
        self.assertEqual(dados.get("tipo_pendencia"), "ambigua")
        self.assertIn(movimento.pk, obrigacao.evidencia_detalhe["ambiguos"])

        with pytest.raises(ValidationError, match="concilia"):
            resolver_pendencia_estoque(
                obrigacao,
                usuario=self.usuario,
                justificativa="tentativa sem conciliar ambiguidade",
            )
        estoque = Estoque.objects.get(
            produto=self.produto, unidade=self.unidade
        )
        self.assertEqual(estoque.quantidade, Decimal("7.00"))
        self.assertEqual(
            MovimentoEstoque.objects.filter(obrigacao=obrigacao).count(), 0
        )

    def test_excess_blocks_resolver_until_explicit_decision(self):
        pedido = self._pedido()
        obrigacao = self._obrigacao(pedido)
        self._movimento(
            f"Baixa definitiva por pedido {pedido.numero}", delta="-4.00"
        )
        dados = _aplicar_reconstrucao(obrigacao)
        self.assertEqual(dados.get("tipo_pendencia"), "excesso")
        self.assertEqual(obrigacao.evidencia_baixada, Decimal("4.00"))
        self.assertEqual(obrigacao.quantidade_baixada, Decimal("3.00"))

        with pytest.raises(ValidationError, match="concilia"):
            resolver_pendencia_estoque(
                obrigacao,
                usuario=self.usuario,
                justificativa="tentativa de encerrar excesso",
            )
        obrigacao.refresh_from_db()
        self.assertEqual(
            obrigacao.status, ObrigacaoEstoquePedido.Status.PENDENTE
        )
        self.assertEqual(
            obrigacao.motivo_pendencia,
            "evidência histórica excede a obrigação; revisar",
        )

    def test_unrelated_ambiguous_motive_does_not_block(self):
        pedido = self._pedido()
        obrigacao = self._obrigacao(pedido)
        self._movimento("Baixa manual dos pedidos PF888888 e PF999999")
        dados = _aplicar_reconstrucao(obrigacao)
        self.assertEqual(dados.get("tipo_pendencia"), "falta")
        self.assertEqual(dados["evidencia_detalhe"]["ambiguos"], [])
        self.assertEqual(dados["quantidade_baixada"], Decimal("0.00"))

        resolver_pendencia_estoque(
            obrigacao,
            usuario=self.usuario,
            justificativa="não há ambiguidade pertinente",
        )
        estoque = Estoque.objects.get(
            produto=self.produto, unidade=self.unidade
        )
        obrigacao.refresh_from_db()
        self.assertEqual(estoque.quantidade, Decimal("4.00"))
        self.assertEqual(
            obrigacao.status, ObrigacaoEstoquePedido.Status.RESOLVIDA
        )

    def test_explicit_attribution_preserves_evidence_without_new_movement(self):
        from sales.services import conciliar_obrigacao_historica

        pedido = self._pedido()
        obrigacao = self._obrigacao(pedido)
        movimento = self._movimento(
            f"Baixa manual pedido {pedido.numero} e pedido PF999999"
        )
        _aplicar_reconstrucao(obrigacao)
        movimentos_antes = MovimentoEstoque.objects.count()

        conciliar_obrigacao_historica(
            obrigacao,
            decisao="atribuir",
            movimento_id=movimento.pk,
            usuario=self.usuario,
            justificativa="conferido no comprovante físico",
        )

        obrigacao.refresh_from_db()
        self.assertEqual(
            obrigacao.status, ObrigacaoEstoquePedido.Status.RESOLVIDA
        )
        self.assertEqual(obrigacao.quantidade_baixada, Decimal("3.00"))
        self.assertEqual(obrigacao.evidencia_baixada, Decimal("3.00"))
        self.assertEqual(MovimentoEstoque.objects.count(), movimentos_antes)
        from core.models import LogAuditoria

        log = LogAuditoria.objects.filter(
            acao="pedido.estoque_evidencia_conciliada",
            objeto_id=str(pedido.pk),
        ).latest("pk")
        self.assertEqual(log.usuario_id, self.usuario.pk)
        self.assertEqual(log.depois["decisao"], "atribuir")
        self.assertEqual(log.depois["movimento_id"], movimento.pk)
        _aplicar_reconstrucao(obrigacao)
        self.assertEqual(
            obrigacao.status, ObrigacaoEstoquePedido.Status.RESOLVIDA
        )
        self.assertEqual(obrigacao.quantidade_baixada, Decimal("3.00"))

    def test_conciliation_command_is_dry_run_until_confirmed(self):
        pedido = self._pedido()
        obrigacao = self._obrigacao(pedido)
        movimento = self._movimento(
            f"Baixa manual pedido {pedido.numero} e pedido PF999999"
        )
        _aplicar_reconstrucao(obrigacao)
        argumentos = [
            str(obrigacao.pk),
            "--decisao",
            "atribuir",
            "--movimento",
            str(movimento.pk),
            "--usuario",
            self.usuario.username,
            "--justificativa",
            "conferência do comando",
        ]
        call_command(
            "conciliar_obrigacao_historica",
            *argumentos,
            stdout=StringIO(),
        )
        obrigacao.refresh_from_db()
        self.assertEqual(
            obrigacao.status, ObrigacaoEstoquePedido.Status.PENDENTE
        )
        call_command(
            "conciliar_obrigacao_historica",
            *argumentos,
            "--confirmar",
            stdout=StringIO(),
        )
        obrigacao.refresh_from_db()
        self.assertEqual(
            obrigacao.status, ObrigacaoEstoquePedido.Status.RESOLVIDA
        )

    def test_explicit_excess_acceptance_is_auditable_and_idempotent(self):
        from sales.services import conciliar_obrigacao_historica

        pedido = self._pedido()
        obrigacao = self._obrigacao(pedido)
        self._movimento(
            f"Baixa definitiva por pedido {pedido.numero}", delta="-4.00"
        )
        _aplicar_reconstrucao(obrigacao)
        movimentos_antes = MovimentoEstoque.objects.count()

        conciliar_obrigacao_historica(
            obrigacao,
            decisao="aceitar_excesso",
            usuario=self.usuario,
            justificativa="diferença conferida e aceita pela operação",
        )

        obrigacao.refresh_from_db()
        self.assertEqual(
            obrigacao.status, ObrigacaoEstoquePedido.Status.RESOLVIDA
        )
        self.assertEqual(obrigacao.evidencia_baixada, Decimal("4.00"))
        self.assertEqual(obrigacao.quantidade_baixada, Decimal("3.00"))
        self.assertEqual(obrigacao.motivo_pendencia, "")
        self.assertEqual(MovimentoEstoque.objects.count(), movimentos_antes)
        _aplicar_reconstrucao(obrigacao)
        self.assertEqual(
            obrigacao.status, ObrigacaoEstoquePedido.Status.RESOLVIDA
        )
