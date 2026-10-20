"""R8/R10: inventário legado é read-only e não inventa prova."""

import json
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import TestCase

from accounts.models import Usuario
from customers.factories import ClienteFactory
from sales.factories import PedidoFactory
from sales.models import Pagamento, Pedido


class InventarioLegadoTests(TestCase):
    def test_lista_pagos_sem_prova_e_vinculos_pendentes(self):
        cliente = ClienteFactory()
        usuario = Usuario.objects.create_user(
            username="legado", password="senha-forte-123"
        )
        cliente.usuario = usuario
        cliente.save(update_fields=["usuario"])

        com_prova = PedidoFactory(
            status=Pedido.Status.PAGO,
            status_financeiro=Pedido.StatusFinanceiro.PAGO,
        )
        Pagamento.objects.create(
            pedido=com_prova,
            valor=com_prova.total,
            status=Pagamento.Status.APROVADO,
        )
        sem_prova = PedidoFactory(
            status=Pedido.Status.PAGO,
            status_financeiro=Pedido.StatusFinanceiro.PAGO,
            financeiro_conciliado=False,
        )

        saida = StringIO()
        call_command("inventariar_legado", "--json", stdout=saida)
        conteudo = saida.getvalue()
        dados = json.loads(conteudo)

        self.assertIn(sem_prova.numero, conteudo)
        self.assertNotIn(com_prova.numero, conteudo)
        self.assertIn(str(cliente.pk), conteudo)
        self.assertEqual(
            dados["pedidos_pagos_sem_pagamento_aprovado"][0]["numero"],
            sem_prova.numero,
        )
        # Nenhum estado foi reescrito.
        sem_prova.refresh_from_db()
        self.assertEqual(
            sem_prova.status_financeiro, Pedido.StatusFinanceiro.PAGO
        )

    def test_inventario_nao_cria_auditoria_nem_muta(self):
        pedido = PedidoFactory(
            status=Pedido.Status.PAGO,
            status_financeiro=Pedido.StatusFinanceiro.PAGO,
        )
        saida = StringIO()
        with mock.patch(
            "core.auditoria.LogAuditoria.objects.create"
        ) as criar:
            call_command("inventariar_legado", stdout=saida)
        criar.assert_not_called()
        pedido.refresh_from_db()
        self.assertEqual(pedido.status, Pedido.Status.PAGO)

    def test_reconciliacao_autorizada_libera_operacao_e_audita(self):
        pedido = PedidoFactory(
            status=Pedido.Status.AGUARDANDO_PAGAMENTO,
            status_financeiro=Pedido.StatusFinanceiro.PAGO,
            financeiro_conciliado=False,
        )
        saida = StringIO()

        call_command(
            "reconciliar_pedido_financeiro",
            pedido.numero,
            justificativa="Extrato do provedor conferido pela operação.",
            stdout=saida,
        )

        pedido.refresh_from_db()
        self.assertTrue(pedido.financeiro_conciliado)
        pedido.transicionar(Pedido.Status.EM_SEPARACAO)
        self.assertEqual(pedido.status, Pedido.Status.EM_SEPARACAO)
