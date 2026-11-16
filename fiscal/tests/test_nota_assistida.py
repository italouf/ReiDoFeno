"""NF-e assistida via IOB (ADR-006)."""

import json
import tempfile
from decimal import Decimal

from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import Usuario
from catalog.factories import ProdutoFactory
from core.factories import UnidadeFactory
from core.models import LogAuditoria
from customers.factories import ClienteFactory
from fiscal.models import NotaFiscal
from fiscal.services import exportar_para_iob, exportar_para_iob_csv
from sales.factories import ItemPedidoFactory, PedidoFactory
from sales.models import Pedido

CHAVE = "29260812345678901234567890123456789012345678"


class BaseNotaAssistidaTests(TestCase):
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
        cls.emissor = Usuario.objects.create_user(
            username="emissor", password=cls.senha
        )
        cls.emissor.groups.add(Group.objects.get(name="Emissor Fiscal"))
        cls.vendedor = Usuario.objects.create_user(
            username="vendedor", password=cls.senha
        )
        cls.vendedor.groups.add(Group.objects.get(name="Vendedor"))

    def criar_pedido_pago(self, *, cliente=None, nome_produto="Feno", ncm="1214.90.00"):
        cliente = cliente or ClienteFactory(
            nome="Cliente Teste",
            documento="52998224725",
            tipo_pessoa="fisica",
            logradouro="Rua A",
            numero="10",
            bairro="Centro",
            cidade="Feira de Santana",
            uf="BA",
            cep="44000000",
        )
        unidade = UnidadeFactory(uf="BA")
        produto = ProdutoFactory(nome=nome_produto, ncm=ncm)
        pedido = PedidoFactory(
            cliente=cliente,
            unidade=unidade,
            status=Pedido.Status.PAGO,
            status_financeiro=Pedido.StatusFinanceiro.PAGO,
            financeiro_conciliado=True,
            logradouro="Rua A",
            numero_endereco="10",
            bairro="Centro",
            cidade="Feira de Santana",
            uf="BA",
            cep="44000000",
        )
        ItemPedidoFactory(
            pedido=pedido,
            produto=produto,
            produto_nome=nome_produto,
            quantidade=Decimal("2.00"),
            preco_unitario=Decimal("50.00"),
            custo_unitario=Decimal("30.00"),
        )
        pedido.recalcular_totais()
        return pedido

    def pdf(self, nome="nfe_123.pdf"):
        return SimpleUploadedFile(
            nome, b"%PDF-1.4 fake", content_type="application/pdf"
        )


