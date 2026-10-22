"""Reprodução dos achados A01-A04 da auditoria da Fase 2C."""

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from unittest import mock

import pytest
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db.models import Sum
from django.test import TestCase
from django.utils import timezone

from accounts.models import Usuario
from analytics.models import Aviso
from analytics.services import comparativo_unidades, metricas_do_periodo
from catalog.factories import ProdutoFactory
from core.factories import UnidadeFactory
from fiscal.models import NotaFiscal
from sales.factories import (
    ItemPedidoFactory,
    PagamentoFactory,
    PedidoFactory,
)
from sales.models import (
    ObrigacaoEstoquePedido,
    Pagamento,
    Pedido,
)
from sales.services import (
    _obrigacao_por_movimento,
    aplicar_resultado_pagamento,
    cancelar_pedido_padrao,
    estornar_pagamento,
    registrar_devolucao,
)
from stock.factories import EstoqueFactory
from stock.models import Estoque, MovimentoEstoque

CHAVE = "29260812345678901234567890123456789012345678"


def _em(dia: date, hora=12):
    return timezone.make_aware(datetime.combine(dia, time(hora)))


def _em(dia: date, hora=12):
    return timezone.make_aware(datetime.combine(dia, time(hora)))


def _aplicar_chargeback(pedido):
    return aplicar_resultado_pagamento(
        {
            "external_reference": pedido.numero,
            "status": "charged_back",
            "id": "pay-audit",
            "transaction_amount": str(pedido.total),
            "currency_id": "BRL",
            "collector_id": "fake-collector",
            "live_mode": False,
        },
        id_consultado="pay-audit",
    )


class BaseAuditoriaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_groups", verbosity=0)
        cls.admin = Usuario.objects.create_user(
            username="admin_auditoria", password="senha-forte-123"
        )
        cls.admin.groups.add(Group.objects.get(name="Administrador"))

    def _pedido(
        self,
        *,
        status=Pedido.Status.CONCLUIDO,
        financeiro=None,
        aprovado_em=None,
        unidade=None,
        com_estoque=False,
    ):
        unidade = unidade or UnidadeFactory()
        pedido = PedidoFactory(
            status=status,
            status_financeiro=financeiro or Pedido.StatusFinanceiro.PAGO,
            financeiro_conciliado=True,
            unidade=unidade,
            subtotal=Decimal("100.00"),
            frete=Decimal("0.00"),
            total=Decimal("100.00"),
        )
        ItemPedidoFactory(
            pedido=pedido,
            produto=ProdutoFactory(custo=Decimal("30.00")),
            quantidade=2,
            preco_unitario=Decimal("50.00"),
            custo_unitario=Decimal("30.00"),
        )
        if com_estoque:
            EstoqueFactory(
                produto=pedido.itens.get().produto,
                unidade=unidade,
                quantidade=Decimal("10.00"),
            )
        PagamentoFactory(
            pedido=pedido,
            valor=Decimal("100.00"),
            status=Pagamento.Status.APROVADO,
            id_externo="pay-audit",
            aprovado_em=aprovado_em or timezone.now(),
        )
        return pedido


class A01A02ChargebackTests(BaseAuditoriaTests):
    def test_chargeback_deve_manter_lucro_coerente_entre_paineis(self):
        pedido = self._pedido()
        _aplicar_chargeback(pedido)
        hoje = timezone.localdate()

        metricas = metricas_do_periodo(hoje, hoje)
        unidade = comparativo_unidades(hoje, hoje)[0]

        self.assertEqual(metricas["receita"], Decimal("0.00"))
        self.assertEqual(metricas["cmv_total"], Decimal("60.00"))
        self.assertEqual(metricas["lucro_bruto"], Decimal("-60.00"))
        self.assertEqual(unidade["receita"], Decimal("0.00"))
        self.assertEqual(unidade["cmv"], Decimal("60.00"))
        self.assertEqual(unidade["lucro_bruto"], Decimal("-60.00"))

    def test_chargeback_nao_deve_apagar_cmv_de_janeiro(self):
        pedido = self._pedido(
            status=Pedido.Status.AGUARDANDO_PAGAMENTO,
            aprovado_em=_em(date(2026, 1, 10)),
        )
        janeiro = metricas_do_periodo(
            date(2026, 1, 1), date(2026, 1, 31)
        )
        self.assertEqual(janeiro["cmv_total"], Decimal("60.00"))

        _aplicar_chargeback(pedido)

        janeiro_depois = metricas_do_periodo(
            date(2026, 1, 1), date(2026, 1, 31)
        )
        self.assertEqual(janeiro_depois["receita"], Decimal("100.00"))
        self.assertEqual(janeiro_depois["cmv_total"], Decimal("60.00"))
        self.assertEqual(janeiro_depois["lucro_bruto"], Decimal("40.00"))


