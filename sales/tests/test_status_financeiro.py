"""ADR-002: status financeiro separado do andamento operacional."""

from decimal import Decimal
from unittest import mock

from django.core.exceptions import ValidationError
from django.test import TestCase

from catalog.factories import ProdutoFactory
from core.factories import UnidadeFactory
from core.models import LogAuditoria
from sales.factories import PedidoFactory
from sales.models import Pagamento, Pedido
from sales.services import (
    ResultadoPagamentoInvalido,
    _validar_disponibilidade,
    aplicar_resultado_pagamento,
    cancelar_pedido,
    marcar_pagamento_aprovado,
    reconciliar_pedido_financeiro,
)
from stock.factories import EstoqueFactory
from stock.models import Estoque

from .helpers import fluxo_checkout


class StatusFinanceiroModelTests(TestCase):
    def test_pagamento_aprovado_atualiza_status_financeiro(self):
        pedido = fluxo_checkout(self.client, quantidade=2)
        pagamento = Pagamento.objects.create(pedido=pedido, valor=pedido.total)

        marcar_pagamento_aprovado(pedido, id_externo="123")

        pedido.refresh_from_db()
        pagamento.refresh_from_db()
        self.assertEqual(
            pedido.status_financeiro, Pedido.StatusFinanceiro.PAGO
        )
        self.assertEqual(pedido.status, Pedido.Status.AGUARDANDO_PAGAMENTO)
        self.assertEqual(pagamento.status, Pagamento.Status.APROVADO)
        self.assertEqual(pagamento.id_externo, "123")

    def test_pedido_pago_pode_avancar_operacionalmente(self):
        pedido = PedidoFactory(status_financeiro=Pedido.StatusFinanceiro.PAGO)

        pedido.transicionar(Pedido.Status.EM_SEPARACAO)

        self.assertEqual(pedido.status, Pedido.Status.EM_SEPARACAO)
        self.assertEqual(
            pedido.status_financeiro, Pedido.StatusFinanceiro.PAGO
        )

    def test_pedido_nao_pago_nao_pode_avancar_para_separacao(self):
        pedido = PedidoFactory(
            status=Pedido.Status.AGUARDANDO_PAGAMENTO,
            status_financeiro=Pedido.StatusFinanceiro.PENDENTE,
        )

        with self.assertRaises(ValidationError):
            pedido.transicionar(Pedido.Status.EM_SEPARACAO)

    def test_pagamento_pendente_legado_pago_pode_separar(self):
        pedido = PedidoFactory(
            status=Pedido.Status.PAGAMENTO_PENDENTE,
            status_financeiro=Pedido.StatusFinanceiro.PAGO,
        )

        pedido.transicionar(Pedido.Status.EM_SEPARACAO)

        self.assertEqual(pedido.status, Pedido.Status.EM_SEPARACAO)

    def test_legado_pago_sem_prova_nao_avanca_ate_reconciliar(self):
        pedido = PedidoFactory(
            status=Pedido.Status.AGUARDANDO_PAGAMENTO,
            status_financeiro=Pedido.StatusFinanceiro.PAGO,
            financeiro_conciliado=False,
        )

        with self.assertRaises(ValidationError):
            pedido.transicionar(Pedido.Status.EM_SEPARACAO)

        reconciliar_pedido_financeiro(
            pedido,
            justificativa="Conferido no extrato do provedor em 20/10/2026.",
        )
        pedido.refresh_from_db()
        pedido.transicionar(Pedido.Status.EM_SEPARACAO)

        self.assertEqual(pedido.status, Pedido.Status.EM_SEPARACAO)
        self.assertTrue(pedido.financeiro_conciliado)

    def test_estornado_nao_avanca_para_concluido(self):
        pedido = PedidoFactory(
            status=Pedido.Status.PRONTO_PARA_ENTREGA,
            status_financeiro=Pedido.StatusFinanceiro.ESTORNADO,
        )

        with self.assertRaises(ValidationError):
            pedido.transicionar(Pedido.Status.CONCLUIDO)

    def test_pendente_nao_avanca_para_pronto(self):
        pedido = PedidoFactory(
            status=Pedido.Status.EM_SEPARACAO,
            status_financeiro=Pedido.StatusFinanceiro.PENDENTE,
        )

        with self.assertRaises(ValidationError):
            pedido.transicionar(Pedido.Status.PRONTO_PARA_ENTREGA)

    def test_transicao_para_estado_financeiro_e_bloqueada_no_modelo(self):
        pedido = PedidoFactory(status=Pedido.Status.AGUARDANDO_PAGAMENTO)

        with self.assertRaises(ValidationError):
            pedido.transicionar(Pedido.Status.PAGO)

    def test_pagamento_aprovado_e_idempotente(self):
        pedido = fluxo_checkout(self.client, quantidade=2)
        marcar_pagamento_aprovado(pedido, id_externo="123")
        marcar_pagamento_aprovado(pedido, id_externo="123")

        item = pedido.itens.first()
        estoque = Estoque.objects.get(
            produto=item.produto, unidade=pedido.unidade
        )
        self.assertEqual(estoque.quantidade, Decimal("98"))
        self.assertEqual(estoque.quantidade_bloqueada, Decimal("0"))

    def test_aprovacao_com_instancia_stale_nao_duplica_baixa(self):
        pedido = fluxo_checkout(self.client, quantidade=2)
        stale = Pedido.objects.get(pk=pedido.pk)

        marcar_pagamento_aprovado(pedido, id_externo="123")
        marcar_pagamento_aprovado(stale, id_externo="123")

        item = pedido.itens.first()
        estoque = Estoque.objects.get(
            produto=item.produto, unidade=pedido.unidade
        )
        self.assertEqual(estoque.quantidade, Decimal("98"))
        self.assertEqual(estoque.quantidade_bloqueada, Decimal("0"))

    def test_cancelamento_com_instancia_stale_apos_pagamento_nao_libera_reserva(self):
        pedido = fluxo_checkout(self.client, quantidade=2)
        stale = Pedido.objects.get(pk=pedido.pk)
        marcar_pagamento_aprovado(pedido, id_externo="123")

        cancelar_pedido(stale)

        item = pedido.itens.first()
        estoque = Estoque.objects.get(
            produto=item.produto, unidade=pedido.unidade
        )
        pedido.refresh_from_db()
        self.assertEqual(estoque.quantidade, Decimal("98"))
        self.assertEqual(estoque.quantidade_bloqueada, Decimal("0"))
        self.assertEqual(pedido.status, Pedido.Status.CANCELADO)
        self.assertEqual(
            pedido.status_financeiro, Pedido.StatusFinanceiro.PAGO
        )

    def test_expiracao_ignora_pedido_pago_por_instancia_stale(self):
        pedido = fluxo_checkout(self.client, quantidade=2)
        stale = Pedido.objects.get(pk=pedido.pk)
        marcar_pagamento_aprovado(pedido, id_externo="123")

        cancelar_pedido(stale, permitir_pago=False)

        pedido.refresh_from_db()
        self.assertEqual(pedido.status, Pedido.Status.AGUARDANDO_PAGAMENTO)
        self.assertEqual(
            pedido.status_financeiro, Pedido.StatusFinanceiro.PAGO
        )

    def test_cancelamento_de_pedido_pago_preserva_financeiro(self):
        pedido = fluxo_checkout(self.client, quantidade=1)
        marcar_pagamento_aprovado(pedido, id_externo="123")

        cancelar_pedido(pedido)

        pedido.refresh_from_db()
        self.assertEqual(pedido.status, Pedido.Status.CANCELADO)
        self.assertEqual(
            pedido.status_financeiro, Pedido.StatusFinanceiro.PAGO
        )

    def test_aprovacao_em_rascunho_nao_marca_pago(self):
        pedido = PedidoFactory(status=Pedido.Status.RASCUNHO)

        marcar_pagamento_aprovado(pedido, id_externo="123")

        pedido.refresh_from_db()
        self.assertEqual(
            pedido.status_financeiro, Pedido.StatusFinanceiro.PENDENTE
        )
        self.assertEqual(pedido.status, Pedido.Status.RASCUNHO)
        self.assertTrue(
            LogAuditoria.objects.filter(
                acao="pedido.pagamento_inconsistente",
                objeto_id=str(pedido.pk),
            ).exists()
        )

    def test_aprovacao_em_falhou_legado_nao_marca_pago(self):
        pedido = PedidoFactory(status=Pedido.Status.FALHOU)

        marcar_pagamento_aprovado(pedido, id_externo="123")

        pedido.refresh_from_db()
        self.assertEqual(
            pedido.status_financeiro, Pedido.StatusFinanceiro.CANCELADO
        )
        self.assertEqual(pedido.status, Pedido.Status.FALHOU)
        self.assertTrue(
            LogAuditoria.objects.filter(
                acao="pedido.pagamento_inconsistente",
                objeto_id=str(pedido.pk),
            ).exists()
        )


