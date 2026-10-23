from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from analytics.models import Aviso
from customers.factories import ClienteFactory
from customers.models import Cliente
from fiscal.models import NotaFiscal
from sales.factories import (
    ItemPedidoFactory,
    PagamentoFactory,
    PedidoFactory,
)
from sales.models import Pagamento, Pedido
from sales.services import registrar_devolucao


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
        self.assertEqual(len(nota.chave_acesso), 44)
        self.assertEqual(nota.cfop, "5.102")
        self.assertEqual(nota.origem, NotaFiscal.Origem.API)
        self.assertFalse(
            Aviso.objects.filter(tipo=Aviso.Tipo.PAGO_SEM_NFE).exists()
        )

    def test_nota_emitida_permite_devolucao_com_cfop_inverso(self):
        pedido = pedido_pago()
        PagamentoFactory(
            pedido=pedido,
            valor=pedido.total,
            status=Pagamento.Status.APROVADO,
            aprovado_em=timezone.now(),
        )
        call_command("processar_fiscal", verbosity=0)
        nota_saida = NotaFiscal.objects.get(
            pedido=pedido, tipo=NotaFiscal.Tipo.SAIDA
        )

        nota_entrada = registrar_devolucao(
            pedido=pedido,
            justificativa="Devolução após entrega",
            usuario=self._usuario_fiscal(),
        )

        self.assertEqual(nota_saida.cfop, "5.102")
        self.assertEqual(nota_entrada.cfop, "1.202")
        self.assertEqual(
            nota_entrada.chave_referenciada, nota_saida.chave_acesso
        )

    def _usuario_fiscal(self):
        from django.contrib.auth.models import Group

        from accounts.models import Usuario

        Grupo = Group.objects.get_or_create(name="Administrador")[0]
        usuario = Usuario.objects.create_user(
            username="fiscal_teste", password="senha-forte-123"
        )
        usuario.groups.add(Grupo)
        return usuario

    def test_financeiro_pago_com_andamento_aguardando_e_emitido(self):
        pedido = PedidoFactory(
            status=Pedido.Status.AGUARDANDO_PAGAMENTO,
            status_financeiro=Pedido.StatusFinanceiro.PAGO,
            cliente=ClienteFactory(nome="Cliente Financeiro"),
        )
        ItemPedidoFactory(pedido=pedido)

        call_command("processar_fiscal", verbosity=0)

        nota = NotaFiscal.objects.get(pedido=pedido)
        self.assertEqual(nota.status, NotaFiscal.Status.AUTORIZADA)
        self.assertEqual(pedido.status, Pedido.Status.AGUARDANDO_PAGAMENTO)

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
