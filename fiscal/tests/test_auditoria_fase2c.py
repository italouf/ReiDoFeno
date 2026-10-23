"""Reprodução dos achados A05-A07 da auditoria da Fase 2C."""

import uuid
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from unittest import mock

from django.contrib.auth.models import Group
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Usuario
from analytics.models import Aviso
from core.models import LogAuditoria
from customers.factories import ClienteFactory
from fiscal.client import ErroFiscal
from fiscal.models import NotaFiscal
from fiscal.services import (
    LEASE_EMISSAO,
    cancelar_nota_fiscal,
    enviar_para_emissao,
    pedido_elegivel,
)
from sales.factories import (
    ItemPedidoFactory,
    PagamentoFactory,
    PedidoFactory,
)
from sales.models import Pagamento, Pedido
from sales.services import cancelar_pedido_padrao
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
            cliente=ClienteFactory(documento="52998224725"),
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


class A02ChaveUnicaTests(BaseFiscalAuditoriaTests):
    def test_chave_nao_vazia_e_unica_no_banco(self):
        pedido1 = self._pedido()
        pedido2 = self._pedido()
        NotaFiscal.objects.create(
            pedido=pedido1,
            tipo=NotaFiscal.Tipo.SAIDA,
            status=NotaFiscal.Status.AUTORIZADA,
            chave_acesso=CHAVE_SAIDA,
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                NotaFiscal.objects.create(
                    pedido=pedido2,
                    tipo=NotaFiscal.Tipo.SAIDA,
                    status=NotaFiscal.Status.AUTORIZADA,
                    chave_acesso=CHAVE_SAIDA,
                )


class N03IntegracaoFiscalTests(BaseFiscalAuditoriaTests):
    def test_autorizacao_tardia_apos_cancelamento_gera_pendencia(self):
        pedido = self._pedido(status=Pedido.Status.PAGO)
        nota = NotaFiscal.objects.create(
            pedido=pedido,
            tipo=NotaFiscal.Tipo.SAIDA,
            status=NotaFiscal.Status.ERRO,
            cfop="5.102",
        )
        self.client.force_login(self.gestor)
        gestor = self.gestor
        self.assertTrue(pedido_elegivel(pedido), pedido.cliente.documento)

        class ClienteQueCancela:
            def criar_nfe(self, pedido_arg):
                cancelar_pedido_padrao(
                    pedido=Pedido.objects.get(pk=pedido.pk),
                    justificativa="Cancelamento durante integração",
                    usuario=gestor,
                )
                return {
                    "numero": "TARDIA",
                    "chave": CHAVE_ENTRADA,
                    "link": "https://exemplo.com/tardia",
                }

        resultado = enviar_para_emissao(
            pedido, client=ClienteQueCancela()
        )

        self.assertEqual(resultado.pk, nota.pk)
        nota.refresh_from_db()
        self.assertEqual(nota.status, NotaFiscal.Status.AUTORIZADA)
        self.assertIn("conciliação", nota.ultimo_erro)
        self.assertTrue(
            Aviso.objects.filter(
                tipo=Aviso.Tipo.FISCAL_ERRO,
                objeto_id=str(nota.pk),
            ).exists()
        )
        self.assertTrue(
            LogAuditoria.objects.filter(
                acao="fiscal.autorizacao_apos_cancelamento",
                objeto_id=str(nota.pk),
            ).exists()
        )
        self.assertEqual(
            Pedido.objects.get(pk=pedido.pk).status, Pedido.Status.CANCELADO
        )

    def test_integracao_nao_reemite_nota_cancelada(self):
        pedido = self._pedido(status=Pedido.Status.PAGO)
        nota = NotaFiscal.objects.create(
            pedido=pedido,
            tipo=NotaFiscal.Tipo.SAIDA,
            status=NotaFiscal.Status.CANCELADA,
            cfop="5.102",
            chave_acesso=CHAVE_SAIDA,
        )
        cliente = mock.Mock()

        resultado = enviar_para_emissao(pedido, client=cliente)

        self.assertEqual(resultado.pk, nota.pk)
        cliente.criar_nfe.assert_not_called()
        nota.refresh_from_db()
        self.assertEqual(nota.status, NotaFiscal.Status.CANCELADA)

    def test_retry_nao_chama_provedor_quando_lease_ativo(self):
        pedido = self._pedido(status=Pedido.Status.PAGO)
        nota = NotaFiscal.objects.create(
            pedido=pedido,
            tipo=NotaFiscal.Tipo.SAIDA,
            status=NotaFiscal.Status.PENDENTE,
            cfop="5.102",
            processando_desde=timezone.now(),
        )
        cliente = mock.Mock()

        resultado = enviar_para_emissao(pedido, client=cliente)

        self.assertEqual(resultado.pk, nota.pk)
        cliente.criar_nfe.assert_not_called()


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


class A01RegistroAposCancelamentoTests(BaseFiscalAuditoriaTests):
    def test_primeiro_registro_apos_cancelamento_e_rejeitado(self):
        pedido = self._pedido(status=Pedido.Status.PAGO)
        cancelar_pedido_padrao(
            pedido=pedido,
            justificativa="Antes da primeira nota",
            usuario=self.gestor,
        )
        self.client.force_login(self.gestor)

        resposta = self.client.post(
            reverse("fiscal:nota_manual", args=[pedido.pk]),
            {"numero": "R01", "chave_acesso": CHAVE_SAIDA},
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(
            NotaFiscal.objects.filter(
                pedido=pedido, tipo=NotaFiscal.Tipo.SAIDA
            ).exists()
        )


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

class L01AutoridadeTentativaTests(BaseFiscalAuditoriaTests):
    CHAVE_MANUAL = "29260811111111111111111111111111111111111111"
    CHAVE_API_A = "29260822222222222222222222222222222222222222"
    CHAVE_API_B = "29260833333333333333333333333333333333333333"

    def _nota_em_erro(self, pedido):
        return NotaFiscal.objects.create(
            pedido=pedido,
            tipo=NotaFiscal.Tipo.SAIDA,
            status=NotaFiscal.Status.ERRO,
            cfop="5.102",
        )

    def _post_manual(self):
        return self.client.post(
            reverse("fiscal:nota_manual", args=[self.pedido.pk]),
            {
                "numero": "MANUAL",
                "chave_acesso": self.CHAVE_MANUAL,
                "link_documento": "https://exemplo.com/manual.pdf",
            },
        )

    def _preparar_cenario(self):
        self.pedido = self._pedido(status=Pedido.Status.PAGO)
        nota = self._nota_em_erro(self.pedido)
        self.client.force_login(self.gestor)
        return nota

    class _ManualDuranteLease:
        def __init__(self, teste):
            self.teste = teste
            self.resposta = None

        def criar_nfe(self, pedido):
            self.resposta = self.teste._post_manual()
            return {
                "numero": "API-A",
                "chave": self.teste.CHAVE_API_A,
                "link": "https://exemplo.com/api-a",
            }

    class _ManualDepoisDeExpirar:
        def __init__(self, teste, *, cancelar=False, erro=False):
            self.teste = teste
            self.cancelar = cancelar
            self.erro = erro
            self.resposta = None

        def criar_nfe(self, pedido):
            nota = NotaFiscal.objects.get(
                pedido=pedido, tipo=NotaFiscal.Tipo.SAIDA
            )
            NotaFiscal.objects.filter(pk=nota.pk).update(
                processando_desde=(
                    timezone.now()
                    - LEASE_EMISSAO
                    - timedelta(seconds=1)
                )
            )
            self.resposta = self.teste._post_manual()
            if self.cancelar:
                nota.refresh_from_db()
                cancelar_nota_fiscal(
                    nota,
                    motivo="Cancelamento durante tentativa antiga",
                    usuario=self.teste.gestor,
                )
            if self.erro:
                raise ErroFiscal("falha da tentativa antiga")
            return {
                "numero": "API-A",
                "chave": self.teste.CHAVE_API_A,
                "link": "https://exemplo.com/api-a",
            }

    class _TentativaNovaAtiva:
        def __init__(self, teste, token):
            self.teste = teste
            self.token = token

        def criar_nfe(self, pedido):
            NotaFiscal.objects.filter(
                pedido=pedido, tipo=NotaFiscal.Tipo.SAIDA
            ).update(
                tentativa_atual=self.token,
                processando_desde=timezone.now(),
                status=NotaFiscal.Status.PENDENTE,
            )
            raise ErroFiscal("falha da tentativa antiga")

    class _TentativaNovaComSucesso:
        def __init__(self, teste, *, resultado_antigo):
            self.teste = teste
            self.resultado_antigo = resultado_antigo

        def criar_nfe(self, pedido):
            NotaFiscal.objects.filter(
                pedido=pedido, tipo=NotaFiscal.Tipo.SAIDA
            ).update(
                processando_desde=(
                    timezone.now()
                    - LEASE_EMISSAO
                    - timedelta(seconds=1)
                )
            )

            class ClienteB:
                def criar_nfe(self, pedido_b):
                    return {
                        "numero": "API-B",
                        "chave": L01AutoridadeTentativaTests.CHAVE_API_B,
                        "link": "https://exemplo.com/api-b",
                    }

            self.teste._resultado_b = enviar_para_emissao(
                pedido, client=ClienteB()
            )
            if self.resultado_antigo == "erro":
                raise ErroFiscal("falha da tentativa antiga")
            return {
                "numero": "API-A",
                "chave": self.teste.CHAVE_API_A,
                "link": "https://exemplo.com/api-a",
            }

    def test_manual_durante_lease_ativo_e_bloqueado(self):
        nota = self._preparar_cenario()
        cliente = self._ManualDuranteLease(self)

        resultado = enviar_para_emissao(self.pedido, client=cliente)

        self.assertEqual(cliente.resposta.status_code, 200)
        self.assertContains(cliente.resposta, "emissão automática em andamento")
        nota.refresh_from_db()
        self.assertEqual(resultado.pk, nota.pk)
        self.assertEqual(nota.status, NotaFiscal.Status.AUTORIZADA)
        self.assertEqual(nota.numero, "API-A")
        self.assertEqual(nota.chave_acesso, self.CHAVE_API_A)
        self.assertEqual(nota.origem, NotaFiscal.Origem.API)
        self.assertIsNone(nota.tentativa_atual)
        self.assertIsNone(nota.processando_desde)

    def test_sucesso_antigo_nao_substitui_manual(self):
        nota = self._preparar_cenario()
        cliente = self._ManualDepoisDeExpirar(self)

        resultado = enviar_para_emissao(self.pedido, client=cliente)

        self.assertEqual(cliente.resposta.status_code, 302)
        nota.refresh_from_db()
        self.assertEqual(resultado.pk, nota.pk)
        self.assertEqual(nota.status, NotaFiscal.Status.AUTORIZADA)
        self.assertEqual(nota.numero, "MANUAL")
        self.assertEqual(nota.chave_acesso, self.CHAVE_MANUAL)
        self.assertEqual(nota.origem, NotaFiscal.Origem.MANUAL)
        self.assertEqual(
            nota.resultado_externo["eventos"][-1]["tipo"], "sucesso"
        )
        self.assertEqual(
            nota.resultado_externo["eventos"][-1]["resultado"]["numero"],
            "API-A",
        )
        self.assertTrue(
            Aviso.objects.filter(
                tipo=Aviso.Tipo.FISCAL_ERRO,
                objeto_id=str(nota.pk),
            ).exists()
        )
        self.assertTrue(
            LogAuditoria.objects.filter(
                acao="fiscal.resultado_externo_obsoleto",
                objeto_id=str(nota.pk),
            ).exists()
        )
        self.assertTrue(
            LogAuditoria.objects.filter(
                acao="fiscal.tentativa_manual_assumida",
                objeto_id=str(nota.pk),
            ).exists()
        )

    def test_erro_antigo_nao_rebaixa_manual_autorizada(self):
        nota = self._preparar_cenario()
        cliente = self._ManualDepoisDeExpirar(self, erro=True)

        enviar_para_emissao(self.pedido, client=cliente)

        nota.refresh_from_db()
        self.assertEqual(nota.status, NotaFiscal.Status.AUTORIZADA)
        self.assertEqual(nota.numero, "MANUAL")
        self.assertEqual(nota.chave_acesso, self.CHAVE_MANUAL)
        self.assertEqual(
            nota.resultado_externo["eventos"][-1]["tipo"], "erro"
        )

    def test_erro_antigo_nao_desfaz_cancelamento(self):
        nota = self._preparar_cenario()
        cliente = self._ManualDepoisDeExpirar(
            self, cancelar=True, erro=True
        )

        enviar_para_emissao(self.pedido, client=cliente)

        nota.refresh_from_db()
        self.assertEqual(nota.status, NotaFiscal.Status.CANCELADA)
        self.assertEqual(nota.numero, "MANUAL")
        self.assertEqual(nota.chave_acesso, self.CHAVE_MANUAL)
        self.assertEqual(
            nota.resultado_externo["eventos"][-1]["tipo"], "erro"
        )

    def test_resultado_antigo_nao_limpa_claim_novo_ativo(self):
        nota = self._preparar_cenario()
        token_novo = uuid.uuid4()
        cliente = self._TentativaNovaAtiva(self, token_novo)

        enviar_para_emissao(self.pedido, client=cliente)

        nota.refresh_from_db()
        self.assertEqual(nota.status, NotaFiscal.Status.PENDENTE)
        self.assertEqual(nota.tentativa_atual, token_novo)
        self.assertIsNotNone(nota.processando_desde)
        self.assertEqual(
            nota.resultado_externo["eventos"][-1]["tipo"], "erro"
        )

    def test_resultado_antigo_nao_desfaz_sucesso_de_b(self):
        nota = self._preparar_cenario()
        cliente = self._TentativaNovaComSucesso(
            self, resultado_antigo="erro"
        )

        enviar_para_emissao(self.pedido, client=cliente)

        nota.refresh_from_db()
        self.assertEqual(nota.status, NotaFiscal.Status.AUTORIZADA)
        self.assertEqual(nota.numero, "API-B")
        self.assertEqual(nota.chave_acesso, self.CHAVE_API_B)
        self.assertIsNone(nota.tentativa_atual)
        self.assertTrue(
            Aviso.objects.filter(
                tipo=Aviso.Tipo.FISCAL_ERRO,
                objeto_id=str(nota.pk),
            ).exists()
        )

    def test_sucesso_antigo_apos_cancelamento_fica_como_evidencia(self):
        nota = self._preparar_cenario()
        cliente = self._ManualDepoisDeExpirar(
            self, cancelar=True, erro=False
        )

        enviar_para_emissao(self.pedido, client=cliente)

        nota.refresh_from_db()
        self.assertEqual(nota.status, NotaFiscal.Status.CANCELADA)
        self.assertEqual(nota.numero, "MANUAL")
        self.assertEqual(nota.chave_acesso, self.CHAVE_MANUAL)
        evento = nota.resultado_externo["eventos"][-1]
        self.assertEqual(evento["tipo"], "sucesso")
        self.assertEqual(evento["resultado"]["numero"], "API-A")
        self.assertEqual(evento["resultado"]["chave"], self.CHAVE_API_A)
        self.assertTrue(
            LogAuditoria.objects.filter(
                acao="fiscal.resultado_externo_obsoleto",
                objeto_id=str(nota.pk),
            ).exists()
        )

    def test_erro_com_token_atual_em_documento_terminal_nao_rebaixa(self):
        nota = self._preparar_cenario()

        class ClienteQueConfirmaDireto:
            def criar_nfe(self, pedido):
                NotaFiscal.objects.filter(pk=nota.pk).update(
                    status=NotaFiscal.Status.AUTORIZADA,
                    numero="MANUAL-DIRETO",
                    chave_acesso="29260844444444444444444444444444444444444444",
                )
                raise ErroFiscal("falha após confirmação direta")

        enviar_para_emissao(self.pedido, client=ClienteQueConfirmaDireto())

        nota.refresh_from_db()
        self.assertEqual(nota.status, NotaFiscal.Status.AUTORIZADA)
        self.assertEqual(nota.numero, "MANUAL-DIRETO")
        self.assertIsNone(nota.tentativa_atual)
        self.assertEqual(
            nota.resultado_externo["eventos"][-1]["tipo"], "erro"
        )

    def test_sucesso_com_token_atual_em_documento_terminal_nao_substitui(self):
        nota = self._preparar_cenario()
        chave_api = self.CHAVE_API_A

        class ClienteQueCancelaDireto:
            def criar_nfe(self, pedido):
                NotaFiscal.objects.filter(pk=nota.pk).update(
                    status=NotaFiscal.Status.CANCELADA,
                    numero="CANCELADA-DIRETO",
                    chave_acesso="29260855555555555555555555555555555555555555",
                )
                return {
                    "numero": "API-A",
                    "chave": chave_api,
                    "link": "https://exemplo.com/api-a",
                }

        enviar_para_emissao(self.pedido, client=ClienteQueCancelaDireto())

        nota.refresh_from_db()
        self.assertEqual(nota.status, NotaFiscal.Status.CANCELADA)
        self.assertEqual(nota.numero, "CANCELADA-DIRETO")
        self.assertIsNone(nota.tentativa_atual)
        self.assertEqual(
            nota.resultado_externo["eventos"][-1]["tipo"], "sucesso"
        )

    def test_conflito_de_chave_preserva_resposta_externa(self):
        nota = self._preparar_cenario()
        outro_pedido = self._pedido(status=Pedido.Status.PAGO)
        NotaFiscal.objects.create(
            pedido=outro_pedido,
            tipo=NotaFiscal.Tipo.SAIDA,
            status=NotaFiscal.Status.AUTORIZADA,
            cfop="5.102",
            chave_acesso=self.CHAVE_API_A,
        )
        chave_api = self.CHAVE_API_A

        class ClienteComChaveDuplicada:
            def criar_nfe(self, pedido):
                return {
                    "numero": "API-A",
                    "chave": chave_api,
                    "link": "https://exemplo.com/api-a",
                }

        enviar_para_emissao(
            self.pedido, client=ClienteComChaveDuplicada()
        )

        nota.refresh_from_db()
        self.assertEqual(nota.status, NotaFiscal.Status.ERRO)
        self.assertIsNone(nota.tentativa_atual)
        evento = nota.resultado_externo["eventos"][-1]
        self.assertEqual(evento["tipo"], "conflito_chave")
        self.assertEqual(evento["resultado"]["numero"], "API-A")
        self.assertEqual(evento["resultado"]["chave"], self.CHAVE_API_A)

    def test_resultado_externo_repetido_nao_duplica_efeitos(self):
        from fiscal.services import _registrar_resultado_externo

        nota = self._preparar_cenario()
        token = uuid.uuid4()
        with transaction.atomic():
            _registrar_resultado_externo(
                nota,
                token=token,
                tipo="sucesso",
                resultado={"numero": "API-A", "chave": self.CHAVE_API_A},
                motivo="resultado repetido",
            )
            _registrar_resultado_externo(
                nota,
                token=token,
                tipo="sucesso",
                resultado={"numero": "API-A", "chave": self.CHAVE_API_A},
                motivo="resultado repetido",
            )

        nota.refresh_from_db()
        eventos = [
            evento
            for evento in nota.resultado_externo["eventos"]
            if evento["tentativa"] == str(token)
        ]
        self.assertEqual(len(eventos), 1)
        self.assertEqual(
            Aviso.objects.filter(
                tipo=Aviso.Tipo.FISCAL_ERRO,
                objeto_id=str(nota.pk),
            ).count(),
            1,
        )
        self.assertEqual(
            LogAuditoria.objects.filter(
                acao="fiscal.resultado_externo_obsoleto",
                objeto_id=str(nota.pk),
            ).count(),
            1,
        )

    def test_resultados_externos_distintos_ficam_visiveis(self):
        from fiscal.services import _registrar_resultado_externo

        nota = self._preparar_cenario()
        token_sucesso = uuid.uuid4()
        token_erro = uuid.uuid4()
        with transaction.atomic():
            _registrar_resultado_externo(
                nota,
                token=token_sucesso,
                tipo="sucesso",
                resultado={"numero": "API-A", "chave": self.CHAVE_API_A},
                motivo="conflito de sucesso",
            )
            _registrar_resultado_externo(
                nota,
                token=token_erro,
                tipo="erro",
                resultado={"erro": "falha antiga"},
                motivo="conflito de erro",
            )

        nota.refresh_from_db()
        self.assertEqual(len(nota.resultado_externo["eventos"]), 2)
        avisos = Aviso.objects.filter(
            tipo=Aviso.Tipo.FISCAL_ERRO,
            objeto_id=str(nota.pk),
        )
        self.assertEqual(avisos.count(), 2)
        self.assertTrue(
            any("API-A" in aviso.mensagem for aviso in avisos)
        )
        self.assertEqual(
            LogAuditoria.objects.filter(
                acao="fiscal.resultado_externo_obsoleto",
                objeto_id=str(nota.pk),
            ).count(),
            2,
        )