class A01A02FluxoPublicoTresPeriodosTests(BaseAuditoriaTests):
    def test_oracle_janeiro_fevereiro_marco_por_fluxos_publicos(self):
        pedido = self._pedido(aprovado_em=_em(date(2026, 1, 10)))
        item = pedido.itens.get()
        NotaFiscal.objects.create(
            pedido=pedido,
            tipo=NotaFiscal.Tipo.SAIDA,
            status=NotaFiscal.Status.AUTORIZADA,
            cfop="5.102",
            chave_acesso=CHAVE,
        )
        ObrigacaoEstoquePedido.objects.create(
            pedido=pedido,
            produto=item.produto,
            unidade=pedido.unidade,
            quantidade_devida=Decimal("2.00"),
            quantidade_baixada=Decimal("2.00"),
            evidencia_baixada=Decimal("2.00"),
            status=ObrigacaoEstoquePedido.Status.RESOLVIDA,
        )

        janeiro = metricas_do_periodo(
            date(2026, 1, 1), date(2026, 1, 31)
        )
        self.assertEqual(janeiro["receita"], Decimal("100.00"))
        self.assertEqual(janeiro["cmv_total"], Decimal("60.00"))
        self.assertEqual(janeiro["lucro_bruto"], Decimal("40.00"))

        with mock.patch(
            "django.utils.timezone.now",
            return_value=_em(date(2026, 2, 10)),
        ):
            _aplicar_chargeback(pedido)

        fevereiro = metricas_do_periodo(
            date(2026, 2, 1), date(2026, 2, 28)
        )
        self.assertEqual(fevereiro["receita"], Decimal("-100.00"))
        self.assertEqual(fevereiro["cmv_total"], Decimal("0.00"))
        self.assertEqual(fevereiro["lucro_bruto"], Decimal("-100.00"))

        with mock.patch(
            "django.utils.timezone.now",
            return_value=_em(date(2026, 3, 10)),
        ):
            registrar_devolucao(
                pedido=pedido,
                justificativa="Retorno físico em março",
                usuario=self.admin,
            )

        marco = metricas_do_periodo(
            date(2026, 3, 1), date(2026, 3, 31)
        )
        self.assertEqual(marco["receita"], Decimal("0.00"))
        self.assertEqual(marco["cmv_total"], Decimal("-60.00"))
        self.assertEqual(marco["lucro_bruto"], Decimal("60.00"))


class A03DevolucaoPosChargebackTests(BaseAuditoriaTests):
    def test_devolucao_manual_apos_chargeback_deve_ser_possivel(self):
        pedido = self._pedido()
        NotaFiscal.objects.create(
            pedido=pedido,
            tipo=NotaFiscal.Tipo.SAIDA,
            status=NotaFiscal.Status.AUTORIZADA,
            cfop="5.102",
            chave_acesso=CHAVE,
        )
        ObrigacaoEstoquePedido.objects.create(
            pedido=pedido,
            produto=pedido.itens.get().produto,
            unidade=pedido.unidade,
            quantidade_devida=Decimal("2.00"),
            quantidade_baixada=Decimal("2.00"),
            evidencia_baixada=Decimal("2.00"),
            status=ObrigacaoEstoquePedido.Status.RESOLVIDA,
        )
        _aplicar_chargeback(pedido)

        nota_entrada = registrar_devolucao(
            pedido=pedido,
            justificativa="Mercadoria devolvida após chargeback",
            usuario=self.admin,
        )

        self.assertEqual(nota_entrada.tipo, NotaFiscal.Tipo.ENTRADA)
        self.assertEqual(nota_entrada.chave_referenciada, CHAVE)
        self.assertEqual(
            MovimentoEstoque.objects.filter(
                tipo=MovimentoEstoque.Tipo.ENTRADA_DEVOLUCAO,
                delta=Decimal("2.00"),
            ).count(),
            1,
        )
        self.assertEqual(
            Pagamento.objects.filter(
                pedido=pedido, estornado_em__isnull=False
            ).count(),
            1,
        )


