"""Reprodução dos achados A01-A04 da auditoria da Fase 2C."""

from datetime import date, datetime, time
from decimal import Decimal

import pytest
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.core.management import call_command
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

    def test_estorno_rejeita_pagamento_recusado(self):
        pedido = self._pedido()
        pagamento = pedido.pagamento
        pagamento.status = Pagamento.Status.RECUSADO
        pagamento.save(update_fields=["status"])

        with pytest.raises(ValidationError):
            estornar_pagamento(pagamento, motivo="inválido")


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
