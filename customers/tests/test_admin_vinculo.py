"""R10: revisão administrativa de vínculo com justificativa e auditoria."""

from unittest import mock

from django.test import TestCase
from django.urls import reverse

from accounts.models import Usuario
from core.models import LogAuditoria
from customers.factories import ClienteFactory
from customers.models import Cliente
from sales.factories import PedidoFactory


class AdminVinculoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = Usuario.objects.create_superuser(
            username="admin-vinculo",
            email="admin@example.com",
            password="senha-forte-123",
        )
        cls.titular = Usuario.objects.create_user(
            username="titular-admin",
            email="titular-admin@example.com",
            password="senha-forte-123",
        )
        cls.outro_titular = Usuario.objects.create_user(
            username="outro-admin",
            email="outro-admin@example.com",
            password="senha-forte-123",
        )
        cls.cliente = ClienteFactory(
            usuario=cls.titular,
            vinculo_verificado=False,
            documento="52998224725",
        )

    def _dados(self, **overrides):
        dados = {
            "nome": self.cliente.nome,
            "tipo_pessoa": self.cliente.tipo_pessoa,
            "documento": self.cliente.documento,
            "categoria": self.cliente.categoria,
            "telefone": self.cliente.telefone,
            "email": self.cliente.email,
            "logradouro": "",
            "numero": "",
            "bairro": "",
            "cidade": "",
            "uf": "",
            "cep": "",
            "preferencia": "",
            "usuario": self.titular.pk,
            "vinculo_verificado": "on",
            "justificativa_vinculo": "Documento conferido pela operação.",
        }
        dados.update(overrides)
        return dados

    def test_admin_verifica_vinculo_com_justificativa(self):
        pedido = PedidoFactory(
            cliente=self.cliente,
            usuario_criador=self.titular,
            identidade_verificada=False,
        )
        self.client.force_login(self.admin)

        resposta = self.client.post(
            reverse("admin:customers_cliente_change", args=[self.cliente.pk]),
            self._dados(),
        )

        self.assertEqual(resposta.status_code, 302)
        self.cliente.refresh_from_db()
        pedido.refresh_from_db()
        self.assertTrue(self.cliente.vinculo_verificado)
        self.assertTrue(pedido.identidade_verificada)
        log = LogAuditoria.objects.get(
            acao="cliente.vinculo_revisado_admin",
            objeto_id=str(self.cliente.pk),
        )
        self.assertIn("Documento conferido", log.depois["justificativa"])
        self.assertFalse(log.antes["vinculo_verificado"])

    def test_admin_nao_altera_vinculo_sem_justificativa(self):
        self.client.force_login(self.admin)

        resposta = self.client.post(
            reverse("admin:customers_cliente_change", args=[self.cliente.pk]),
            self._dados(justificativa_vinculo=""),
        )

        self.assertEqual(resposta.status_code, 200)
        self.cliente.refresh_from_db()
        self.assertFalse(self.cliente.vinculo_verificado)

    def test_admin_revoga_vinculo_e_desvincula(self):
        self.cliente.vinculo_verificado = True
        self.cliente.save(update_fields=["vinculo_verificado"])
        pedido = PedidoFactory(
            cliente=self.cliente,
            usuario_criador=self.titular,
            identidade_verificada=True,
        )
        self.client.force_login(self.admin)

        resposta = self.client.post(
            reverse("admin:customers_cliente_change", args=[self.cliente.pk]),
            self._dados(
                vinculo_verificado="",
                justificativa_vinculo="Suspeita de apropriação de cadastro.",
            ),
        )

        self.assertEqual(resposta.status_code, 302)
        self.cliente.refresh_from_db()
        pedido.refresh_from_db()
        self.assertFalse(self.cliente.vinculo_verificado)
        self.assertIsNone(self.cliente.usuario)
        self.assertFalse(pedido.identidade_verificada)

    def test_admin_troca_usuario_nao_herda_verificacao_nem_historico(self):
        self.cliente.vinculo_verificado = True
        self.cliente.save(update_fields=["vinculo_verificado"])
        pedido = PedidoFactory(
            cliente=self.cliente,
            usuario_criador=self.titular,
            identidade_verificada=True,
        )
        self.client.force_login(self.admin)

        resposta = self.client.post(
            reverse("admin:customers_cliente_change", args=[self.cliente.pk]),
            self._dados(
                usuario=self.outro_titular.pk,
                vinculo_verificado="on",
                justificativa_vinculo="Troca de titular autorizada.",
            ),
        )

        self.assertEqual(resposta.status_code, 302)
        self.cliente.refresh_from_db()
        pedido.refresh_from_db()
        self.assertEqual(self.cliente.usuario, self.outro_titular)
        self.assertFalse(self.cliente.vinculo_verificado)
        self.assertFalse(pedido.identidade_verificada)
        log = LogAuditoria.objects.get(
            acao="cliente.identidade_alterada_admin",
            objeto_id=str(self.cliente.pk),
        )
        self.assertEqual(log.antes["usuario_id"], self.titular.pk)

    def test_admin_troca_email_reseta_verificacao_e_historico(self):
        self.cliente.vinculo_verificado = True
        self.cliente.save(update_fields=["vinculo_verificado"])
        pedido = PedidoFactory(
            cliente=self.cliente,
            usuario_criador=self.titular,
            identidade_verificada=True,
        )
        self.client.force_login(self.admin)

        resposta = self.client.post(
            reverse("admin:customers_cliente_change", args=[self.cliente.pk]),
            self._dados(
                email="novo-email-admin@example.com",
                vinculo_verificado="on",
                justificativa_vinculo="Atualização de contato.",
            ),
        )

        self.assertEqual(resposta.status_code, 302)
        self.cliente.refresh_from_db()
        pedido.refresh_from_db()
        self.assertEqual(self.cliente.email, "novo-email-admin@example.com")
        self.assertFalse(self.cliente.vinculo_verificado)
        self.assertFalse(pedido.identidade_verificada)

    def test_admin_troca_usuario_sem_justificativa_e_rejeitada(self):
        self.cliente.vinculo_verificado = True
        self.cliente.save(update_fields=["vinculo_verificado"])
        self.client.force_login(self.admin)

        resposta = self.client.post(
            reverse("admin:customers_cliente_change", args=[self.cliente.pk]),
            self._dados(
                usuario=self.outro_titular.pk,
                vinculo_verificado="on",
                justificativa_vinculo="",
            ),
        )

        self.assertEqual(resposta.status_code, 200)
        self.cliente.refresh_from_db()
        self.assertEqual(self.cliente.usuario, self.titular)

    def _dados_criacao(self, **overrides):
        dados = self._dados(
            nome="Cliente Novo Admin",
            documento="11144477735",
            email="novo-admin@example.com",
            usuario=self.outro_titular.pk,
            vinculo_verificado="on",
            justificativa_vinculo="Documento conferido na criação.",
        )
        dados.update(overrides)
        return dados

    def test_admin_criacao_verificada_exige_justificativa(self):
        self.client.force_login(self.admin)

        resposta = self.client.post(
            reverse("admin:customers_cliente_add"),
            self._dados_criacao(justificativa_vinculo=""),
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(
            Cliente.objects.filter(documento="11144477735").exists()
        )

    def test_admin_criacao_verificada_audita(self):
        self.client.force_login(self.admin)

        resposta = self.client.post(
            reverse("admin:customers_cliente_add"),
            self._dados_criacao(),
        )

        self.assertEqual(resposta.status_code, 302)
        cliente = Cliente.objects.get(documento="11144477735")
        self.assertTrue(cliente.vinculo_verificado)
        log = LogAuditoria.objects.get(
            acao="cliente.vinculo_revisado_admin",
            objeto_id=str(cliente.pk),
        )
        self.assertFalse(log.antes["vinculo_verificado"])
        self.assertTrue(log.depois["vinculo_verificado"])

    def test_falha_auditoria_reverte_criacao_verificada(self):
        self.client.force_login(self.admin)

        with mock.patch(
            "customers.services.registrar_auditoria",
            side_effect=RuntimeError("auditoria indisponível"),
        ):
            with self.assertRaises(RuntimeError):
                self.client.post(
                    reverse("admin:customers_cliente_add"),
                    self._dados_criacao(),
                )

        self.assertFalse(
            Cliente.objects.filter(documento="11144477735").exists()
        )
