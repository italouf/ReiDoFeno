"""Registro manual de pagamento (PAY-MANUAL)."""

import tempfile
from datetime import date, timedelta
from decimal import Decimal
from unittest import mock

from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import Usuario
from catalog.factories import ProdutoFactory
from core.factories import UnidadeFactory
from core.models import LogAuditoria
from customers.factories import ClienteFactory
from sales.factories import ItemPedidoFactory, PedidoFactory
from sales.models import ComprovantePagamento, Pagamento, Pedido
from stock.factories import EstoqueFactory
from stock.models import ReservaEstoque
from stock.services import reservar

from .helpers import saldo_de


class BasePagamentoManualTests(TestCase):
    @classmethod
    def setUpClass(cls):
        cls._media = tempfile.TemporaryDirectory()
        cls._override = override_settings(MEDIA_ROOT=cls._media.name)
        cls._override.enable()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls._override.disable()
        cls._media.cleanup()

    @classmethod
    def setUpTestData(cls):
        call_command("seed_groups", verbosity=0)
        cls.senha = "senha-forte-123"
        cls.vendedor = Usuario.objects.create_user(
            username="vendedor", password=cls.senha
        )
        cls.vendedor.groups.add(Group.objects.get(name="Vendedor"))
        cls.outro_vendedor = Usuario.objects.create_user(
            username="outro-vendedor", password=cls.senha
        )
        cls.outro_vendedor.groups.add(Group.objects.get(name="Vendedor"))
        cls.gestor = Usuario.objects.create_user(
            username="gestor", password=cls.senha
        )
        cls.gestor.groups.add(Group.objects.get(name="Gestor"))

    def criar_pedido(self, *, total="100.00", status_financeiro="pendente", status=None):
        cliente = ClienteFactory()
        unidade = UnidadeFactory()
        produto = ProdutoFactory(preco_online="10.00", custo="5.00")
        EstoqueFactory(
            produto=produto,
            unidade=unidade,
            quantidade="100.00",
            quantidade_bloqueada="0.00",
        )
        pedido = PedidoFactory(
            cliente=cliente,
            unidade=unidade,
            usuario_criador=self.vendedor,
            status=status or Pedido.Status.AGUARDANDO_PAGAMENTO,
            status_financeiro=status_financeiro,
        )
        quantidade = Decimal(total) / Decimal("10.00")
        item = ItemPedidoFactory(
            pedido=pedido,
            produto=produto,
            quantidade=quantidade,
            preco_unitario=Decimal("10.00"),
            custo_unitario=Decimal("5.00"),
        )
        pedido.recalcular_totais()
        if (
            status_financeiro == Pedido.StatusFinanceiro.PENDENTE
            and pedido.status != Pedido.Status.CANCELADO
        ):
            reservar(
                produto=produto,
                unidade=unidade,
                quantidade=quantidade,
                pedido=pedido,
                item_pedido=item,
            )
        return pedido

    def dados(self, **extra):
        base = {
            "metodo": "pix",
            "valor": "100.00",
            "data_pagamento": "2026-11-10T14:30:00",
            "referencia": "E12345678901234567890123456789012",
        }
        base.update(extra)
        return base

    def postar(self, pedido, **extra):
        return self.client.post(
            reverse("sales:pedido_pagamento_manual", args=[pedido.pk]),
            self.dados(**extra),
        )


