"""R01/R02: concorrência fiscal real em PostgreSQL."""
import threading
import unittest
from decimal import Decimal
from unittest import mock

import pytest
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.db import IntegrityError, close_old_connections, connection, transaction
from django.test import Client, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Usuario
from fiscal.models import NotaFiscal
from fiscal.services import pedido_elegivel
from sales.factories import PagamentoFactory, PedidoFactory
from sales.models import Pagamento, Pedido
from sales.services import cancelar_pedido_padrao

pytestmark = pytest.mark.postgres

CHAVE = "29260812345678901234567890123456789012345678"


class FiscalConcurrencyTests(TransactionTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if connection.vendor != "postgresql":
            raise unittest.SkipTest("Concorrência fiscal exige PostgreSQL.")

    @classmethod
    def setUpTestData(cls):
        call_command("seed_groups", verbosity=0)
        cls.gestor = Usuario.objects.create_user(
            username="gestor_fiscal_conc", password="senha-forte-123"
        )
        cls.gestor.groups.add(Group.objects.get(name="Administrador"))

    def _pedido(self):
        pedido = PedidoFactory(
            status=Pedido.Status.PAGO,
            status_financeiro=Pedido.StatusFinanceiro.PAGO,
            financeiro_conciliado=True,
            subtotal=Decimal("100.00"),
            total=Decimal("100.00"),
        )
        PagamentoFactory(
            pedido=pedido,
            valor=Decimal("100.00"),
            status=Pagamento.Status.APROVADO,
            aprovado_em=timezone.now(),
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

    def test_r02_duas_notas_nao_confirmam_a_mesma_chave(self):
        pedido1 = self._pedido()
        pedido2 = self._pedido()
        barreira = threading.Barrier(2)
        resultados = []

        def criar(pedido):
            close_old_connections()
            try:
                barreira.wait(timeout=10)
                with transaction.atomic():
                    NotaFiscal.objects.create(
                        pedido=pedido,
                        tipo=NotaFiscal.Tipo.SAIDA,
                        status=NotaFiscal.Status.AUTORIZADA,
                        chave_acesso=CHAVE,
                    )
                resultados.append("ok")
            except IntegrityError:
                resultados.append("conflito")
            except Exception as erro:  # pragma: no cover - diagnóstico
                resultados.append(erro)
            finally:
                close_old_connections()

        self._rodar(
            [
                threading.Thread(target=criar, args=(pedido1,)),
                threading.Thread(target=criar, args=(pedido2,)),
            ]
        )

        self.assertEqual(sorted(resultados), ["conflito", "ok"])
        self.assertEqual(
            NotaFiscal.objects.filter(chave_acesso=CHAVE).count(), 1
        )

    def test_r01_registro_primeiro_serializa_com_cancelamento(self):
        pedido = self._pedido()
        pedido_id = pedido.pk
        entrou = threading.Event()
        liberar = threading.Event()
        resposta = []
        erros = []
        chamadas = {"n": 0}

        def elegivel_com_pausa(pedido_arg):
            chamadas["n"] += 1
            if chamadas["n"] == 1:
                entrou.set()
                liberar.wait(timeout=10)
            return pedido_elegivel(pedido_arg)

        def registrar():
            close_old_connections()
            client = Client()
            client.force_login(self.gestor)
            try:
                with mock.patch(
                    "fiscal.services.pedido_elegivel",
                    side_effect=elegivel_com_pausa,
                ):
                    resposta.append(
                        client.post(
                            reverse(
                                "fiscal:nota_manual", args=[pedido_id]
                            ),
                            {
                                "numero": "R01",
                                "chave_acesso": CHAVE,
                            },
                        )
                    )
            except Exception as erro:  # pragma: no cover - diagnóstico
                erros.append(erro)
            finally:
                close_old_connections()

        def cancelar():
            close_old_connections()
            try:
                cancelar_pedido_padrao(
                    pedido=Pedido.objects.get(pk=pedido_id),
                    justificativa="Cancelamento concorrente R01",
                    usuario=self.gestor,
                )
            except Exception as erro:  # pragma: no cover - diagnóstico
                erros.append(erro)
            finally:
                close_old_connections()

        thread_registro = threading.Thread(target=registrar)
        thread_registro.start()
        self.assertTrue(entrou.wait(timeout=10))
        thread_cancelamento = threading.Thread(target=cancelar)
        thread_cancelamento.start()
        liberar.set()
        self._rodar([thread_registro, thread_cancelamento])

        self.assertFalse(erros, erros)
        self.assertEqual(resposta[0].status_code, 302)
        nota = NotaFiscal.objects.get(
            pedido_id=pedido_id, tipo=NotaFiscal.Tipo.SAIDA
        )
        self.assertEqual(nota.status, NotaFiscal.Status.CANCELADA)
        self.assertEqual(
            Pedido.objects.get(pk=pedido_id).status,
            Pedido.Status.CANCELADO,
        )