class A03ComplementoTests(BaseAuditoriaTests):
    def test_devolucao_reutiliza_entrada_pendente(self):
        pedido = self._pedido()
        NotaFiscal.objects.create(
            pedido=pedido,
            tipo=NotaFiscal.Tipo.SAIDA,
            status=NotaFiscal.Status.AUTORIZADA,
            cfop="5.102",
            chave_acesso=CHAVE,
        )
        pendente = NotaFiscal.objects.create(
            pedido=pedido,
            tipo=NotaFiscal.Tipo.ENTRADA,
            status=NotaFiscal.Status.PENDENTE,
            cfop="1.202",
            chave_referenciada=CHAVE,
        )

        resultado = registrar_devolucao(
            pedido=pedido,
            justificativa="Devolução idempotente",
            usuario=self.admin,
        )

        self.assertEqual(resultado.pk, pendente.pk)
        self.assertEqual(
            NotaFiscal.objects.filter(
                pedido=pedido, tipo=NotaFiscal.Tipo.ENTRADA
            ).count(),
            1,
        )

    def test_devolucao_reconcilia_evidencia_parcial_em_segunda_chamada(self):
        pedido = self._pedido()
        item = pedido.itens.get()
        NotaFiscal.objects.create(
            pedido=pedido,
            tipo=NotaFiscal.Tipo.SAIDA,
            status=NotaFiscal.Status.AUTORIZADA,
            cfop="5.102",
            chave_acesso=CHAVE,
        )
        obrigacao = ObrigacaoEstoquePedido.objects.create(
            pedido=pedido,
            produto=item.produto,
            unidade=pedido.unidade,
            quantidade_devida=Decimal("2.00"),
            quantidade_baixada=Decimal("2.00"),
            evidencia_baixada=Decimal("1.00"),
            status=ObrigacaoEstoquePedido.Status.PENDENTE,
        )

        registrar_devolucao(
            pedido=pedido,
            justificativa="Retorno parcial",
            usuario=self.admin,
        )
        self.assertEqual(
            MovimentoEstoque.objects.filter(
                tipo=MovimentoEstoque.Tipo.ENTRADA_DEVOLUCAO
            ).aggregate(total=Sum("delta"))["total"],
            Decimal("1.00"),
        )

        obrigacao.evidencia_baixada = Decimal("2.00")
        obrigacao.save(update_fields=["evidencia_baixada"])
        registrar_devolucao(
            pedido=pedido,
            justificativa="Conciliação do restante",
            usuario=self.admin,
        )

        self.assertEqual(
            MovimentoEstoque.objects.filter(
                tipo=MovimentoEstoque.Tipo.ENTRADA_DEVOLUCAO
            ).aggregate(total=Sum("delta"))["total"],
            Decimal("2.00"),
        )

    def test_estorno_rejeita_pagamento_recusado(self):
        pedido = self._pedido()
        pagamento = pedido.pagamento
        pagamento.status = Pagamento.Status.RECUSADO
        pagamento.save(update_fields=["status"])

        with pytest.raises(ValidationError):
            estornar_pagamento(pagamento, motivo="inválido")


