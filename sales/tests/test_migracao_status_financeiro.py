"""ADR-002: a migration preserva o significado financeiro dos dados legados."""

import importlib

from django.apps import apps
from django.test import TestCase

from sales.factories import PedidoFactory
from sales.models import Pagamento, Pedido

migracao = importlib.import_module(
    "sales.migrations.0002_pedido_status_financeiro"
)


class MigracaoStatusFinanceiroTests(TestCase):
    def _zerar_financeiro(self, *pedidos):
        Pedido.objects.filter(
            pk__in=[pedido.pk for pedido in pedidos]
        ).update(status_financeiro=Pedido.StatusFinanceiro.PENDENTE)

    def test_mapeia_estados_legados_sem_perder_pagamentos(self):
        pago = PedidoFactory(status=Pedido.Status.PAGO)
        separacao = PedidoFactory(status=Pedido.Status.EM_SEPARACAO)
        cancelado = PedidoFactory(status=Pedido.Status.CANCELADO)
        falhou = PedidoFactory(status=Pedido.Status.FALHOU)
        aguardando = PedidoFactory(status=Pedido.Status.AGUARDANDO_PAGAMENTO)
        aprovado = PedidoFactory(status=Pedido.Status.AGUARDANDO_PAGAMENTO)
        recusado = PedidoFactory(status=Pedido.Status.AGUARDANDO_PAGAMENTO)
        Pagamento.objects.create(
            pedido=aprovado,
            valor=aprovado.total,
            status=Pagamento.Status.APROVADO,
        )
        Pagamento.objects.create(
            pedido=recusado,
            valor=recusado.total,
            status=Pagamento.Status.RECUSADO,
        )
        self._zerar_financeiro(
            pago, separacao, cancelado, falhou, aguardando, aprovado, recusado
        )

        migracao.preencher_status_financeiro(apps, None)

        for pedido in (pago, separacao, aprovado):
            pedido.refresh_from_db()
            self.assertEqual(
                pedido.status_financeiro,
                Pedido.StatusFinanceiro.PAGO,
                pedido.status,
            )
        for pedido in (cancelado, falhou, recusado):
            pedido.refresh_from_db()
            self.assertEqual(
                pedido.status_financeiro,
                Pedido.StatusFinanceiro.CANCELADO,
                pedido.status,
            )
        aguardando.refresh_from_db()
        self.assertEqual(
            aguardando.status_financeiro, Pedido.StatusFinanceiro.PENDENTE
        )

    def test_estado_cumprido_com_pagamento_recusado_permanece_pago(self):
        concluido = PedidoFactory(status=Pedido.Status.CONCLUIDO)
        Pagamento.objects.create(
            pedido=concluido,
            valor=concluido.total,
            status=Pagamento.Status.RECUSADO,
        )
        Pedido.objects.filter(pk=concluido.pk).update(
            status_financeiro=Pedido.StatusFinanceiro.PENDENTE
        )

        migracao.preencher_status_financeiro(apps, None)

        concluido.refresh_from_db()
        self.assertEqual(
            concluido.status_financeiro, Pedido.StatusFinanceiro.PAGO
        )
