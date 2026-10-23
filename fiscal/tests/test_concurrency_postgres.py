"""R01/R02: concorrência fiscal real em PostgreSQL."""
import threading
import unittest
from datetime import timedelta
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
from analytics.models import Aviso
from fiscal.client import ErroFiscal
from fiscal.models import NotaFiscal
from fiscal.services import enviar_para_emissao, pedido_elegivel
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

    def setUp(self):
        call_command("seed_groups", verbosity=0)
        self.gestor = Usuario.objects.create_user(
            username="gestor_fiscal_conc", password="senha-forte-123"
        )
        self.gestor.groups.add(Group.objects.get(name="Administrador"))

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

    @staticmethod
    def _juntar(threads):
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
            try:
                client = Client()
                client.force_login(self.gestor)
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
        try:
            chegou = entrou.wait(timeout=10)
        finally:
            if not entrou.is_set():
                liberar.set()
        self.assertTrue(chegou, f"thread de registro não chegou: {erros}")
        thread_cancelamento = threading.Thread(target=cancelar)
        thread_cancelamento.start()
        liberar.set()
        self._juntar([thread_registro, thread_cancelamento])

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

    CHAVE_MANUAL_L01 = "29260811111111111111111111111111111111111111"
    CHAVE_API_L01 = "29260822222222222222222222222222222222222222"
    CHAVE_API_B_L01 = "29260833333333333333333333333333333333333333"

    def _nota_em_erro(self, pedido):
        return NotaFiscal.objects.create(
            pedido=pedido,
            tipo=NotaFiscal.Tipo.SAIDA,
            status=NotaFiscal.Status.ERRO,
            cfop="5.102",
        )

    def _post_manual(self, pedido):
        return self.client.post(
            reverse("fiscal:nota_manual", args=[pedido.pk]),
            {
                "numero": "MANUAL",
                "chave_acesso": self.CHAVE_MANUAL_L01,
                "link_documento": "https://exemplo.com/manual.pdf",
            },
        )

    def _iniciar_emissao_pausada(self, pedido, *, erro):
        entrou = threading.Event()
        liberar = threading.Event()
        resultados = []
        erros = []
        chave_api = self.CHAVE_API_L01

        class ClientePausado:
            def criar_nfe(self, pedido_arg):
                entrou.set()
                if not liberar.wait(timeout=10):
                    raise AssertionError("emissão pausada não foi liberada")
                if erro:
                    raise ErroFiscal("falha da tentativa antiga")
                return {
                    "numero": "API-A",
                    "chave": chave_api,
                    "link": "https://exemplo.com/api-a",
                }

        def executar():
            close_old_connections()
            try:
                resultados.append(
                    enviar_para_emissao(
                        Pedido.objects.get(pk=pedido.pk),
                        client=ClientePausado(),
                    )
                )
            except Exception as exc:  # pragma: no cover - diagnóstico
                erros.append(exc)
            finally:
                close_old_connections()

        thread = threading.Thread(target=executar)
        thread.start()
        if not entrou.wait(timeout=10):
            liberar.set()
            thread.join(timeout=10)
            self.fail(f"emissão não entrou no cliente simulado: {erros}")
        return {
            "thread": thread,
            "liberar": liberar,
            "resultados": resultados,
            "erros": erros,
        }

    def test_l01_manual_bloqueado_durante_lease_ativo_postgres(self):
        pedido = self._pedido()
        nota = self._nota_em_erro(pedido)
        self.client.force_login(self.gestor)
        contexto = self._iniciar_emissao_pausada(pedido, erro=False)
        try:
            resposta = self._post_manual(pedido)
            self.assertEqual(resposta.status_code, 200)
            self.assertContains(resposta, "emissão automática em andamento")
            nota.refresh_from_db()
            self.assertEqual(nota.status, NotaFiscal.Status.PENDENTE)
            self.assertIsNotNone(nota.tentativa_atual)
        finally:
            contexto["liberar"].set()
            self._juntar([contexto["thread"]])

        self.assertFalse(contexto["erros"], contexto["erros"])
        nota.refresh_from_db()
        self.assertEqual(nota.status, NotaFiscal.Status.AUTORIZADA)
        self.assertEqual(nota.numero, "API-A")
        self.assertEqual(nota.chave_acesso, self.CHAVE_API_L01)
        self.assertEqual(nota.origem, NotaFiscal.Origem.API)

    def test_l01_erro_antigo_nao_rebaixa_manual_postgres(self):
        pedido = self._pedido()
        nota = self._nota_em_erro(pedido)
        self.client.force_login(self.gestor)
        contexto = self._iniciar_emissao_pausada(pedido, erro=True)
        try:
            NotaFiscal.objects.filter(pk=nota.pk).update(
                processando_desde=timezone.now() - timedelta(minutes=3)
            )
            resposta = self._post_manual(pedido)
            self.assertEqual(resposta.status_code, 302)
        finally:
            contexto["liberar"].set()
            self._juntar([contexto["thread"]])

        self.assertFalse(contexto["erros"], contexto["erros"])
        nota.refresh_from_db()
        self.assertEqual(nota.status, NotaFiscal.Status.AUTORIZADA)
        self.assertEqual(nota.numero, "MANUAL")
        self.assertEqual(nota.chave_acesso, self.CHAVE_MANUAL_L01)
        self.assertEqual(nota.origem, NotaFiscal.Origem.MANUAL)
        self.assertEqual(
            nota.resultado_externo["eventos"][-1]["tipo"], "erro"
        )
        self.assertTrue(
            Aviso.objects.filter(
                tipo=Aviso.Tipo.FISCAL_ERRO,
                objeto_id=str(nota.pk),
            ).exists()
        )

    def test_l01_sucesso_antigo_nao_substitui_manual_postgres(self):
        pedido = self._pedido()
        nota = self._nota_em_erro(pedido)
        self.client.force_login(self.gestor)
        contexto = self._iniciar_emissao_pausada(pedido, erro=False)
        try:
            NotaFiscal.objects.filter(pk=nota.pk).update(
                processando_desde=timezone.now() - timedelta(minutes=3)
            )
            resposta = self._post_manual(pedido)
            self.assertEqual(resposta.status_code, 302)
        finally:
            contexto["liberar"].set()
            self._juntar([contexto["thread"]])

        self.assertFalse(contexto["erros"], contexto["erros"])
        nota.refresh_from_db()
        self.assertEqual(nota.status, NotaFiscal.Status.AUTORIZADA)
        self.assertEqual(nota.numero, "MANUAL")
        self.assertEqual(nota.chave_acesso, self.CHAVE_MANUAL_L01)
        self.assertEqual(nota.origem, NotaFiscal.Origem.MANUAL)
        self.assertEqual(
            nota.resultado_externo["eventos"][-1]["tipo"], "sucesso"
        )
        self.assertEqual(
            nota.resultado_externo["eventos"][-1]["resultado"]["numero"],
            "API-A",
        )

    def test_l01_erro_antigo_nao_desfaz_sucesso_de_b_postgres(self):
        pedido = self._pedido()
        nota = self._nota_em_erro(pedido)
        contexto = self._iniciar_emissao_pausada(pedido, erro=True)
        try:
            NotaFiscal.objects.filter(pk=nota.pk).update(
                processando_desde=timezone.now() - timedelta(minutes=3)
            )
            chave_b = self.CHAVE_API_B_L01

            class ClienteB:
                def criar_nfe(self, pedido_b):
                    return {
                        "numero": "API-B",
                        "chave": chave_b,
                        "link": "https://exemplo.com/api-b",
                    }

            enviar_para_emissao(
                Pedido.objects.get(pk=pedido.pk), client=ClienteB()
            )
            nota.refresh_from_db()
            self.assertEqual(nota.status, NotaFiscal.Status.AUTORIZADA)
            self.assertEqual(nota.numero, "API-B")
        finally:
            contexto["liberar"].set()
            self._juntar([contexto["thread"]])

        self.assertFalse(contexto["erros"], contexto["erros"])
        nota.refresh_from_db()
        self.assertEqual(nota.status, NotaFiscal.Status.AUTORIZADA)
        self.assertEqual(nota.numero, "API-B")
        self.assertEqual(nota.chave_acesso, self.CHAVE_API_B_L01)
        self.assertEqual(
            nota.resultado_externo["eventos"][-1]["tipo"], "erro"
        )