class ResultadoPagamentoTests(TestCase):
    def _pedido_com_pagamento(self):
        pedido = fluxo_checkout(self.client, quantidade=2)
        Pagamento.objects.create(pedido=pedido, valor=pedido.total)
        return pedido

    def _aplicar(self, pedido, status):
        return aplicar_resultado_pagamento(
            {
                "external_reference": pedido.numero,
                "status": status,
                "id": "pay-status",
                "transaction_amount": str(pedido.total),
                "currency_id": "BRL",
                "collector_id": "fake-collector",
                "live_mode": False,
            },
            id_consultado="pay-status",
        )

    def test_pendente_mantem_status_operacional(self):
        pedido = self._pedido_com_pagamento()

        self._aplicar(pedido, "pending")

        pedido.refresh_from_db()
        self.assertEqual(
            pedido.status_financeiro, Pedido.StatusFinanceiro.PENDENTE
        )
        self.assertEqual(pedido.status, Pedido.Status.AGUARDANDO_PAGAMENTO)

    def test_recusado_cancela_financeiro_e_operacional(self):
        pedido = self._pedido_com_pagamento()
        item = pedido.itens.first()
        estoque = Estoque.objects.get(
            produto=item.produto, unidade=pedido.unidade
        )
        self.assertEqual(estoque.quantidade_bloqueada, Decimal("2"))

        self._aplicar(pedido, "refused")

        pedido.refresh_from_db()
        estoque.refresh_from_db()
        self.assertEqual(
            pedido.status_financeiro, Pedido.StatusFinanceiro.CANCELADO
        )
        self.assertEqual(pedido.status, Pedido.Status.CANCELADO)
        self.assertEqual(estoque.quantidade_bloqueada, Decimal("0"))

    def test_chargeback_marca_estornado_e_cancela(self):
        pedido = self._pedido_com_pagamento()
        marcar_pagamento_aprovado(pedido, id_externo="pay-status")

        self._aplicar(pedido, "charged_back")

        pedido.refresh_from_db()
        self.assertEqual(
            pedido.status_financeiro, Pedido.StatusFinanceiro.ESTORNADO
        )
        self.assertEqual(pedido.status, Pedido.Status.CANCELADO)

    def test_aprovacao_legada_concilia_pagamento_pendente(self):
        from decimal import Decimal

        from sales.factories import PedidoFactory

        pedido = PedidoFactory(
            status=Pedido.Status.AGUARDANDO_PAGAMENTO,
            status_financeiro=Pedido.StatusFinanceiro.PAGO,
            financeiro_conciliado=False,
            total="10.00",
        )
        pagamento = Pagamento.objects.create(
            pedido=pedido,
            valor=Decimal("10.00"),
            status=Pagamento.Status.PENDENTE,
        )

        self._aplicar(pedido, "approved")

        pedido.refresh_from_db()
        pagamento.refresh_from_db()
        self.assertTrue(pedido.financeiro_conciliado)
        self.assertEqual(pagamento.status, Pagamento.Status.APROVADO)
        self.assertEqual(pagamento.id_externo, "pay-status")
        self.assertTrue(
            LogAuditoria.objects.filter(
                acao="pedido.financeiro_reconciliado",
                objeto_id=str(pedido.pk),
            ).exists()
        )

    def test_aprovacao_legada_repetida_nao_duplica_efeito(self):
        from decimal import Decimal

        from sales.factories import PedidoFactory

        pedido = PedidoFactory(
            status=Pedido.Status.AGUARDANDO_PAGAMENTO,
            status_financeiro=Pedido.StatusFinanceiro.PAGO,
            financeiro_conciliado=False,
            total="10.00",
        )
        Pagamento.objects.create(
            pedido=pedido,
            valor=Decimal("10.00"),
            status=Pagamento.Status.PENDENTE,
        )

        self._aplicar(pedido, "approved")
        self._aplicar(pedido, "approved")

        pedido.refresh_from_db()
        pedido.pagamento.refresh_from_db()
        self.assertTrue(pedido.financeiro_conciliado)
        self.assertEqual(pedido.pagamento.status, Pagamento.Status.APROVADO)
        # Um evento idempotente não repete a conciliação.
        self.assertEqual(
            LogAuditoria.objects.filter(
                acao="pedido.financeiro_reconciliado",
                objeto_id=str(pedido.pk),
            ).count(),
            1,
        )

    def test_falha_auditoria_reverte_conciliacao_e_pagamento_legado(self):
        from core import auditoria as modulo_auditoria
        from sales.factories import PedidoFactory

        pedido = PedidoFactory(
            status=Pedido.Status.AGUARDANDO_PAGAMENTO,
            status_financeiro=Pedido.StatusFinanceiro.PAGO,
            financeiro_conciliado=False,
            total="10.00",
        )
        pagamento = Pagamento.objects.create(
            pedido=pedido,
            valor=pedido.total,
            status=Pagamento.Status.PENDENTE,
        )
        real = modulo_auditoria.registrar_auditoria

        def falhar_na_conciliacao(*args, **kwargs):
            if kwargs.get("acao") == "pedido.financeiro_reconciliado":
                raise RuntimeError("auditoria indisponível")
            return real(*args, **kwargs)

        with mock.patch(
            "core.auditoria.registrar_auditoria",
            side_effect=falhar_na_conciliacao,
        ):
            with self.assertRaises(RuntimeError):
                self._aplicar(pedido, "approved")

        pedido.refresh_from_db()
        pagamento.refresh_from_db()
        self.assertFalse(pedido.financeiro_conciliado)
        self.assertEqual(pagamento.status, Pagamento.Status.PENDENTE)

    def test_aprovacao_apos_cancelamento_nao_reabre_pedido(self):
        pedido = self._pedido_com_pagamento()
        cancelar_pedido(pedido)

        self._aplicar(pedido, "approved")

        pedido.refresh_from_db()
        self.assertEqual(pedido.status, Pedido.Status.CANCELADO)
        self.assertNotEqual(
            pedido.status_financeiro, Pedido.StatusFinanceiro.PAGO
        )
        self.assertTrue(
            LogAuditoria.objects.filter(
                acao="pedido.pagamento_apos_cancelamento",
                objeto_id=str(pedido.pk),
            ).exists()
        )

    def test_chargeback_sem_pagamento_nao_altera_financeiro(self):
        pedido = self._pedido_com_pagamento()

        self._aplicar(pedido, "charged_back")

        pedido.refresh_from_db()
        self.assertEqual(
            pedido.status_financeiro, Pedido.StatusFinanceiro.PENDENTE
        )
        self.assertTrue(
            LogAuditoria.objects.filter(
                acao="pedido.pagamento_estorno_inconsistente",
                objeto_id=str(pedido.pk),
            ).exists()
        )

    def test_evento_recusado_apos_pagamento_nao_rebaixa(self):
        pedido = self._pedido_com_pagamento()
        marcar_pagamento_aprovado(pedido, id_externo="pay-status")

        self._aplicar(pedido, "refused")

        pedido.refresh_from_db()
        self.assertEqual(
            pedido.status_financeiro, Pedido.StatusFinanceiro.PAGO
        )
        self.assertEqual(
            pedido.pagamento.status, Pagamento.Status.APROVADO
        )
        self.assertTrue(
            LogAuditoria.objects.filter(
                acao="pedido.pagamento_evento_ignorado",
                objeto_id=str(pedido.pk),
            ).exists()
        )

    def test_evento_pendente_apos_pagamento_nao_altera_pagamento(self):
        pedido = self._pedido_com_pagamento()
        marcar_pagamento_aprovado(pedido, id_externo="pay-status")

        self._aplicar(pedido, "pending")

        pedido.refresh_from_db()
        self.assertEqual(
            pedido.status_financeiro, Pedido.StatusFinanceiro.PAGO
        )
        self.assertEqual(
            pedido.pagamento.status, Pagamento.Status.APROVADO
        )

    def test_rejected_cancela_como_recusa(self):
        pedido = self._pedido_com_pagamento()

        self._aplicar(pedido, "rejected")

        pedido.refresh_from_db()
        self.assertEqual(
            pedido.status_financeiro, Pedido.StatusFinanceiro.CANCELADO
        )
        self.assertEqual(pedido.status, Pedido.Status.CANCELADO)
        self.assertEqual(
            pedido.pagamento.status, Pagamento.Status.RECUSADO
        )

    def test_refunded_marca_estornado(self):
        pedido = self._pedido_com_pagamento()
        marcar_pagamento_aprovado(pedido, id_externo="pay-status")

        self._aplicar(pedido, "refunded")

        pedido.refresh_from_db()
        self.assertEqual(
            pedido.status_financeiro, Pedido.StatusFinanceiro.ESTORNADO
        )
        self.assertEqual(pedido.status, Pedido.Status.CANCELADO)
        self.assertEqual(
            pedido.pagamento.status, Pagamento.Status.CANCELADO
        )

    def test_pending_apos_refunded_preserva_ambos_os_estados(self):
        pedido = self._pedido_com_pagamento()
        marcar_pagamento_aprovado(pedido, id_externo="pay-status")
        self._aplicar(pedido, "refunded")

        self._aplicar(pedido, "pending")

        pedido.refresh_from_db()
        pedido.pagamento.refresh_from_db()
        self.assertEqual(
            pedido.status_financeiro, Pedido.StatusFinanceiro.ESTORNADO
        )
        self.assertEqual(
            pedido.pagamento.status, Pagamento.Status.CANCELADO
        )

    def test_status_desconhecido_e_auditado(self):
        pedido = self._pedido_com_pagamento()

        self._aplicar(pedido, "in_mediation")
        self._aplicar(pedido, "status_inexistente")

        pedido.refresh_from_db()
        self.assertTrue(
            LogAuditoria.objects.filter(
                acao="pedido.pagamento_em_mediacao",
                objeto_id=str(pedido.pk),
            ).exists()
        )
        self.assertTrue(
            LogAuditoria.objects.filter(
                acao="pedido.pagamento_status_desconhecido",
                objeto_id=str(pedido.pk),
            ).exists()
        )

    def test_evento_pendente_apos_pagamento_nao_rebaixa(self):
        pedido = self._pedido_com_pagamento()
        marcar_pagamento_aprovado(pedido, id_externo="pay-status")

        self._aplicar(pedido, "pending")

        pedido.refresh_from_db()
        self.assertEqual(
            pedido.status_financeiro, Pedido.StatusFinanceiro.PAGO
        )
        self.assertTrue(
            LogAuditoria.objects.filter(
                acao="pedido.pagamento_evento_ignorado",
                objeto_id=str(pedido.pk),
            ).exists()
        )

    def test_pedido_legado_pago_sem_financeiro_pago_nao_separa(self):
        pedido = PedidoFactory(
            status=Pedido.Status.PAGO,
            status_financeiro=Pedido.StatusFinanceiro.PENDENTE,
        )

        with self.assertRaises(ValidationError):
            pedido.transicionar(Pedido.Status.EM_SEPARACAO)

    def test_evento_pendente_apos_cancelamento_nao_reabre(self):
        pedido = self._pedido_com_pagamento()
        cancelar_pedido(pedido)

        self._aplicar(pedido, "pending")

        pedido.refresh_from_db()
        self.assertEqual(pedido.status, Pedido.Status.CANCELADO)
        self.assertEqual(
            pedido.status_financeiro, Pedido.StatusFinanceiro.CANCELADO
        )

    def test_evento_recusado_em_separacao_inconsistente_nao_quebra(self):
        pedido = PedidoFactory(
            status=Pedido.Status.EM_SEPARACAO,
            status_financeiro=Pedido.StatusFinanceiro.PENDENTE,
        )
        Pagamento.objects.create(pedido=pedido, valor=pedido.total)

        self._aplicar(pedido, "refused")

        pedido.refresh_from_db()
        self.assertEqual(pedido.status, Pedido.Status.EM_SEPARACAO)
        self.assertEqual(
            pedido.status_financeiro, Pedido.StatusFinanceiro.PENDENTE
        )
        self.assertTrue(
            LogAuditoria.objects.filter(
                acao="pedido.pagamento_evento_ignorado",
                objeto_id=str(pedido.pk),
            ).exists()
        )

    def test_chargeback_em_separacao_mantem_andamento_para_revisao(self):
        pedido = PedidoFactory(
            status=Pedido.Status.EM_SEPARACAO,
            status_financeiro=Pedido.StatusFinanceiro.PAGO,
        )
        Pagamento.objects.create(pedido=pedido, valor=pedido.total)

        self._aplicar(pedido, "charged_back")

        pedido.refresh_from_db()
        self.assertEqual(pedido.status, Pedido.Status.EM_SEPARACAO)
        self.assertEqual(
            pedido.status_financeiro, Pedido.StatusFinanceiro.ESTORNADO
        )
        self.assertTrue(
            LogAuditoria.objects.filter(
                acao="pedido.estorno_com_andamento",
                objeto_id=str(pedido.pk),
            ).exists()
        )

    def test_chargeback_apos_cancelamento_pago_marca_estornado(self):
        pedido = self._pedido_com_pagamento()
        marcar_pagamento_aprovado(pedido, id_externo="pay-status")
        cancelar_pedido(pedido)

        self._aplicar(pedido, "charged_back")

        pedido.refresh_from_db()
        self.assertEqual(pedido.status, Pedido.Status.CANCELADO)
        self.assertEqual(
            pedido.status_financeiro, Pedido.StatusFinanceiro.ESTORNADO
        )

    def test_resultado_sem_tentativa_local_e_invalido(self):
        pedido = PedidoFactory(status=Pedido.Status.AGUARDANDO_PAGAMENTO)
        with self.assertRaises(ResultadoPagamentoInvalido):
            aplicar_resultado_pagamento(
                {
                    "external_reference": pedido.numero,
                    "status": "pending",
                    "id": "pay-sem-objeto",
                    "transaction_amount": str(pedido.total),
                    "currency_id": "BRL",
                    "collector_id": "fake-collector",
                    "live_mode": False,
                },
                id_consultado="pay-sem-objeto",
            )
        inexistente = aplicar_resultado_pagamento(
            {
                "external_reference": "PF999999",
                "status": "pending",
                "id": "pay-inexistente",
                "transaction_amount": "10.00",
                "currency_id": "BRL",
                "collector_id": "fake-collector",
                "live_mode": False,
            },
            id_consultado="pay-inexistente",
        )

        self.assertIsNone(inexistente)
        pedido.refresh_from_db()
        self.assertEqual(
            pedido.status_financeiro, Pedido.StatusFinanceiro.PENDENTE
        )
        self.assertTrue(
            LogAuditoria.objects.filter(
                acao="pedido.pagamento_contrato_invalido",
                objeto_id=str(pedido.pk),
            ).exists()
        )

    def test_cancelar_com_financeiro_estornado_preserva_estorno(self):
        pedido = PedidoFactory(
            status=Pedido.Status.AGUARDANDO_PAGAMENTO,
            status_financeiro=Pedido.StatusFinanceiro.ESTORNADO,
        )

        cancelar_pedido(pedido)

        pedido.refresh_from_db()
        self.assertEqual(pedido.status, Pedido.Status.CANCELADO)
        self.assertEqual(
            pedido.status_financeiro, Pedido.StatusFinanceiro.ESTORNADO
        )


class DisponibilidadeTests(TestCase):
    def test_quantidade_indisponivel_lista_produto(self):
        produto = ProdutoFactory(nome="Feno Curto")
        unidade = UnidadeFactory()
        EstoqueFactory(
            produto=produto, unidade=unidade, quantidade="1.00"
        )

        with self.assertRaises(ValidationError) as contexto:
            _validar_disponibilidade(
                [{"produto": produto, "quantidade": Decimal("2.00")}],
                unidade,
            )

        self.assertIn("Feno Curto", str(contexto.exception))
        self.assertIn("indisponível", str(contexto.exception))
