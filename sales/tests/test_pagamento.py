import hashlib
import hmac
import json
from decimal import Decimal

from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from stock.models import Estoque

from ..models import Pagamento, PagamentoWebhookEvento, Pedido
from ..services import (
    aplicar_resultado_pagamento,
    marcar_pagamento_aprovado,
)
from .helpers import fluxo_checkout


def id_fake_aprovado(pedido) -> str:
    return f"fake-pay-{pedido.numero}-ok"


class FluxoPagamentoTests(TestCase):
    def _iniciar(self, pedido):
        resposta = self.client.get(
            reverse("sales:pagamento_iniciar", args=[pedido.token_acesso])
        )
        self.assertRedirects(
            resposta,
            reverse("sales:simular_pagamento", args=[pedido.token_acesso]),
            fetch_redirect_response=False,
        )

    def test_iniciar_pagamento_cria_preferencia_e_redireciona_ao_simulador(self):
        pedido = fluxo_checkout(self.client, quantidade=4)
        self._iniciar(pedido)
        pagamento = pedido.pagamento
        self.assertTrue(pagamento.preferencia_id.startswith("fake-pref-"))
        self.assertEqual(pagamento.valor, pedido.total)

    def test_aprovado_atualiza_pedido_e_baixa_estoque_definitivamente(self):
        pedido = fluxo_checkout(self.client, quantidade=4)
        self._iniciar(pedido)
        self.client.post(
            reverse("sales:simular_resultado", args=[pedido.token_acesso]),
            {"resultado": "aprovado"},
        )

        pedido.refresh_from_db()
        self.assertEqual(pedido.status, Pedido.Status.PAGO)
        saldo, bloqueada = _saldo(pedido)
        # 100 - 4 baixados; reserva zerada (virou baixa definitiva).
        self.assertEqual(saldo, Decimal("96.00"))
        self.assertEqual(bloqueada, Decimal("0"))
        pagamento = pedido.pagamento
        self.assertEqual(pagamento.status, Pagamento.Status.APROVADO)
        self.assertEqual(pagamento.id_externo, id_fake_aprovado(pedido))

    def test_email_de_aprovacao_e_enviado(self):
        pedido = fluxo_checkout(self.client, quantidade=2)
        mail.outbox.clear()
        self._iniciar(pedido)
        self.client.post(
            reverse("sales:simular_resultado", args=[pedido.token_acesso]),
            {"resultado": "aprovado"},
        )
        assuntos = [email.subject for email in mail.outbox]
        self.assertTrue(any("Pagamento aprovado" in a for a in assuntos), assuntos)

    def test_recusa_marca_falhou_e_libera_reserva(self):
        pedido = fluxo_checkout(self.client, quantidade=3)
        saldo_antes, _ = _saldo(pedido)
        self._iniciar(pedido)
        self.client.post(
            reverse("sales:simular_resultado", args=[pedido.token_acesso]),
            {"resultado": "recusado"},
        )
        pedido.refresh_from_db()
        saldo, bloqueada = _saldo(pedido)
        self.assertEqual(pedido.status, Pedido.Status.FALHOU)
        self.assertEqual(saldo, saldo_antes)  # reserva devolvida
        self.assertEqual(bloqueada, Decimal("0"))

    def test_aprovacao_duplicada_nao_duplica_baixa(self):
        pedido = fluxo_checkout(self.client, quantidade=5)
        dados = {
            "id": "pay-1",
            "status": "approved",
            "external_reference": pedido.numero,
        }
        marcar_pagamento_aprovado(pedido, id_externo="pay-1")
        aplicar_resultado_pagamento(dados)
        aplicar_resultado_pagamento(dados)

        saldo, _bloqueada = _saldo(pedido)
        self.assertEqual(saldo, Decimal("95"))

    def test_cancelamento_devolve_reserva(self):
        from ..services import cancelar_pedido

        pedido = fluxo_checkout(self.client, quantidade=7)
        saldo_antes, bloqueada_antes = _saldo(pedido)
        self.assertEqual(bloqueada_antes, Decimal("7"))

        cancelar_pedido(pedido)

        saldo, bloqueada = _saldo(pedido)
        pedido.refresh_from_db()
        self.assertEqual(pedido.status, Pedido.Status.CANCELADO)
        self.assertEqual(saldo, saldo_antes)      # nada baixado
        self.assertEqual(bloqueada, Decimal("0"))  # reserva devolvida

    def test_cancelamento_e_idempotente(self):
        from ..services import cancelar_pedido

        pedido = fluxo_checkout(self.client, quantidade=2)
        cancelar_pedido(pedido)
        cancelar_pedido(pedido)  # segunda chamada não levanta nem duplica
        saldo, bloqueada = _saldo(pedido)
        self.assertEqual(bloqueada, Decimal("0"))


