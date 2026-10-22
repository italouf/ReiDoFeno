"""Reprodução dos achados A05-A07 da auditoria da Fase 2C."""

from datetime import date, datetime, time
from decimal import Decimal

from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Usuario
from fiscal.models import NotaFiscal
from sales.factories import (
    ItemPedidoFactory,
    PagamentoFactory,
    PedidoFactory,
)
from sales.models import Pagamento, Pedido
from stock.models import MovimentoEstoque

CHAVE_SAIDA = "29260812345678901234567890123456789012345678"
CHAVE_ENTRADA = "31261098765432109876543210987654321098765432"


def _em(dia: date, hora=12):
    return timezone.make_aware(datetime.combine(dia, time(hora)))


class BaseFiscalAuditoriaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_groups", verbosity=0)
        cls.emissor = Usuario.objects.create_user(
            username="emissor_auditoria", password="senha-forte-123"
        )
        cls.emissor.groups.add(Group.objects.get(name="Emissor Fiscal"))
        cls.gestor = Usuario.objects.create_user(
            username="gestor_auditoria", password="senha-forte-123"
        )
        cls.gestor.groups.add(Group.objects.get(name="Gestor"))

    def _pedido(self, status=Pedido.Status.CONCLUIDO, financeiro=None):
        pedido = PedidoFactory(
            status=status,
            status_financeiro=financeiro or Pedido.StatusFinanceiro.PAGO,
            financeiro_conciliado=True,
            subtotal=Decimal("100.00"),
            total=Decimal("100.00"),
        )
        ItemPedidoFactory(
            pedido=pedido,
            quantidade=1,
            preco_unitario=Decimal("100.00"),
            custo_unitario=Decimal("60.00"),
        )
        PagamentoFactory(
            pedido=pedido,
            valor=Decimal("100.00"),
            status=Pagamento.Status.APROVADO,
            aprovado_em=timezone.now(),
        )
        return pedido


