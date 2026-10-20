"""R10: revisão administrativa de vínculo com justificativa e auditoria."""

from django.test import TestCase
from django.urls import reverse

from accounts.models import Usuario
from core.models import LogAuditoria
from customers.factories import ClienteFactory
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