class RegistroPagamentoManualTests(BasePagamentoManualTests):
    def test_vendedor_registra_pagamento_pix(self):
        pedido = self.criar_pedido()
        self.client.force_login(self.vendedor)

        resposta = self.postar(pedido)

        self.assertEqual(resposta.status_code, 302)
        pedido.refresh_from_db()
        self.assertEqual(pedido.status_financeiro, Pedido.StatusFinanceiro.PAGO)
        self.assertFalse(pedido.financeiro_conciliado)
        self.assertEqual(pedido.comprovantes.count(), 1)
        comprovante = pedido.comprovantes.first()
        self.assertEqual(comprovante.metodo, ComprovantePagamento.Metodo.PIX)
        self.assertEqual(comprovante.valor, Decimal("100.00"))
        self.assertEqual(
            comprovante.referencia, "E12345678901234567890123456789012"
        )
        self.assertEqual(
            comprovante.status, ComprovantePagamento.Status.PENDENTE
        )
        self.assertEqual(comprovante.registrado_por, self.vendedor)

    def test_pagamento_manual_cria_pagamento_para_receita(self):
        pedido = self.criar_pedido()
        self.client.force_login(self.vendedor)

        self.postar(pedido)

        pagamento = Pagamento.objects.get(pedido=pedido)
        self.assertEqual(pagamento.provedor, "manual")
        self.assertEqual(pagamento.status, Pagamento.Status.APROVADO)
        self.assertEqual(pagamento.valor, Decimal("100.00"))
        self.assertEqual(
            timezone.localtime(pagamento.aprovado_em).date(), date(2026, 11, 10)
        )

        from analytics.services import pagamentos_aprovados

        aprovados = pagamentos_aprovados(date(2026, 11, 10), date(2026, 11, 10))
        self.assertIn(pagamento.pk, list(aprovados.values_list("pk", flat=True)))

    def test_pagamento_manual_consome_reserva(self):
        pedido = self.criar_pedido()
        self.client.force_login(self.vendedor)

        self.postar(pedido)

        reserva = pedido.reservas.get()
        self.assertEqual(reserva.status, ReservaEstoque.Status.CONSUMIDA)
        quantidade, bloqueada = saldo_de(pedido)
        self.assertEqual(quantidade, Decimal("90.00"))
        self.assertEqual(bloqueada, Decimal("0.00"))

    def test_pagamento_manual_gera_auditoria(self):
        pedido = self.criar_pedido()
        self.client.force_login(self.vendedor)

        self.postar(pedido)

        log = LogAuditoria.objects.filter(
            acao="pagamento_manual_registrado",
            objeto_tipo="sales.Pedido",
            objeto_id=str(pedido.pk),
        ).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.usuario, self.vendedor)
        self.assertEqual(log.depois["metodo"], "pix")
        self.assertEqual(log.depois["valor"], "100.00")
        self.assertEqual(log.depois["status_financeiro"], "pago")

    def test_pagamento_parcial_mantem_status_pendente(self):
        pedido = self.criar_pedido()
        self.client.force_login(self.vendedor)

        resposta = self.postar(pedido, valor="50.00")

        self.assertEqual(resposta.status_code, 302)
        pedido.refresh_from_db()
        self.assertEqual(
            pedido.status_financeiro, Pedido.StatusFinanceiro.PENDENTE
        )
        self.assertEqual(pedido.comprovantes.count(), 1)
        self.assertFalse(Pagamento.objects.filter(pedido=pedido).exists())
        self.assertEqual(pedido.reservas.get().status, ReservaEstoque.Status.ATIVA)

    def test_pagamento_parcial_complementar_fecha_saldo(self):
        pedido = self.criar_pedido()
        self.client.force_login(self.vendedor)

        self.postar(pedido, valor="50.00")
        self.postar(
            pedido,
            valor="50.00",
            referencia="E99999999999999999999999999999999",
        )

        pedido.refresh_from_db()
        self.assertEqual(pedido.status_financeiro, Pedido.StatusFinanceiro.PAGO)
        self.assertEqual(pedido.comprovantes.count(), 2)
        self.assertEqual(pedido.reservas.get().status, ReservaEstoque.Status.CONSUMIDA)

    def test_valor_acima_do_saldo_e_rejeitado(self):
        pedido = self.criar_pedido()
        self.client.force_login(self.vendedor)

        resposta = self.postar(pedido, valor="150.00")

        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(pedido.comprovantes.exists())
        pedido.refresh_from_db()
        self.assertEqual(
            pedido.status_financeiro, Pedido.StatusFinanceiro.PENDENTE
        )

    def test_pagamento_bloqueado_se_ja_pago(self):
        pedido = self.criar_pedido(status_financeiro=Pedido.StatusFinanceiro.PAGO)
        self.client.force_login(self.vendedor)

        resposta = self.postar(pedido)

        self.assertEqual(resposta.status_code, 400)
        self.assertFalse(pedido.comprovantes.exists())

    def test_pagamento_bloqueado_se_estornado(self):
        pedido = self.criar_pedido(
            status_financeiro=Pedido.StatusFinanceiro.ESTORNADO
        )
        self.client.force_login(self.vendedor)

        resposta = self.postar(pedido)

        self.assertEqual(resposta.status_code, 400)
        self.assertFalse(pedido.comprovantes.exists())

    def test_pagamento_bloqueado_se_cancelado(self):
        pedido = self.criar_pedido(status=Pedido.Status.CANCELADO)
        self.client.force_login(self.vendedor)

        resposta = self.postar(pedido)

        self.assertEqual(resposta.status_code, 400)
        self.assertFalse(pedido.comprovantes.exists())

    def test_vendedor_nao_registra_em_pedido_de_outro_vendedor(self):
        pedido = self.criar_pedido()
        self.client.force_login(self.outro_vendedor)

        resposta = self.postar(pedido)

        self.assertEqual(resposta.status_code, 404)
        self.assertFalse(pedido.comprovantes.exists())

    def test_gestor_registra_pagamento_de_qualquer_vendedor(self):
        pedido = self.criar_pedido()
        self.client.force_login(self.gestor)

        resposta = self.postar(pedido)

        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(pedido.comprovantes.count(), 1)