class A05RegistroEntradaTests(BaseFiscalAuditoriaTests):
    def _entrada_pendente(self):
        pedido = self._pedido(
            financeiro=Pedido.StatusFinanceiro.ESTORNADO
        )
        Pagamento.objects.filter(pedido=pedido).update(
            status=Pagamento.Status.CANCELADO,
            estornado_em=timezone.now(),
        )
        saida = NotaFiscal.objects.create(
            pedido=pedido,
            tipo=NotaFiscal.Tipo.SAIDA,
            status=NotaFiscal.Status.AUTORIZADA,
            cfop="5.102",
            chave_acesso=CHAVE_SAIDA,
        )
        entrada = NotaFiscal.objects.create(
            pedido=pedido,
            tipo=NotaFiscal.Tipo.ENTRADA,
            status=NotaFiscal.Status.PENDENTE,
            cfop="1.202",
            chave_referenciada=saida.chave_acesso,
        )
        return pedido, entrada

    def test_emissor_deve_conseguir_registrar_documento_de_entrada(self):
        pedido, entrada = self._entrada_pendente()
        self.client.force_login(self.emissor)

        lista = self.client.get(reverse("fiscal:nota_entrada_lista"))
        self.assertEqual(lista.status_code, 200)
        self.assertContains(lista, pedido.numero)

        formulario = self.client.get(
            reverse("fiscal:nota_entrada_registrar", args=[entrada.pk])
        )
        self.assertEqual(formulario.status_code, 200)

        resposta = self.client.post(
            reverse("fiscal:nota_entrada_registrar", args=[entrada.pk]),
            {
                "numero": "77001",
                "chave_acesso": CHAVE_ENTRADA,
                "link_documento": "https://exemplo.com/entrada.pdf",
            },
        )
        self.assertEqual(resposta.status_code, 302)

        entrada.refresh_from_db()
        self.assertEqual(entrada.status, NotaFiscal.Status.AUTORIZADA)
        self.assertEqual(entrada.origem, NotaFiscal.Origem.MANUAL)
        self.assertEqual(entrada.numero, "77001")
        self.assertEqual(entrada.chave_acesso, CHAVE_ENTRADA)
        self.assertEqual(entrada.chave_referenciada, CHAVE_SAIDA)

    def test_entrada_com_referencia_incompativel_e_rejeitada(self):
        pedido, entrada = self._entrada_pendente()
        entrada.chave_referenciada = "99999999999999999999999999999999999999999999"
        entrada.save(update_fields=["chave_referenciada"])
        self.client.force_login(self.emissor)

        resposta = self.client.post(
            reverse("fiscal:nota_entrada_registrar", args=[entrada.pk]),
            {
                "numero": "77003",
                "chave_acesso": CHAVE_ENTRADA,
            },
        )

        self.assertEqual(resposta.status_code, 200)
        entrada.refresh_from_db()
        self.assertEqual(entrada.status, NotaFiscal.Status.PENDENTE)

    def test_entrada_nao_pode_reutilizar_chave_da_saida(self):
        _, entrada = self._entrada_pendente()
        self.client.force_login(self.emissor)

        resposta = self.client.post(
            reverse("fiscal:nota_entrada_registrar", args=[entrada.pk]),
            {"numero": "77004", "chave_acesso": CHAVE_SAIDA},
        )

        self.assertEqual(resposta.status_code, 200)
        entrada.refresh_from_db()
        self.assertEqual(entrada.status, NotaFiscal.Status.PENDENTE)

    def test_entrada_nao_pode_duplicar_chave_de_outra_nota(self):
        _, entrada = self._entrada_pendente()
        outro_pedido = self._pedido()
        NotaFiscal.objects.create(
            pedido=outro_pedido,
            tipo=NotaFiscal.Tipo.SAIDA,
            status=NotaFiscal.Status.AUTORIZADA,
            cfop="5.102",
            chave_acesso=CHAVE_ENTRADA,
        )
        self.client.force_login(self.emissor)

        resposta = self.client.post(
            reverse("fiscal:nota_entrada_registrar", args=[entrada.pk]),
            {"numero": "77006", "chave_acesso": CHAVE_ENTRADA},
        )

        self.assertEqual(resposta.status_code, 200)
        entrada.refresh_from_db()
        self.assertEqual(entrada.status, NotaFiscal.Status.PENDENTE)

    def test_entrada_cancelada_nao_e_reautorizada(self):
        _, entrada = self._entrada_pendente()
        entrada.status = NotaFiscal.Status.CANCELADA
        entrada.save(update_fields=["status"])
        self.client.force_login(self.emissor)

        resposta = self.client.post(
            reverse("fiscal:nota_entrada_registrar", args=[entrada.pk]),
            {"numero": "77005", "chave_acesso": CHAVE_ENTRADA},
        )

        self.assertEqual(resposta.status_code, 200)
        entrada.refresh_from_db()
        self.assertEqual(entrada.status, NotaFiscal.Status.CANCELADA)

    def test_registro_de_entrada_nao_repete_estoque_nem_estorno(self):
        pedido, entrada = self._entrada_pendente()
        movimentos_antes = MovimentoEstoque.objects.count()
        self.client.force_login(self.emissor)
        self.client.post(
            reverse("fiscal:nota_entrada_registrar", args=[entrada.pk]),
            {
                "numero": "77002",
                "chave_acesso": CHAVE_ENTRADA,
            },
        )

        self.assertEqual(
            Pagamento.objects.filter(
                pedido=pedido, estornado_em__isnull=False
            ).count(),
            1,
        )
        self.assertEqual(NotaFiscal.objects.filter(pedido=pedido).count(), 2)
        self.assertEqual(MovimentoEstoque.objects.count(), movimentos_antes)


class A06CsvFiscalTests(BaseFiscalAuditoriaTests):
    def test_csv_fiscal_com_dados_deve_funcionar(self):
        self._pedido()
        self.client.force_login(self.emissor)

        resposta = self.client.get(
            reverse("fiscal:relatorio_fiscal"),
            {
                "formato": "csv",
                "inicio": timezone.localdate().isoformat(),
                "fim": timezone.localdate().isoformat(),
            },
        )

        self.assertEqual(resposta.status_code, 200)
        conteudo = resposta.content.decode("utf-8")
        self.assertIn("aprovacao", conteudo)
        self.assertIn("100.00", conteudo)

    def test_csv_fiscal_sanitiza_formula_e_exporta_estorno(self):
        pedido = self._pedido()
        unidade = pedido.unidade
        unidade.nome = "=Planilha Perigosa"
        unidade.save(update_fields=["nome"])
        Pagamento.objects.filter(pedido=pedido).update(
            status=Pagamento.Status.CANCELADO,
            estornado_em=timezone.now(),
        )
        self.client.force_login(self.emissor)

        resposta = self.client.get(
            reverse("fiscal:relatorio_fiscal"),
            {
                "formato": "csv",
                "inicio": timezone.localdate().isoformat(),
                "fim": timezone.localdate().isoformat(),
            },
        )

        self.assertEqual(resposta.status_code, 200)
        conteudo = resposta.content.decode("utf-8")
        self.assertIn("'=Planilha Perigosa", conteudo)
        self.assertIn("estorno", conteudo)
        self.assertIn("-100.00", conteudo)