class WebhookTests(TestCase):
    def _post_webhook(self, payload: dict, *, assinatura: str | None = None,
                      request_id: str = "req-1", ts: str = "1700000000"):
        headers = {}
        if assinatura is not None:
            headers["HTTP_X_SIGNATURE"] = f"ts={ts};v1={assinatura}"
            headers["HTTP_X_REQUEST_ID"] = request_id
        return self.client.post(
            reverse("sales:webhook"),
            data=json.dumps(payload),
            content_type="application/json",
            **headers,
        )

    @staticmethod
    def _v1(data_id: str, segredo: str, request_id="req-1", ts="1700000000"):
        manifest = f"id:{data_id};request-id:{request_id};ts:{ts};"
        return hmac.new(segredo.encode(), manifest.encode(), hashlib.sha256).hexdigest()

    @override_settings(MERCADO_PAGO_WEBHOOK_SECRET="")
    def test_webhook_aprovado_atualiza_pedido_e_reenvio_e_idempotente(self):
        pedido = fluxo_checkout(self.client, quantidade=6)
        data_id = id_fake_aprovado(pedido)
        payload = {"data": {"id": data_id}}

        for _ in range(2):  # provedor reenvia a mesma notificação
            resposta = self._post_webhook(payload)
            self.assertEqual(resposta.status_code, 200)

        pedido.refresh_from_db()
        self.assertEqual(pedido.status, Pedido.Status.PAGO)
        saldo, _bloqueada = _saldo(pedido)
        self.assertEqual(saldo, Decimal("94"))
        eventos = PagamentoWebhookEvento.objects.filter(
            referencia_externa=data_id
        )
        self.assertEqual(eventos.count(), 2)
        self.assertTrue(all(evento.processado for evento in eventos))
        # Aprovação gera exatamente um e-mail, mesmo com reenvio.
        aprovacoes = [
            email for email in mail.outbox if "Pagamento aprovado" in email.subject
        ]
        self.assertEqual(len(aprovacoes), 1)

    @override_settings(MERCADO_PAGO_WEBHOOK_SECRET="segredo-teste")
    def test_assinatura_invalida_rejeitada_sem_alterar_pedido(self):
        pedido = fluxo_checkout(self.client, quantidade=2)
        payload = {"data": {"id": id_fake_aprovado(pedido)}}

        resposta = self._post_webhook(
            payload,
            assinatura=self._v1(id_fake_aprovado(pedido), "segredo-errado"),
        )
        self.assertEqual(resposta.status_code, 403)
        pedido.refresh_from_db()
        self.assertNotEqual(pedido.status, Pedido.Status.PAGO)
        self.assertEqual(PagamentoWebhookEvento.objects.count(), 0)

    @override_settings(MERCADO_PAGO_WEBHOOK_SECRET="segredo-teste")
    def test_assinatura_valida_processa_notificacao(self):
        pedido = fluxo_checkout(self.client, quantidade=2)
        data_id = id_fake_aprovado(pedido)
        payload = {"data": {"id": data_id}}

        resposta = self._post_webhook(
            payload,
            assinatura=self._v1(data_id, "segredo-teste", request_id="req-9"),
            request_id="req-9",
        )
        self.assertEqual(resposta.status_code, 200)
        pedido.refresh_from_db()
        self.assertEqual(pedido.status, Pedido.Status.PAGO)


def _saldo(pedido):
    item = pedido.itens.select_related("produto").first()
    estoque = Estoque.objects.get(produto=item.produto, unidade=pedido.unidade)
    return estoque.quantidade, estoque.quantidade_bloqueada
