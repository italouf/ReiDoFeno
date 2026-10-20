"""R1/PAY-02: contrato financeiro completo antes de qualquer mutação."""

import json
from decimal import Decimal

from django.test import TestCase, override_settings
from django.urls import reverse

from core.models import LogAuditoria
from sales.models import (
    Pagamento,
    PagamentoWebhookEvento,
    Pedido,
)
from sales.services import (
    ResultadoPagamentoInvalido,
    aplicar_resultado_pagamento,
)
from stock.models import Estoque

from .helpers import fluxo_checkout


@override_settings(MERCADO_PAGO_COLLECTOR_ID="collector-teste")
class ContratoPagamentoTests(TestCase):
    def setUp(self):
        self.pedido = fluxo_checkout(self.client, quantidade=2)
        self.pagamento = Pagamento.objects.create(
            pedido=self.pedido, valor=self.pedido.total
        )

    def _dados(self, **overrides):
        dados = {
            "external_reference": self.pedido.numero,
            "status": "approved",
            "id": "pay-ok",
            "transaction_amount": str(self.pedido.total),
            "currency_id": "BRL",
            "collector_id": "collector-teste",
            "live_mode": False,
        }
        dados.update(overrides)
        return dados

    def _aplicar(self, **overrides):
        return aplicar_resultado_pagamento(
            self._dados(**overrides),
            id_consultado=overrides.get("id_consultado", "pay-ok"),
        )

    def _assert_sem_mutacao(self):
        self.pedido.refresh_from_db()
        self.pagamento.refresh_from_db()
        item = self.pedido.itens.first()
        estoque = Estoque.objects.get(
            produto=item.produto, unidade=self.pedido.unidade
        )
        self.assertEqual(
            self.pedido.status_financeiro, Pedido.StatusFinanceiro.PENDENTE
        )
        self.assertEqual(self.pagamento.status, Pagamento.Status.PENDENTE)
        self.assertEqual(estoque.quantidade, Decimal("100"))
        self.assertEqual(estoque.quantidade_bloqueada, Decimal("2"))
        self.assertTrue(
            LogAuditoria.objects.filter(
                acao="pedido.pagamento_contrato_invalido",
                objeto_id=str(self.pedido.pk),
            ).exists()
        )

    def test_contrato_valido_aprova_e_baixa_estoque(self):
        self._aplicar()

        self.pedido.refresh_from_db()
        self.pagamento.refresh_from_db()
        self.assertEqual(
            self.pedido.status_financeiro, Pedido.StatusFinanceiro.PAGO
        )
        self.assertEqual(self.pagamento.status, Pagamento.Status.APROVADO)
        self.assertEqual(self.pagamento.id_externo, "pay-ok")

    def test_valor_divergente_nao_altera_nada(self):
        with self.assertRaises(ResultadoPagamentoInvalido):
            self._aplicar(transaction_amount="0.01")
        self._assert_sem_mutacao()

    def test_moeda_divergente_nao_altera_nada(self):
        with self.assertRaises(ResultadoPagamentoInvalido):
            self._aplicar(currency_id="USD")
        self._assert_sem_mutacao()

    def test_recebedor_divergente_nao_altera_nada(self):
        with self.assertRaises(ResultadoPagamentoInvalido):
            self._aplicar(collector_id="outra-conta")
        self._assert_sem_mutacao()

    def test_id_retornado_difere_do_consultado(self):
        with self.assertRaises(ResultadoPagamentoInvalido):
            aplicar_resultado_pagamento(
                self._dados(), id_consultado="pay-outro"
            )
        self._assert_sem_mutacao()

    def test_id_difere_da_tentativa_local(self):
        self.pagamento.id_externo = "pay-local"
        self.pagamento.save(update_fields=["id_externo"])
        with self.assertRaises(ResultadoPagamentoInvalido):
            self._aplicar()
        self._assert_sem_mutacao()

    def test_sem_tentativa_local_e_invalido(self):
        self.pagamento.delete()
        with self.assertRaises(ResultadoPagamentoInvalido):
            self._aplicar()
        self.pedido.refresh_from_db()
        self.assertEqual(
            self.pedido.status_financeiro, Pedido.StatusFinanceiro.PENDENTE
        )
        self.assertTrue(
            LogAuditoria.objects.filter(
                acao="pedido.pagamento_contrato_invalido",
                objeto_id=str(self.pedido.pk),
            ).exists()
        )

    def test_tentativa_local_com_valor_divergente_e_invalida(self):
        self.pagamento.valor = "1.00"
        self.pagamento.save(update_fields=["valor"])

        with self.assertRaises(ResultadoPagamentoInvalido):
            self._aplicar()

        self.pedido.refresh_from_db()
        self.assertEqual(
            self.pedido.status_financeiro, Pedido.StatusFinanceiro.PENDENTE
        )
        self.assertTrue(
            LogAuditoria.objects.filter(
                acao="pedido.pagamento_contrato_invalido",
                objeto_id=str(self.pedido.pk),
            ).exists()
        )

    def test_live_mode_divergente_nao_altera_nada(self):
        with self.assertRaises(ResultadoPagamentoInvalido):
            self._aplicar(live_mode=True)
        self._assert_sem_mutacao()

    def test_evento_negativo_divergente_nao_cancela(self):
        with self.assertRaises(ResultadoPagamentoInvalido):
            self._aplicar(status="refused", transaction_amount="0.01")
        self._assert_sem_mutacao()


class WebhookContratoTests(TestCase):
    def test_webhook_com_valor_divergente_nao_altera_e_registra_evento(self):
        pedido = fluxo_checkout(self.client, quantidade=2)
        Pagamento.objects.create(pedido=pedido, valor=pedido.total)
        data_id = f"fake-pay-{pedido.numero}-ok"
        payload = {"data": {"id": data_id}}

        from unittest import mock

        from sales.payments import MercadoPagoFake

        dados_invalidos = {
            "id": data_id,
            "status": "approved",
            "external_reference": pedido.numero,
            "transaction_amount": "0.01",
            "currency_id": "BRL",
            "collector_id": "fake-collector",
            "live_mode": False,
        }
        with mock.patch.object(
            MercadoPagoFake,
            "consultar_pagamento",
            return_value=dados_invalidos,
        ):
            resposta = self.client.post(
                reverse("sales:webhook"),
                data=json.dumps(payload),
                content_type="application/json",
            )

        self.assertEqual(resposta.status_code, 200)
        pedido.refresh_from_db()
        self.assertEqual(
            pedido.status_financeiro, Pedido.StatusFinanceiro.PENDENTE
        )
        evento = PagamentoWebhookEvento.objects.get(
            referencia_externa=data_id
        )
        self.assertFalse(evento.processado)
        self.assertIn("valor divergente", evento.erro)
        self.assertTrue(
            LogAuditoria.objects.filter(
                acao="pedido.pagamento_contrato_invalido",
                objeto_id=str(pedido.pk),
            ).exists()
        )

    def test_query_e_body_com_ids_divergentes_sao_rejeitados(self):
        resposta = self.client.post(
            reverse("sales:webhook") + "?data.id=111",
            data=json.dumps({"data": {"id": "222"}}),
            content_type="application/json",
        )

        self.assertEqual(resposta.status_code, 400)
        self.assertEqual(PagamentoWebhookEvento.objects.count(), 0)