class A07CfopTests(BaseFiscalAuditoriaTests):
    def _nota_autorizada(self, cfop="5.102"):
        pedido = self._pedido()
        return NotaFiscal.objects.create(
            pedido=pedido,
            tipo=NotaFiscal.Tipo.SAIDA,
            status=NotaFiscal.Status.AUTORIZADA,
            origem=NotaFiscal.Origem.MANUAL,
            cfop=cfop,
            numero="123",
            chave_acesso=CHAVE_SAIDA,
        )

    def test_cfop_de_nota_autorizada_nao_deve_ser_reescrito_silenciosamente(self):
        nota = self._nota_autorizada()
        self.client.force_login(self.gestor)

        resposta = self.client.post(
            reverse("fiscal:nota_manual", args=[nota.pedido_id]),
            {
                "numero": nota.numero,
                "chave_acesso": nota.chave_acesso,
                "cfop": "5.101",
            },
        )

        self.assertEqual(resposta.status_code, 200)
        nota.refresh_from_db()
        self.assertEqual(nota.cfop, "5.102")

    def test_saida_cancelada_nao_e_reautorizada(self):
        nota = self._nota_autorizada()
        nota.status = NotaFiscal.Status.CANCELADA
        nota.save(update_fields=["status"])
        self.client.force_login(self.gestor)

        resposta = self.client.post(
            reverse("fiscal:nota_manual", args=[nota.pedido_id]),
            {
                "numero": nota.numero,
                "chave_acesso": nota.chave_acesso,
            },
        )

        self.assertEqual(resposta.status_code, 200)
        nota.refresh_from_db()
        self.assertEqual(nota.status, NotaFiscal.Status.CANCELADA)

    def test_cfop_sem_mapeamento_e_rejeitado(self):
        pedido = self._pedido()
        self.client.force_login(self.gestor)

        resposta = self.client.post(
            reverse("fiscal:nota_manual", args=[pedido.pk]),
            {
                "numero": "555",
                "chave_acesso": CHAVE_SAIDA,
                "cfop": "5.405",
            },
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(
            NotaFiscal.objects.filter(
                pedido=pedido, tipo=NotaFiscal.Tipo.SAIDA
            ).exists()
        )

    def test_saneamento_de_legado_apos_estorno_e_permitido(self):
        nota = self._nota_autorizada(cfop="")
        pedido = nota.pedido
        pedido.status_financeiro = Pedido.StatusFinanceiro.ESTORNADO
        pedido.save(update_fields=["status_financeiro"])
        Pagamento.objects.filter(pedido=pedido).update(
            status=Pagamento.Status.CANCELADO,
            estornado_em=timezone.now(),
        )
        self.client.force_login(self.gestor)

        resposta = self.client.post(
            reverse("fiscal:nota_manual", args=[pedido.pk]),
            {
                "numero": nota.numero,
                "chave_acesso": nota.chave_acesso,
                "cfop": "5.102",
                "motivo_retificacao": "Saneamento após estorno",
                "evidencia_retificacao": "https://exemplo.com/evidencia",
            },
        )

        self.assertEqual(resposta.status_code, 302)
        nota.refresh_from_db()
        self.assertEqual(nota.cfop, "5.102")
        from core.models import LogAuditoria

        self.assertTrue(
            LogAuditoria.objects.filter(
                acao="fiscal.nota_cfop_retificado",
                objeto_id=str(nota.pk),
            ).exists()
        )

    def test_saneamento_autorizado_de_cfop_legado_e_auditado(self):
        nota = self._nota_autorizada(cfop="")
        self.client.force_login(self.gestor)

        resposta = self.client.post(
            reverse("fiscal:nota_manual", args=[nota.pedido_id]),
            {
                "numero": nota.numero,
                "chave_acesso": nota.chave_acesso,
                "cfop": "5.102",
                "motivo_retificacao": "Saneamento de metadado legado",
                "evidencia_retificacao": "https://exemplo.com/evidencia",
            },
        )

        self.assertEqual(resposta.status_code, 302)
        nota.refresh_from_db()
        self.assertEqual(nota.cfop, "5.102")
        from core.models import LogAuditoria

        self.assertTrue(
            LogAuditoria.objects.filter(
                acao="fiscal.nota_cfop_retificado",
                objeto_id=str(nota.pk),
            ).exists()
        )
