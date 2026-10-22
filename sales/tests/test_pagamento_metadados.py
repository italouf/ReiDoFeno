"""E01/E02: correção de metadados legados é auditada, atômica e idempotente."""

from datetime import timedelta
from unittest import mock

from django.test import TestCase

from core.models import LogAuditoria
from sales.factories import PedidoFactory
from sales.models import Pagamento, Pedido
from sales.services import aplicar_resultado_pagamento


class CorrecaoMetadadosPagamentoTests(TestCase):
    def setUp(self):
        self.pedido = PedidoFactory(
            status=Pedido.Status.AGUARDANDO_PAGAMENTO,
            status_financeiro=Pedido.StatusFinanceiro.PAGO,
            financeiro_conciliado=True,
            total="20.00",
            subtotal="20.00",
            frete="0.00",
        )
        self.pagamento = Pagamento.objects.create(
            pedido=self.pedido,
            valor=self.pedido.total,
            status=Pagamento.Status.APROVADO,
            id_externo="",
            aprovado_em=None,
        )

    def _dados(self):
        return {
            "external_reference": self.pedido.numero,
            "status": "approved",
            "id": "pay-metadados",
            "transaction_amount": str(self.pedido.total),
            "currency_id": "BRL",
            "collector_id": "fake-collector",
            "live_mode": False,
        }

    def _aplicar(self):
        return aplicar_resultado_pagamento(
            self._dados(),
            id_consultado="pay-metadados",
        )

    def test_correcao_preenche_metadados_e_audita(self):
        self._aplicar()

        self.pagamento.refresh_from_db()
        self.assertEqual(self.pagamento.status, Pagamento.Status.APROVADO)
        self.assertEqual(self.pagamento.id_externo, "pay-metadados")
        self.assertIsNotNone(self.pagamento.aprovado_em)

        log = LogAuditoria.objects.get(
            acao="pedido.pagamento_aprovado_metadados_corrigidos",
            objeto_id=str(self.pedido.pk),
        )
        self.assertEqual(log.antes["id_externo"], "")
        self.assertIsNone(log.antes["aprovado_em"])
        self.assertEqual(log.depois["id_externo"], "pay-metadados")
        self.assertIsNotNone(log.depois["aprovado_em"])

    def test_reaplicacao_preserva_data_e_nao_duplica_correcao(self):
        self._aplicar()
        self.pagamento.refresh_from_db()
        primeira_data = self.pagamento.aprovado_em
        self.assertIsNotNone(primeira_data)

        with mock.patch(
            "django.utils.timezone.now",
            return_value=primeira_data + timedelta(days=1),
        ):
            self._aplicar()

        self.pagamento.refresh_from_db()
        self.assertEqual(self.pagamento.status, Pagamento.Status.APROVADO)
        self.assertEqual(self.pagamento.aprovado_em, primeira_data)
        self.assertEqual(
            LogAuditoria.objects.filter(
                acao="pedido.pagamento_aprovado_metadados_corrigidos",
                objeto_id=str(self.pedido.pk),
            ).count(),
            1,
        )

    def test_falha_na_auditoria_reverte_metadados(self):
        from core import auditoria as modulo_auditoria

        real = modulo_auditoria.registrar_auditoria

        def falhar_na_correcao(*args, **kwargs):
            if kwargs.get("acao") == (
                "pedido.pagamento_aprovado_metadados_corrigidos"
            ):
                raise RuntimeError("auditoria indisponível")
            return real(*args, **kwargs)

        with mock.patch(
            "core.auditoria.registrar_auditoria",
            side_effect=falhar_na_correcao,
        ):
            with self.assertRaises(RuntimeError):
                self._aplicar()

        self.pagamento.refresh_from_db()
        self.pedido.refresh_from_db()
        self.assertEqual(self.pagamento.status, Pagamento.Status.APROVADO)
        self.assertEqual(self.pagamento.id_externo, "")
        self.assertIsNone(self.pagamento.aprovado_em)
        self.assertTrue(self.pedido.financeiro_conciliado)
        self.assertFalse(
            LogAuditoria.objects.filter(
                acao="pedido.pagamento_aprovado_metadados_corrigidos",
                objeto_id=str(self.pedido.pk),
            ).exists()
        )
