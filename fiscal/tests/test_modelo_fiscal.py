"""Modelo fiscal expandido: entrada/devolução, CFOP e chave referenciada."""

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from core.models import LogAuditoria
from fiscal.models import NotaFiscal
from fiscal.services import calcular_cfop_inverso, cancelar_nota_fiscal
from sales.factories import PedidoFactory

CHAVE = "29260812345678901234567890123456789012345678"


class ModeloFiscalTests(TestCase):
    def _pedido(self):
        return PedidoFactory(subtotal=Decimal("100.00"), total=Decimal("100.00"))

    def _nota(self, pedido, **kwargs):
        dados = {
            "pedido": pedido,
            "tipo": NotaFiscal.Tipo.SAIDA,
            "status": NotaFiscal.Status.AUTORIZADA,
            "cfop": "5.102",
            "chave_acesso": CHAVE,
        }
        dados.update(kwargs)
        return NotaFiscal.objects.create(**dados)

    def test_nfe_entrada_exige_chave_referenciada(self):
        nota = NotaFiscal(
            pedido=self._pedido(),
            tipo=NotaFiscal.Tipo.ENTRADA,
            chave_referenciada="",
            cfop="1.202",
        )

        with pytest.raises(ValidationError, match="chave"):
            nota.full_clean()

    def test_nfe_entrada_exige_chave_referenciada_com_44_digitos(self):
        nota = NotaFiscal(
            pedido=self._pedido(),
            tipo=NotaFiscal.Tipo.ENTRADA,
            chave_referenciada="123",
            cfop="1.202",
        )

        with pytest.raises(ValidationError, match="44"):
            nota.full_clean()

    def test_nfe_saida_sem_chave_referenciada_e_valida(self):
        nota = NotaFiscal(
            pedido=self._pedido(),
            tipo=NotaFiscal.Tipo.SAIDA,
            chave_acesso=CHAVE,
        )

        nota.full_clean()

    def test_calcular_cfop_inverso(self):
        self.assertEqual(calcular_cfop_inverso("5.102"), "1.202")
        self.assertEqual(calcular_cfop_inverso("5102"), "1.202")
        self.assertEqual(calcular_cfop_inverso("6.102"), "2.202")
        self.assertEqual(calcular_cfop_inverso("7.101"), "3.101")

    def test_calcular_cfop_inverso_rejeita_entrada(self):
        with pytest.raises(ValidationError):
            calcular_cfop_inverso("1.202")

    def test_pedido_admite_saida_e_entrada(self):
        pedido = self._pedido()
        saida = self._nota(pedido)
        entrada = self._nota(
            pedido,
            tipo=NotaFiscal.Tipo.ENTRADA,
            cfop="1.202",
            chave_referenciada=saida.chave_acesso,
            chave_acesso="",
        )

        self.assertEqual(pedido.nota_fiscal, saida)
        self.assertEqual(
            pedido.notas_fiscais.filter(tipo=NotaFiscal.Tipo.ENTRADA).get(),
            entrada,
        )

    def test_unicidade_por_pedido_e_tipo(self):
        pedido = self._pedido()
        self._nota(pedido)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self._nota(pedido)

    def test_cancelamento_de_nfe_autorizada_e_auditado(self):
        nota = self._nota(self._pedido())

        cancelar_nota_fiscal(nota, motivo="Erro de emissão")

        nota.refresh_from_db()
        self.assertEqual(nota.status, NotaFiscal.Status.CANCELADA)
        self.assertTrue(
            LogAuditoria.objects.filter(
                acao="fiscal.nota_cancelada",
                objeto_id=str(nota.pk),
            ).exists()
        )

    def test_cancelamento_de_nfe_e_idempotente(self):
        nota = self._nota(self._pedido())

        cancelar_nota_fiscal(nota, motivo="Erro")
        cancelar_nota_fiscal(nota, motivo="Erro")

        self.assertEqual(
            NotaFiscal.objects.get(pk=nota.pk).status,
            NotaFiscal.Status.CANCELADA,
        )
        self.assertEqual(
            LogAuditoria.objects.filter(
                acao="fiscal.nota_cancelada", objeto_id=str(nota.pk)
            ).count(),
            1,
        )

    def test_pedido_sem_nota_retorna_none(self):
        pedido = PedidoFactory()
        self.assertIsNone(pedido.nota_fiscal)

    def test_saida_padrao_do_tipo(self):
        nota = self._nota(self._pedido())
        self.assertEqual(nota.tipo, NotaFiscal.Tipo.SAIDA)
