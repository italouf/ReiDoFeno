"""N07: concorrência real em PostgreSQL para fluxos financeiros críticos."""

import threading
import unittest
from decimal import Decimal

import pytest
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import close_old_connections, connection
from django.test import Client, TransactionTestCase
from django.urls import reverse

from accounts.models import Usuario
from catalog.factories import ProdutoFactory
from core.factories import UnidadeFactory
from sales.factories import ItemPedidoFactory, PedidoFactory
from sales.models import Pagamento, Pedido
from sales.services import (
    alterar_status_operacional,
    aplicar_resultado_pagamento,
    cancelar_pedido,
    marcar_pagamento_aprovado,
)
from stock.factories import EstoqueFactory
from stock.models import Estoque, MovimentoEstoque, ReservaEstoque
from stock.services import reservar

pytestmark = pytest.mark.postgres


class PostgresConcurrencyTests(TransactionTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if connection.vendor != "postgresql":
            raise unittest.SkipTest("Concorrência nativa exige PostgreSQL.")

    def setUp(self):
        call_command("seed_groups", verbosity=0)
        self.gestor = Usuario.objects.create_user(
            username="gestor-concorrencia", password="senha-forte-123"
        )
        self.gestor.groups.add(Group.objects.get(name="Gestor"))
        self.produto = ProdutoFactory(preco_online="10.00")
        self.unidade = UnidadeFactory()
        EstoqueFactory(
            produto=self.produto,
            unidade=self.unidade,
            quantidade="10.00",
            quantidade_bloqueada=Decimal("2.00"),
        )

    def _pedido(self, *, com_pagamento=False):
        pedido = PedidoFactory(
            status=Pedido.Status.AGUARDANDO_PAGAMENTO,
            status_financeiro=Pedido.StatusFinanceiro.PENDENTE,
            financeiro_conciliado=False,
            unidade=self.unidade,
            subtotal="20.00",
            frete="0.00",
            total="20.00",
        )
        ItemPedidoFactory(
            pedido=pedido,
            produto=self.produto,
            quantidade=Decimal("2.00"),
            preco_unitario=Decimal("10.00"),
        )
        if com_pagamento:
            Pagamento.objects.create(
                pedido=pedido,
                valor=pedido.total,
                status=Pagamento.Status.PENDENTE,
                id_externo="pay-conc",
            )
        return pedido

    @staticmethod
    def _rodar(threads):
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=20)
            if thread.is_alive():
                raise AssertionError("thread não terminou")

    def test_cancelamento_vs_aprovacao_nao_duplica_efeito(self):
        pedido = self._pedido()
        erros = []

        def aprovar():
            close_old_connections()
            try:
                marcar_pagamento_aprovado(
                    pedido, id_externo="pay-conc"
                )
            except Exception as erro:  # captura para diagnóstico
                erros.append(erro)
            finally:
                close_old_connections()

        def cancelar():
            close_old_connections()
            try:
                cancelar_pedido(pedido)
            except Exception as erro:  # captura para diagnóstico
                erros.append(erro)
            finally:
                close_old_connections()

        self._rodar(
            [threading.Thread(target=aprovar), threading.Thread(target=cancelar)]
        )

        pedido.refresh_from_db()
        estoque = Estoque.objects.get(
            produto=self.produto, unidade=self.unidade
        )
        self.assertFalse(erros, erros)
        self.assertEqual(estoque.quantidade_bloqueada, Decimal("0"))
        self.assertIn(estoque.quantidade, (Decimal("8"), Decimal("10")))
        self.assertIn(
            pedido.status_financeiro,
            (
                Pedido.StatusFinanceiro.PAGO,
                Pedido.StatusFinanceiro.CANCELADO,
            ),
        )
        self.assertLessEqual(
            MovimentoEstoque.objects.filter(
                produto=self.produto, unidade=self.unidade
            ).count(),
            1,
        )

    def test_cancelamento_vs_aprovacao_com_reserva_vinculada(self):
        produto = ProdutoFactory(preco_online="10.00")
        unidade = UnidadeFactory(nome="Unidade Reserva Concorrente")
        EstoqueFactory(
            produto=produto, unidade=unidade, quantidade="10.00"
        )
        pedido = PedidoFactory(
            status=Pedido.Status.AGUARDANDO_PAGAMENTO,
            status_financeiro=Pedido.StatusFinanceiro.PENDENTE,
            financeiro_conciliado=False,
            unidade=unidade,
            subtotal="20.00",
            frete="0.00",
            total="20.00",
        )
        item = ItemPedidoFactory(
            pedido=pedido,
            produto=produto,
            quantidade=Decimal("2.00"),
            preco_unitario=Decimal("10.00"),
        )
        reserva = reservar(
            produto=produto,
            unidade=unidade,
            quantidade=Decimal("2.00"),
            pedido=pedido,
            item_pedido=item,
        )
        erros = []

        def aprovar():
            close_old_connections()
            try:
                marcar_pagamento_aprovado(pedido, id_externo="pay-reserva")
            except Exception as erro:
                erros.append(erro)
            finally:
                close_old_connections()

        def cancelar():
            close_old_connections()
            try:
                cancelar_pedido(pedido)
            except Exception as erro:
                erros.append(erro)
            finally:
                close_old_connections()

        self._rodar(
            [threading.Thread(target=aprovar), threading.Thread(target=cancelar)]
        )

        pedido.refresh_from_db()
        reserva.refresh_from_db()
        estoque = Estoque.objects.get(produto=produto, unidade=unidade)
        self.assertFalse(erros, erros)
        self.assertEqual(estoque.quantidade_bloqueada, Decimal("0"))
        self.assertIn(estoque.quantidade, (Decimal("8"), Decimal("10")))
        self.assertIn(
            pedido.status_financeiro,
            (
                Pedido.StatusFinanceiro.PAGO,
                Pedido.StatusFinanceiro.CANCELADO,
            ),
        )
        self.assertIn(
            reserva.status,
            (
                ReservaEstoque.Status.CONSUMIDA,
                ReservaEstoque.Status.LIBERADA,
            ),
        )
        self.assertLessEqual(
            MovimentoEstoque.objects.filter(
                produto=produto, unidade=unidade
            ).count(),
            1,
        )

    def test_avanco_vs_estorno_nao_libera_apos_estorno(self):
        pedido = self._pedido(com_pagamento=True)
        marcar_pagamento_aprovado(pedido, id_externo="pay-conc")
        erros = []

        def avancar():
            close_old_connections()
            try:
                alterar_status_operacional(
                    pedido.pk,
                    Pedido.Status.EM_SEPARACAO,
                    usuario=self.gestor,
                )
            except ValidationError:
                pass
            except Exception as erro:
                erros.append(erro)
            finally:
                close_old_connections()

        def estornar():
            close_old_connections()
            try:
                aplicar_resultado_pagamento(
                    {
                        "external_reference": pedido.numero,
                        "status": "refunded",
                        "id": "pay-conc",
                        "transaction_amount": str(pedido.total),
                        "currency_id": "BRL",
                        "collector_id": "fake-collector",
                        "live_mode": False,
                    },
                    id_consultado="pay-conc",
                )
            except Exception as erro:
                erros.append(erro)
            finally:
                close_old_connections()

        self._rodar(
            [threading.Thread(target=avancar), threading.Thread(target=estornar)]
        )

        pedido.refresh_from_db()
        self.assertFalse(erros, erros)
        self.assertEqual(
            pedido.status_financeiro, Pedido.StatusFinanceiro.ESTORNADO
        )
        self.assertIn(
            pedido.status,
            (Pedido.Status.EM_SEPARACAO, Pedido.Status.CANCELADO),
        )
        self.assertNotEqual(pedido.status, Pedido.Status.CONCLUIDO)

    def test_duas_criacoes_de_pagamento_reutilizam_uma_preferencia(self):
        pedido = self._pedido()
        barreira = threading.Barrier(2)
        chamadas = []
        lock = threading.Lock()
        erros = []

        def criar(pedido_arg, idempotency_key=None):
            with lock:
                chamadas.append(idempotency_key)
            return (
                f"pref-{pedido_arg.numero}",
                reverse(
                    "sales:simular_pagamento",
                    args=[pedido_arg.token_acesso],
                ),
            )

        from sales.payments import MercadoPagoFake

        def requisitar():
            close_old_connections()
            try:
                cliente = Client()
                barreira.wait(timeout=10)
                resposta = cliente.post(
                    reverse(
                        "sales:pagamento_iniciar",
                        args=[pedido.token_acesso],
                    )
                )
                if resposta.status_code not in (302, 429):
                    erros.append(f"status {resposta.status_code}")
            except Exception as erro:
                erros.append(erro)
            finally:
                close_old_connections()

        from unittest import mock

        with mock.patch.object(
            MercadoPagoFake, "criar_preferencia", side_effect=criar
        ):
            self._rodar(
                [threading.Thread(target=requisitar),
                 threading.Thread(target=requisitar)]
            )

        self.assertFalse(erros, erros)
        self.assertEqual(Pagamento.objects.filter(pedido=pedido).count(), 1)
        pagamento = Pagamento.objects.get(pedido=pedido)
        self.assertTrue(pagamento.preferencia_id)
        self.assertTrue(pagamento.init_point)
        self.assertEqual(len(chamadas), 1)
