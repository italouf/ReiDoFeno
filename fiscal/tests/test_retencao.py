"""Retenção fiscal: cálculo de prazo e limpeza operacional (ADR-012)."""

from datetime import date, datetime

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from core.models import LogAuditoria
from fiscal.models import NotaFiscal
from sales.factories import PedidoFactory
from sales.models import Pedido


def data_emissao(ano, mes, dia):
    return timezone.make_aware(datetime(ano, mes, dia, 14, 30))


class RetencaoNotaTests(TestCase):
    def criar_nota(self, *, emissao=None, retido_ate=None, numero="123"):
        pedido = PedidoFactory(status=Pedido.Status.PAGO)
        return NotaFiscal.objects.create(
            pedido=pedido,
            tipo=NotaFiscal.Tipo.SAIDA,
            numero=numero,
            chave_acesso=str(pedido.pk).zfill(44),
            data_emissao=emissao,
            retido_ate=retido_ate,
        )

    def test_nota_recebe_retencao_de_cinco_anos(self):
        nota = self.criar_nota(emissao=data_emissao(2026, 11, 10))

        self.assertEqual(nota.retido_ate, date(2031, 11, 10))

    def test_retencao_trata_29_de_fevereiro(self):
        nota = self.criar_nota(emissao=data_emissao(2028, 2, 29))

        self.assertEqual(nota.retido_ate, date(2033, 2, 28))

    def test_nota_sem_data_de_emissao_nao_tem_retencao(self):
        nota = self.criar_nota(emissao=None)

        self.assertIsNone(nota.retido_ate)

    def test_retencao_existente_nao_e_sobrescrita(self):
        nota = self.criar_nota(
            emissao=data_emissao(2026, 11, 10),
            retido_ate=date(2035, 1, 1),
        )

        self.assertEqual(nota.retido_ate, date(2035, 1, 1))

    def test_comando_remove_somente_notas_expiradas(self):
        antiga = self.criar_nota(
            emissao=data_emissao(2020, 1, 1), numero="1"
        )
        recente = self.criar_nota(
            emissao=data_emissao(2026, 1, 1), numero="2"
        )

        call_command("limpar_notas_expiradas", verbosity=0)

        self.assertFalse(
            NotaFiscal.objects.filter(pk=antiga.pk).exists()
        )
        self.assertTrue(
            NotaFiscal.objects.filter(pk=recente.pk).exists()
        )

    def test_comando_audita_cada_remocao(self):
        nota = self.criar_nota(
            emissao=data_emissao(2020, 1, 1), numero="987"
        )
        nota_id = nota.pk
        pedido_numero = nota.pedido.numero
        chave = nota.chave_acesso

        call_command("limpar_notas_expiradas", verbosity=0)

        log = LogAuditoria.objects.filter(
            acao="fiscal.nota_retencao_expirada",
            objeto_tipo="fiscal.NotaFiscal",
            objeto_id=str(nota_id),
        ).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.antes["numero"], "987")
        self.assertEqual(log.antes["pedido"], pedido_numero)
        self.assertEqual(log.antes["chave_acesso"], chave)
        self.assertEqual(log.antes["retido_ate"], "2025-01-01")

    def test_dry_run_nao_remove(self):
        nota = self.criar_nota(emissao=data_emissao(2020, 1, 1))

        call_command("limpar_notas_expiradas", "--dry-run", verbosity=0)

        self.assertTrue(NotaFiscal.objects.filter(pk=nota.pk).exists())
        self.assertFalse(
            LogAuditoria.objects.filter(
                acao="fiscal.nota_retencao_expirada"
            ).exists()
        )