class A02LegadoTests(BaseAuditoriaTests):
    def test_movimento_legado_sem_obrigacao_e_reconhecido(self):
        pedido = self._pedido()
        item = pedido.itens.get()
        obrigacao = ObrigacaoEstoquePedido.objects.create(
            pedido=pedido,
            produto=item.produto,
            unidade=pedido.unidade,
            quantidade_devida=Decimal("2.00"),
            quantidade_baixada=Decimal("2.00"),
            evidencia_baixada=Decimal("2.00"),
            status=ObrigacaoEstoquePedido.Status.RESOLVIDA,
        )
        MovimentoEstoque.objects.create(
            produto=item.produto,
            unidade=pedido.unidade,
            tipo=MovimentoEstoque.Tipo.ENTRADA_DEVOLUCAO,
            delta=Decimal("2.00"),
            motivo=f"Devolução do pedido {pedido.numero}: legado",
        )
        hoje = timezone.localdate()

        metricas = metricas_do_periodo(hoje, hoje)

        self.assertEqual(metricas["cmv_total"], Decimal("0.00"))
        self.assertEqual(metricas["lucro_bruto"], Decimal("100.00"))

        NotaFiscal.objects.create(
            pedido=pedido,
            tipo=NotaFiscal.Tipo.SAIDA,
            status=NotaFiscal.Status.AUTORIZADA,
            cfop="5.102",
            chave_acesso=CHAVE,
        )
        registrar_devolucao(
            pedido=pedido,
            justificativa="Legado já compensado",
            usuario=self.admin,
        )
        self.assertEqual(
            MovimentoEstoque.objects.filter(
                tipo=MovimentoEstoque.Tipo.ENTRADA_DEVOLUCAO
            ).count(),
            1,
        )
        self.assertEqual(obrigacao.quantidade_baixada, Decimal("2.00"))

    def test_motivo_ambiguo_nao_atribui_retorno_a_ninguem(self):
        pedido1 = self._pedido()
        pedido2 = self._pedido()
        item1 = pedido1.itens.get()
        movimento = MovimentoEstoque.objects.create(
            produto=item1.produto,
            unidade=pedido1.unidade,
            tipo=MovimentoEstoque.Tipo.ENTRADA_DEVOLUCAO,
            delta=Decimal("2.00"),
            motivo=(
                f"Devolução em conciliação: {pedido1.numero} ou "
                f"{pedido2.numero}; sem atribuição confirmada"
            ),
        )

        self.assertIsNone(_obrigacao_por_movimento(movimento))

    def test_pagamento_cancelado_sem_data_nao_gera_frete_negativo(self):
        pedido = self._pedido()
        Pagamento.objects.filter(pedido=pedido).update(
            status=Pagamento.Status.CANCELADO,
            estornado_em=None,
        )
        hoje = timezone.localdate()

        metricas = metricas_do_periodo(hoje, hoje)

        self.assertEqual(metricas["receita"], Decimal("0.00"))
        self.assertEqual(metricas["receita_produtos"], Decimal("0.00"))
        self.assertEqual(metricas["receita_frete"], Decimal("0.00"))
        self.assertEqual(metricas["cmv_total"], Decimal("0.00"))
        self.assertEqual(
            metricas["receita_em_conciliacao"], Decimal("100.00")
        )

    def test_frete_e_receita_de_produtos_ficam_separados(self):
        pedido = PedidoFactory(
            status=Pedido.Status.PAGO,
            subtotal=Decimal("100.00"),
            frete=Decimal("20.00"),
            total=Decimal("120.00"),
        )
        ItemPedidoFactory(
            pedido=pedido,
            quantidade=2,
            preco_unitario=Decimal("50.00"),
            custo_unitario=Decimal("30.00"),
        )
        PagamentoFactory(
            pedido=pedido,
            valor=Decimal("120.00"),
            status=Pagamento.Status.APROVADO,
            aprovado_em=timezone.now(),
        )
        hoje = timezone.localdate()

        metricas = metricas_do_periodo(hoje, hoje)

        self.assertEqual(metricas["receita"], Decimal("120.00"))
        self.assertEqual(metricas["receita_produtos"], Decimal("100.00"))
        self.assertEqual(metricas["receita_frete"], Decimal("20.00"))
        self.assertEqual(metricas["cmv_total"], Decimal("60.00"))
        self.assertEqual(metricas["lucro_bruto"], Decimal("40.00"))

    def test_estorno_de_aprovacao_tardia_nao_gera_negativo(self):
        pedido = PedidoFactory(
            status=Pedido.Status.CANCELADO,
            status_financeiro=Pedido.StatusFinanceiro.CANCELADO,
            subtotal=Decimal("100.00"),
            total=Decimal("100.00"),
        )
        Pedido.objects.filter(pk=pedido.pk).update(
            cancelado_em=timezone.now() - timedelta(hours=1)
        )
        pagamento = PagamentoFactory(
            pedido=pedido,
            valor=Decimal("100.00"),
            status=Pagamento.Status.APROVADO,
            aprovado_em=timezone.now(),
        )
        pagamento.status = Pagamento.Status.CANCELADO
        pagamento.estornado_em = timezone.now() + timedelta(minutes=1)
        pagamento.save(update_fields=["status", "estornado_em"])
        hoje = timezone.localdate()

        self.assertEqual(
            metricas_do_periodo(hoje, hoje)["receita"], Decimal("0.00")
        )


