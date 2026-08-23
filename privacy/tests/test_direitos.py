import json

from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from accounts.models import Usuario
from customers.factories import ClienteFactory
from customers.models import Cliente
from privacy.models import SolicitacaoTitular
from privacy.services import anonimizar_cliente
from sales.factories import ItemPedidoFactory, PedidoFactory
from sales.models import Pedido


class DireitosTitularTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_groups", verbosity=0)
        cls.admin = Usuario.objects.create_user(
            username="admin", password="senha-forte-123"
        )
        cls.admin.groups.add(Group.objects.get(name="Administrador"))

    def _login_com_cliente(self, cliente):
        usuario = Usuario.objects.create_user(
            username=f"user{cliente.pk}", password="senha-forte-123"
        )
        cliente.usuario = usuario
        cliente.save()
        self.client.force_login(usuario)
        return usuario

    def test_exportacao_gera_arquivo_e_registra_concluida(self):
        cliente = ClienteFactory(nome="Maria Export")
        pedido = PedidoFactory(status=Pedido.Status.PAGO, cliente=cliente)
        ItemPedidoFactory(pedido=pedido)
        self._login_com_cliente(cliente)

        resposta = self.client.post(
            reverse("privacy:nova_solicitacao"),
            {"tipo": SolicitacaoTitular.Tipo.EXPORTACAO},
        )
        self.assertEqual(resposta.status_code, 200)
        dados = json.loads(resposta.content)
        self.assertEqual(dados["cliente"]["nome"], "Maria Export")
        self.assertEqual(len(dados["pedidos"]), 1)

        solicitacao = SolicitacaoTitular.objects.get(cliente=cliente)
        self.assertEqual(solicitacao.tipo, "exportacao")
        self.assertEqual(solicitacao.status, "concluida")
        self.assertIsNotNone(solicitacao.concluida_em)

    def test_solicitacao_de_exclusao_fica_aberta_com_prazo(self):
        cliente = ClienteFactory()
        self._login_com_cliente(cliente)

        self.client.post(
            reverse("privacy:nova_solicitacao"),
            {"tipo": SolicitacaoTitular.Tipo.EXCLUSAO},
        )
        solicitacao = SolicitacaoTitular.objects.get(cliente=cliente)
        self.assertEqual(solicitacao.status, "aberta")
        self.assertTrue(solicitacao.prazo_limite)

    def test_exclusao_com_retencacao_fiscal_anonimiza(self):
        cliente = ClienteFactory(nome="Fulano de Tal", telefone="(75) 90000-0001",
                                 email="fulano@example.com")
        pedido = PedidoFactory(status=Pedido.Status.PAGO, cliente=cliente)
        ItemPedidoFactory(pedido=pedido)

        houve_anonimizacao = anonimizar_cliente(cliente)

        self.assertTrue(houve_anonimizacao)
        cliente.refresh_from_db()
        self.assertNotEqual(cliente.nome, "Fulano de Tal")
        self.assertTrue(cliente.documento.startswith("999"))
        self.assertNotEqual(cliente.documento, "52998224725")
        self.assertEqual(cliente.email, "")
        # Integridade fiscal preservada:
        pedido.refresh_from_db()
        self.assertEqual(pedido.status, Pedido.Status.PAGO)
        self.assertTrue(pedido.numero)

    def test_exclusao_sem_registro_fiscal_exclui_cadastro(self):
        cliente = ClienteFactory()

        houve_anonimizacao = anonimizar_cliente(cliente)

        self.assertFalse(houve_anonimizacao)
        self.assertFalse(Cliente.objects.filter(pk=cliente.pk).exists())

    def test_correcao_pelo_titular_e_auditada(self):
        cliente = ClienteFactory(telefone="(75) 11111-1111")
        usuario = self._login_com_cliente(cliente)
        usuario.groups.add(Group.objects.get(name="Cliente"))

        resposta = self.client.post(
            reverse("customers:cliente_editar", args=[cliente.pk]),
            {
                "nome": cliente.nome,
                "tipo_pessoa": "fisica",
                "documento": "529.982.247-25",
                "categoria": "varejo",
                "telefone": "(75) 92222-2222",
                "email": "novo@example.com",
                "logradouro": "", "numero": "", "bairro": "",
                "cidade": "", "uf": "", "cep": "", "preferencia": "",
            },
        )
        self.assertIn(resposta.status_code, (200, 302))
        from core.models import LogAuditoria

        self.assertTrue(
            LogAuditoria.objects.filter(acao="cliente.alterado").exists()
        )
