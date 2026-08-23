from django.core.management import call_command
from django.test import TestCase

from analytics.models import Aviso
from customers.factories import ClienteFactory
from customers.models import Cliente
from fiscal.models import NotaFiscal
from sales.factories import ItemPedidoFactory, PedidoFactory
from sales.models import Pedido


def pedido_pago(cliente=None):
    pedido = PedidoFactory(
        status=Pedido.Status.PAGO,
        cliente=cliente or ClienteFactory(nome="João Fazendeiro"),
    )
    ItemPedidoFactory(pedido=pedido)
    return pedido


class EmissaoFiscalTests(TestCase):
    def test_pedido_pago_elegivel_e_emitido(self):
        pedido = pedido_pago()

        call_command("processar_fiscal", verbosity=0)

        nota = NotaFiscal.objects.get(pedido=pedido)
        self.assertEqual(nota.status, NotaFiscal.Status.AUTORIZADA)
        self.assertTrue(nota.numero)
        self.assertTrue(nota.chave_acesso)
        self.assertEqual(nota.origem, NotaFiscal.Origem.API)
        self.assertFalse(
            Aviso.objects.filter(tipo=Aviso.Tipo.PAGO_SEM_NFE).exists()
        )

    def test_documento_invalido_bloqueia_envio_com_aviso(self):
        cliente_ruim = ClienteFactory(nome="Doc Ruim")
        # Simula documento corrompido/legado (a entrada sempre valida).
        Cliente.objects.filter(pk=cliente_ruim.pk).update(documento="12345678901")
        pedido = pedido_pago(cliente=cliente_ruim)

        call_command("processar_fiscal", verbosity=0)

        pedido.refresh_from_db()
        self.assertEqual(pedido.status, Pedido.Status.PAGO)
        self.assertFalse(NotaFiscal.objects.exists())
        aviso = Aviso.objects.get(tipo=Aviso.Tipo.FISCAL_DOCUMENTO)
        self.assertIn("inválido", aviso.mensagem)

    def test_erro_da_api_gera_aviso_e_permite_reprocessar(self):
        pedido = pedido_pago(cliente=ClienteFactory(nome="Cliente ERRO"))

        call_command("processar_fiscal", verbosity=0)

        nota = NotaFiscal.objects.get(pedido=pedido)
        self.assertEqual(nota.status, NotaFiscal.Status.ERRO)
        self.assertEqual(nota.tentativas, 1)
        pedido.refresh_from_db()
        self.assertEqual(pedido.status, Pedido.Status.PAGO)
        aviso = Aviso.objects.filter(tipo=Aviso.Tipo.FISCAL_ERRO).latest("id")
        self.assertIn("Falha ao emitir", aviso.mensagem)

        # Corrigido o motivo do erro, o reprocessamento autoriza.
        pedido.cliente.nome = "Cliente Corrigido"
        pedido.cliente.save()
        call_command("processar_fiscal", verbosity=0)
        nota.refresh_from_db()
        self.assertEqual(nota.status, NotaFiscal.Status.AUTORIZADA)

    def test_nota_autorizada_nao_duplica(self):
        pedido = pedido_pago()
        call_command("processar_fiscal", verbosity=0)
        nota = NotaFiscal.objects.get(pedido=pedido)

        call_command("processar_fiscal", verbosity=0)

        nota.refresh_from_db()
        self.assertEqual(NotaFiscal.objects.count(), 1)
        self.assertEqual(nota.tentativas, 1)
