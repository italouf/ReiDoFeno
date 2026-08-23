from datetime import timedelta

from django.core import mail
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from sales.models import Pedido
from stock.models import Estoque

from .helpers import fluxo_checkout


class ExpiracaoPedidosTests(TestCase):
    def _envelhecer(self, pedido, minutos=300):
        antigo = timezone.now() - timedelta(minutes=minutos)
        Pedido.objects.filter(pk=pedido.pk).update(criado_em=antigo)

    def test_pedido_antigo_e_cancelado_e_reserva_liberada(self):
        pedido = fluxo_checkout(self.client, quantidade=5)
        self._envelhecer(pedido)
        mail.outbox.clear()

        call_command("expirar_pedidos", verbosity=0)

        pedido.refresh_from_db()
        item = pedido.itens.first()
        estoque = Estoque.objects.get(
            produto=item.produto, unidade=pedido.unidade
        )
        self.assertEqual(pedido.status, Pedido.Status.CANCELADO)
        self.assertEqual(estoque.quantidade_bloqueada, 0)
        # E-mail de cancelamento enviado
        self.assertTrue(
            any("cancelado" in email.subject for email in mail.outbox)
        )

    def test_pedido_recente_nao_e_cancelado(self):
        pedido = fluxo_checkout(self.client, quantidade=2)

        call_command("expirar_pedidos", verbosity=0)

        pedido.refresh_from_db()
        self.assertEqual(
            pedido.status, Pedido.Status.AGUARDANDO_PAGAMENTO
        )

    def test_pedidos_pagos_nunca_sao_expirados(self):
        pedido = fluxo_checkout(self.client, quantidade=2)
        pedido.transicionar(Pedido.Status.PAGO)
        self._envelhecer(pedido)

        call_command("expirar_pedidos", verbosity=0)

        pedido.refresh_from_db()
        self.assertEqual(pedido.status, Pedido.Status.PAGO)

    def test_idempotente(self):
        pedido = fluxo_checkout(self.client, quantidade=1)
        self._envelhecer(pedido)
        call_command("expirar_pedidos", verbosity=0)
        call_command("expirar_pedidos", verbosity=0)  # segunda passada: nada a fazer
        pedido.refresh_from_db()
        self.assertEqual(Pedido.objects.filter(status=Pedido.Status.CANCELADO).count(), 1)