class ExportacaoIOBTests(BaseNotaAssistidaTests):
    def test_exportar_para_iob_dados_do_pedido(self):
        pedido = self.criar_pedido_pago()

        dados = exportar_para_iob(pedido)

        self.assertEqual(dados["cliente"]["nome"], "Cliente Teste")
        self.assertEqual(dados["cliente"]["documento"], "52998224725")
        self.assertEqual(dados["cliente"]["tipo_pessoa"], "fisica")
        self.assertEqual(
            dados["cliente"]["endereco"]["logradouro"], "Rua A"
        )
        self.assertEqual(dados["cliente"]["endereco"]["cidade"], "Feira de Santana")
        self.assertEqual(len(dados["itens"]), 1)
        self.assertEqual(dados["itens"][0]["produto"], "Feno")
        self.assertEqual(dados["itens"][0]["ncm"], "1214.90.00")
        self.assertEqual(dados["itens"][0]["quantidade"], 2.0)
        self.assertEqual(dados["itens"][0]["valor_unitario"], 50.0)
        self.assertEqual(dados["itens"][0]["valor_total"], 100.0)
        self.assertEqual(dados["total"], 100.0)

    def test_exportar_para_iob_csv_escapa_formula(self):
        cliente = ClienteFactory(nome="=SUM(A1)", documento="52998224725")
        pedido = self.criar_pedido_pago(cliente=cliente)

        csv_texto = exportar_para_iob_csv(pedido)

        self.assertIn("'=SUM(A1)", csv_texto)
        self.assertIn("Feno", csv_texto)
        self.assertIn("1214.90.00", csv_texto)

    def test_emissor_exporta_json_pelo_endpoint(self):
        pedido = self.criar_pedido_pago()
        self.client.force_login(self.emissor)

        resposta = self.client.get(
            reverse("fiscal:exportar_iob", args=[pedido.pk]) + "?formato=json"
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertIn("application/json", resposta["Content-Type"])
        self.assertIn("iob", resposta["Content-Disposition"])
        dados = json.loads(resposta.content)
        self.assertEqual(dados["cliente"]["nome"], "Cliente Teste")
        self.assertEqual(dados["total"], 100.0)

    def test_emissor_exporta_csv_pelo_endpoint(self):
        pedido = self.criar_pedido_pago()
        self.client.force_login(self.emissor)

        resposta = self.client.get(
            reverse("fiscal:exportar_iob", args=[pedido.pk]) + "?formato=csv"
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertIn("text/csv", resposta["Content-Type"])
        self.assertIn("Feno", resposta.content.decode())

    def test_vendedor_nao_exporta(self):
        pedido = self.criar_pedido_pago()
        self.client.force_login(self.vendedor)

        resposta = self.client.get(
            reverse("fiscal:exportar_iob", args=[pedido.pk])
        )

        self.assertEqual(resposta.status_code, 403)


class AnexoNotaTests(BaseNotaAssistidaTests):
    def test_operador_anexa_pdf_e_snapshot(self):
        pedido = self.criar_pedido_pago()
        self.client.force_login(self.emissor)

        resposta = self.client.post(
            reverse("fiscal:nota_anexar", args=[pedido.pk]),
            {
                "numero": "123",
                "serie": "1",
                "chave_acesso": CHAVE,
                "data_emissao": "2026-11-10T14:30",
                "pdf": self.pdf(),
            },
        )

        self.assertEqual(resposta.status_code, 302)
        nota = NotaFiscal.objects.get(pedido=pedido, tipo=NotaFiscal.Tipo.SAIDA)
        self.assertEqual(nota.status, NotaFiscal.Status.ANEXADA)
        self.assertEqual(nota.numero, "123")
        self.assertEqual(nota.serie, "1")
        self.assertEqual(nota.chave_acesso, CHAVE)
        self.assertEqual(nota.cliente_nome, "Cliente Teste")
        self.assertEqual(nota.cliente_documento, "52998224725")
        self.assertEqual(nota.cliente_tipo_pessoa, "fisica")
        self.assertIn("Rua A", nota.cliente_endereco)
        self.assertEqual(nota.valor_total, Decimal("100.00"))
        self.assertEqual(len(nota.itens_json), 1)
        self.assertEqual(nota.itens_json[0]["produto"], "Feno")
        self.assertEqual(nota.itens_json[0]["ncm"], "1214.90.00")
        self.assertIsNotNone(nota.pdf)
        self.assertTrue(nota.pdf.name.endswith(".pdf"))
        self.assertIsNotNone(nota.data_emissao)
        log = LogAuditoria.objects.filter(
            acao="fiscal.nota_anexada",
            objeto_id=str(nota.pk),
        ).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.usuario, self.emissor)

    def test_anexo_pdf_invalido_e_rejeitado(self):
        pedido = self.criar_pedido_pago()
        self.client.force_login(self.emissor)

        resposta = self.client.post(
            reverse("fiscal:nota_anexar", args=[pedido.pk]),
            {
                "numero": "123",
                "pdf": SimpleUploadedFile(
                    "nota.txt", b"texto", content_type="text/plain"
                ),
            },
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertIn("pdf", resposta.context["form"].errors)
        self.assertFalse(NotaFiscal.objects.filter(pedido=pedido).exists())

    def test_anexar_nota_autorizada_e_rejeitado(self):
        pedido = self.criar_pedido_pago()
        self.client.force_login(self.emissor)
        self.client.post(
            reverse("fiscal:nota_manual", args=[pedido.pk]),
            {
                "numero": "123",
                "chave_acesso": CHAVE,
                "serie": "1",
                "data_emissao": "2026-11-10T14:30",
                "pdf": self.pdf(),
            },
        )

        resposta = self.client.post(
            reverse("fiscal:nota_anexar", args=[pedido.pk]),
            {"pdf": self.pdf("outro.pdf")},
        )

        self.assertEqual(resposta.status_code, 400)


class RegistroNotaCompletaTests(BaseNotaAssistidaTests):
    def test_registrar_nota_completa_preserva_snapshot(self):
        pedido = self.criar_pedido_pago()
        self.client.force_login(self.emissor)

        resposta = self.client.post(
            reverse("fiscal:nota_manual", args=[pedido.pk]),
            {
                "numero": "123456",
                "serie": "1",
                "chave_acesso": CHAVE,
                "data_emissao": "2026-11-10T14:30",
                "pdf": self.pdf(),
            },
        )

        self.assertEqual(resposta.status_code, 302)
        nota = NotaFiscal.objects.get(pedido=pedido, tipo=NotaFiscal.Tipo.SAIDA)
        self.assertEqual(nota.status, NotaFiscal.Status.AUTORIZADA)
        self.assertEqual(nota.cliente_nome, "Cliente Teste")
        self.assertEqual(nota.valor_total, Decimal("100.00"))
        self.assertIsNotNone(nota.pdf)
        self.assertIsNotNone(nota.data_emissao)

    def test_snapshot_nao_muda_quando_cliente_edita(self):
        pedido = self.criar_pedido_pago()
        self.client.force_login(self.emissor)
        self.client.post(
            reverse("fiscal:nota_manual", args=[pedido.pk]),
            {
                "numero": "123456",
                "serie": "1",
                "chave_acesso": CHAVE,
                "data_emissao": "2026-11-10T14:30",
            },
        )

        cliente = pedido.cliente
        cliente.nome = "Cliente Alterado"
        cliente.save(update_fields=["nome"])

        nota = NotaFiscal.objects.get(pedido=pedido, tipo=NotaFiscal.Tipo.SAIDA)
        self.assertEqual(nota.cliente_nome, "Cliente Teste")