class ValidacaoComprovanteTests(BasePagamentoManualTests):
    def test_pix_exige_referencia(self):
        pedido = self.criar_pedido()
        self.client.force_login(self.vendedor)

        resposta = self.postar(pedido, referencia="")

        self.assertEqual(resposta.status_code, 200)
        self.assertIn("referencia", resposta.context["form"].errors)
        self.assertFalse(pedido.comprovantes.exists())

    def test_dinheiro_nao_exige_referencia(self):
        pedido = self.criar_pedido()
        self.client.force_login(self.vendedor)

        resposta = self.postar(pedido, metodo="dinheiro", referencia="")

        self.assertEqual(resposta.status_code, 302)
        comprovante = pedido.comprovantes.get()
        self.assertEqual(comprovante.metodo, "dinheiro")

    def test_upload_comprovante_imagem(self):
        pedido = self.criar_pedido()
        imagem = SimpleUploadedFile(
            "comprovante.jpg",
            b"\xff\xd8\xff\xe0fake image content",
            content_type="image/jpeg",
        )
        self.client.force_login(self.vendedor)

        resposta = self.postar(pedido, arquivo=imagem)

        self.assertEqual(resposta.status_code, 302)
        comprovante = pedido.comprovantes.get()
        self.assertIsNotNone(comprovante.arquivo)
        self.assertTrue(comprovante.arquivo.name.endswith(".jpg"))
        self.assertIn("comprovantes/", comprovante.arquivo.name)

    def test_upload_comprovante_pdf(self):
        pedido = self.criar_pedido()
        pdf = SimpleUploadedFile(
            "comprovante.pdf",
            b"%PDF-1.4 fake",
            content_type="application/pdf",
        )
        self.client.force_login(self.vendedor)

        resposta = self.postar(pedido, arquivo=pdf)

        self.assertEqual(resposta.status_code, 302)
        self.assertTrue(pedido.comprovantes.get().arquivo.name.endswith(".pdf"))

    def test_upload_tipo_invalido_e_rejeitado(self):
        pedido = self.criar_pedido()
        arquivo = SimpleUploadedFile(
            "comprovante.txt", b"texto", content_type="text/plain"
        )
        self.client.force_login(self.vendedor)

        resposta = self.postar(pedido, arquivo=arquivo)

        self.assertEqual(resposta.status_code, 200)
        self.assertIn("arquivo", resposta.context["form"].errors)
        self.assertFalse(pedido.comprovantes.exists())

    def test_upload_com_assinatura_invalida_e_rejeitado(self):
        pedido = self.criar_pedido()
        arquivo = SimpleUploadedFile(
            "comprovante.jpg",
            b"<html>nao e imagem</html>",
            content_type="image/jpeg",
        )
        self.client.force_login(self.vendedor)

        resposta = self.postar(pedido, arquivo=arquivo)

        self.assertEqual(resposta.status_code, 200)
        self.assertIn("arquivo", resposta.context["form"].errors)
        self.assertFalse(pedido.comprovantes.exists())

    def test_upload_acima_de_5mb_e_rejeitado(self):
        pedido = self.criar_pedido()
        arquivo = SimpleUploadedFile(
            "comprovante.pdf",
            b"x" * (5 * 1024 * 1024 + 1),
            content_type="application/pdf",
        )
        self.client.force_login(self.vendedor)

        resposta = self.postar(pedido, arquivo=arquivo)

        self.assertEqual(resposta.status_code, 200)
        self.assertIn("arquivo", resposta.context["form"].errors)
        self.assertFalse(pedido.comprovantes.exists())

    def test_valor_zero_e_rejeitado(self):
        pedido = self.criar_pedido()
        self.client.force_login(self.vendedor)

        resposta = self.postar(pedido, valor="0.00")

        self.assertEqual(resposta.status_code, 200)
        self.assertIn("valor", resposta.context["form"].errors)
        self.assertFalse(pedido.comprovantes.exists())

    def test_data_futura_e_rejeitada(self):
        pedido = self.criar_pedido()
        futura = (
            timezone.localtime(timezone.now()) + timedelta(days=2)
        ).strftime("%Y-%m-%dT%H:%M")
        self.client.force_login(self.vendedor)

        resposta = self.postar(pedido, data_pagamento=futura)

        self.assertEqual(resposta.status_code, 200)
        self.assertIn("data_pagamento", resposta.context["form"].errors)
        self.assertFalse(pedido.comprovantes.exists())

    def test_data_muito_antiga_e_rejeitada(self):
        pedido = self.criar_pedido()
        self.client.force_login(self.vendedor)

        resposta = self.postar(
            pedido, data_pagamento="2020-01-01T10:00"
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertIn("data_pagamento", resposta.context["form"].errors)
        self.assertFalse(pedido.comprovantes.exists())

    def test_pix_referencia_duplicada_e_rejeitada(self):
        pedido = self.criar_pedido()
        self.client.force_login(self.vendedor)
        self.postar(pedido, valor="50.00", referencia="E-DUPLICADA")

        resposta = self.postar(
            pedido, valor="50.00", referencia="E-DUPLICADA"
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertIn("referencia", resposta.context["form"].errors)
        self.assertEqual(pedido.comprovantes.count(), 1)
        pedido.refresh_from_db()
        self.assertEqual(
            pedido.status_financeiro, Pedido.StatusFinanceiro.PENDENTE
        )


class IntegracaoProvedorTests(BasePagamentoManualTests):
    def test_pagamento_parcial_bloqueia_novo_checkout_online(self):
        pedido = self.criar_pedido()
        self.client.force_login(self.vendedor)
        self.postar(pedido, valor="50.00")
        pedido.refresh_from_db()

        from sales.views import PagamentoIniciarView

        self.assertFalse(PagamentoIniciarView._pode_iniciar(pedido))

        with mock.patch("sales.payments.obter_client") as obter:
            resposta = self.client.post(
                reverse("sales:pagamento_iniciar", args=[pedido.token_acesso])
            )

        self.assertEqual(resposta.status_code, 302)
        obter.assert_not_called()

    def test_provedor_com_prova_manual_nao_auto_concilia(self):
        from sales.services import marcar_pagamento_aprovado

        pedido = self.criar_pedido()
        self.client.force_login(self.vendedor)
        self.postar(pedido, valor="50.00")
        pedido.refresh_from_db()

        marcar_pagamento_aprovado(pedido, id_externo="mp-1")

        pedido.refresh_from_db()
        self.assertEqual(pedido.status_financeiro, Pedido.StatusFinanceiro.PAGO)
        self.assertFalse(pedido.financeiro_conciliado)
        self.assertEqual(
            pedido.comprovantes.get().status,
            ComprovantePagamento.Status.PENDENTE,
        )
        self.assertTrue(
            LogAuditoria.objects.filter(
                acao="pedido.pagamento_provedor_com_manual",
                objeto_id=str(pedido.pk),
            ).exists()
        )


class AcessoPagamentoManualTests(BasePagamentoManualTests):
    def test_anonimo_e_redirecionado_para_login(self):
        pedido = self.criar_pedido()

        resposta = self.client.get(
            reverse("sales:pedido_pagamento_manual", args=[pedido.pk])
        )

        self.assertEqual(resposta.status_code, 302)
        self.assertIn("/accounts/login/", resposta["Location"])

    def test_integridade_duplicada_vira_erro_de_formulario(self):
        from django.db import IntegrityError

        pedido = self.criar_pedido()
        self.client.force_login(self.vendedor)

        with mock.patch(
            "sales.views.registrar_pagamento_manual",
            side_effect=IntegrityError("duplicada"),
        ):
            resposta = self.postar(pedido)

        self.assertEqual(resposta.status_code, 200)
        self.assertIn("referencia", resposta.context["form"].errors)
        self.assertFalse(pedido.comprovantes.exists())

    def test_erro_de_servico_vira_erro_de_formulario(self):
        pedido = self.criar_pedido()
        self.client.force_login(self.vendedor)

        with mock.patch(
            "sales.views.registrar_pagamento_manual",
            side_effect=ValidationError("Pedido mudou de estado."),
        ):
            resposta = self.postar(pedido)

        self.assertEqual(resposta.status_code, 200)
        self.assertIn(
            "Pedido mudou de estado.",
            resposta.context["form"].non_field_errors(),
        )
        self.assertFalse(pedido.comprovantes.exists())


class FalhaTransacionalTests(BasePagamentoManualTests):
    def test_falha_de_auditoria_reverte_pagamento(self):
        pedido = self.criar_pedido()
        self.client.force_login(self.vendedor)

        with mock.patch(
            "core.auditoria.registrar_auditoria",
            side_effect=RuntimeError("auditoria indisponível"),
        ):
            with self.assertRaises(RuntimeError):
                self.postar(pedido)

        pedido.refresh_from_db()
        self.assertEqual(
            pedido.status_financeiro, Pedido.StatusFinanceiro.PENDENTE
        )
        self.assertFalse(pedido.comprovantes.exists())
        self.assertFalse(Pagamento.objects.filter(pedido=pedido).exists())
        self.assertEqual(pedido.reservas.get().status, ReservaEstoque.Status.ATIVA)
