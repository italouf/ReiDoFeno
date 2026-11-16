"""Retenção fiscal na anonimização LGPD (ADR-012)."""

from datetime import datetime

from django.test import TestCase
from django.utils import timezone

from core.models import LogAuditoria
from customers.factories import ClienteFactory
from customers.models import Cliente
from fiscal.models import NotaFiscal
from privacy.services import anonimizar_cliente
from sales.factories import PedidoFactory
from sales.models import Pedido


class RetencaoDadosFiscaisTests(TestCase):
    def criar_nota(self, cliente, *, nome="Cliente Original", documento="52998224725"):
        pedido = PedidoFactory(status=Pedido.Status.PAGO, cliente=cliente)
        return NotaFiscal.objects.create(
            pedido=pedido,
            tipo=NotaFiscal.Tipo.SAIDA,
            numero="123",
            chave_acesso=str(pedido.pk).zfill(44),
            data_emissao=timezone.make_aware(datetime(2026, 11, 10, 14, 30)),
            cliente_nome=nome,
            cliente_documento=documento,
            cliente_tipo_pessoa="fisica",
            cliente_endereco="Rua A, 10 - Centro, Feira de Santana/BA",
            valor_total=100,
            itens_json=[{"produto": "Feno", "quantidade": "2"}],
        )

    def test_nota_preserva_dados_se_cliente_excluido(self):
        cliente = ClienteFactory(
            nome="Cliente Original", documento="52998224725"
        )
        nota = self.criar_nota(cliente)

        houve_anonimizacao = anonimizar_cliente(cliente)

        self.assertTrue(houve_anonimizacao)
        cliente.refresh_from_db()
        self.assertNotEqual(cliente.nome, "Cliente Original")
        self.assertTrue(cliente.documento.startswith("999"))

        nota.refresh_from_db()
        self.assertEqual(nota.cliente_nome, "Cliente Original")
        self.assertEqual(nota.cliente_documento, "52998224725")
        self.assertEqual(nota.itens_json[0]["produto"], "Feno")

    def test_anonimizacao_com_nota_gera_auditoria(self):
        cliente = ClienteFactory(
            nome="Cliente Original", documento="52998224725"
        )
        self.criar_nota(cliente)

        anonimizar_cliente(cliente)

        log = LogAuditoria.objects.filter(
            acao="cliente_anonimizado_com_notas",
            objeto_id=str(cliente.pk),
        ).first()
        self.assertIsNotNone(log)
        self.assertTrue(log.depois["notas_preservadas"])

    def test_anonimizacao_com_pedido_sem_nota_gera_auditoria(self):
        cliente = ClienteFactory()
        PedidoFactory(status=Pedido.Status.PAGO, cliente=cliente)

        anonimizar_cliente(cliente)

        self.assertTrue(
            LogAuditoria.objects.filter(
                acao="cliente_anonimizado_com_pedidos",
                objeto_id=str(cliente.pk),
            ).exists()
        )

    def test_cliente_sem_registro_e_excluido(self):
        cliente = ClienteFactory()

        houve_anonimizacao = anonimizar_cliente(cliente)

        self.assertFalse(houve_anonimizacao)
        self.assertFalse(Cliente.objects.filter(pk=cliente.pk).exists())

    def test_nota_tem_data_de_retencao(self):
        cliente = ClienteFactory(documento="52998224725")
        nota = self.criar_nota(cliente)

        self.assertEqual(nota.retido_ate.isoformat(), "2031-11-10")
