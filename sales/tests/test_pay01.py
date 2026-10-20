"""PAY-01: assinatura de webhook conforme contrato e modo real seguro."""

import hashlib
import hmac
import time

from django.test import SimpleTestCase, override_settings

from sales.payments import validar_assinatura_webhook

SEGREDO = "segredo-pay01"


def _assinatura(data_id, *, ts=None, request_id="req-1", segredo=SEGREDO):
    ts = str(int(time.time())) if ts is None else str(ts)
    manifest = f"id:{data_id};request-id:{request_id};ts:{ts};"
    v1 = hmac.new(
        segredo.encode(), manifest.encode(), hashlib.sha256
    ).hexdigest()
    return ts, v1


@override_settings(
    MERCADO_PAGO_WEBHOOK_SECRET=SEGREDO,
    MERCADO_PAGO_FAKE=False,
    MERCADO_PAGO_WEBHOOK_TOLERANCE_SECONDS=300,
)
class AssinaturaWebhookTests(SimpleTestCase):
    def _validar(self, *, data_id="123", ts=None, formato=",", adulterar=False):
        ts, v1 = _assinatura(data_id, ts=ts)
        if adulterar:
            v1 = ("0" * 64) if v1[0] != "0" else ("1" * 64)
        header = f"ts={ts}{formato}v1={v1}"
        return validar_assinatura_webhook(
            {"x-signature": header, "x-request-id": "req-1"},
            data_id,
        )

    def test_formato_oficial_com_virgula_e_aceito(self):
        self.assertTrue(self._validar(data_id="123", formato=","))

    def test_formato_legado_com_ponto_e_virgula_tambem_e_aceito(self):
        self.assertTrue(self._validar(data_id="123", formato=";"))

    def test_assinatura_adulterada_e_rejeitada(self):
        self.assertFalse(self._validar(data_id="123", adulterar=True))

    def test_assinatura_sem_request_id_e_rejeitada(self):
        ts, v1 = _assinatura("123")
        self.assertFalse(
            validar_assinatura_webhook(
                {"x-signature": f"ts={ts},v1={v1}"},
                "123",
            )
        )

    def test_timestamp_expirado_e_rejeitado(self):
        antigo = int(time.time()) - 600
        self.assertFalse(self._validar(data_id="123", ts=antigo))

    def test_timestamp_futuro_alem_da_tolerancia_e_rejeitado(self):
        futuro = int(time.time()) + 600
        self.assertFalse(self._validar(data_id="123", ts=futuro))

    def test_data_id_com_caracteres_invalidos_e_rejeitado(self):
        self.assertFalse(self._validar(data_id="../etc/passwd"))

    def test_data_id_vazio_e_rejeitado(self):
        self.assertFalse(self._validar(data_id=""))


@override_settings(
    MERCADO_PAGO_WEBHOOK_SECRET="",
    MERCADO_PAGO_FAKE=False,
)
class ModoRealSemSegredoTests(SimpleTestCase):
    def test_notificacao_sem_segredo_e_rejeitada(self):
        self.assertFalse(validar_assinatura_webhook({}, "123"))


@override_settings(
    MERCADO_PAGO_WEBHOOK_SECRET="",
    MERCADO_PAGO_FAKE=True,
)
class ModoFakeSemSegredoTests(SimpleTestCase):
    def test_notificacao_sem_segredo_e_aceita_em_fake(self):
        self.assertTrue(validar_assinatura_webhook({}, "123"))