class A04EvidenciaEstoqueTests(BaseAuditoriaTests):
    def test_cancelamento_legado_sem_evidencia_nao_deve_inflar_estoque(self):
        pedido = self._pedido(
            status=Pedido.Status.PAGO,
            com_estoque=True,
        )
        produto = pedido.itens.get().produto
        estoque = Estoque.objects.get(produto=produto, unidade=pedido.unidade)

        cancelar_pedido_padrao(
            pedido=pedido,
            justificativa="Cancelamento sem evidência histórica",
            usuario=self.admin,
        )

        estoque.refresh_from_db()
        self.assertEqual(estoque.quantidade, Decimal("10.00"))
        self.assertEqual(
            MovimentoEstoque.objects.filter(
                tipo=MovimentoEstoque.Tipo.ENTRADA_DEVOLUCAO
            ).count(),
            0,
        )
        self.assertTrue(
            Aviso.objects.filter(
                tipo=Aviso.Tipo.ESTOQUE_PENDENTE,
                objeto_id=str(pedido.pk),
            ).exists()
        )

    def test_evidencia_zero_nao_credita(self):
        pedido = self._pedido(
            status=Pedido.Status.PAGO,
            com_estoque=True,
        )
        item = pedido.itens.get()
        ObrigacaoEstoquePedido.objects.create(
            pedido=pedido,
            produto=item.produto,
            unidade=pedido.unidade,
            quantidade_devida=Decimal("2.00"),
            quantidade_baixada=Decimal("2.00"),
            evidencia_baixada=Decimal("0.00"),
            status=ObrigacaoEstoquePedido.Status.PENDENTE,
        )
        estoque = Estoque.objects.get(
            produto=item.produto, unidade=pedido.unidade
        )

        cancelar_pedido_padrao(
            pedido=pedido,
            justificativa="Sem evidência",
            usuario=self.admin,
        )

        estoque.refresh_from_db()
        self.assertEqual(estoque.quantidade, Decimal("10.00"))
        self.assertTrue(
            Aviso.objects.filter(
                tipo=Aviso.Tipo.ESTOQUE_PENDENTE,
                objeto_id=str(pedido.pk),
            ).exists()
        )

    def test_evidencia_parcial_devolve_somente_quantidade_comprovada(self):
        pedido = self._pedido(
            status=Pedido.Status.PAGO,
            com_estoque=True,
        )
        item = pedido.itens.get()
        ObrigacaoEstoquePedido.objects.create(
            pedido=pedido,
            produto=item.produto,
            unidade=pedido.unidade,
            quantidade_devida=Decimal("2.00"),
            quantidade_baixada=Decimal("1.00"),
            evidencia_baixada=Decimal("1.00"),
            status=ObrigacaoEstoquePedido.Status.PENDENTE,
        )
        estoque = Estoque.objects.get(
            produto=item.produto, unidade=pedido.unidade
        )

        cancelar_pedido_padrao(
            pedido=pedido,
            justificativa="Baixa parcial comprovada",
            usuario=self.admin,
        )

        estoque.refresh_from_db()
        self.assertEqual(estoque.quantidade, Decimal("11.00"))
