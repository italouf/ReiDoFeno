"""R4: checkout não expõe nem altera o cadastro canônico sem comprovação."""

from django.contrib.auth.models import Group
from django.core import mail
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from accounts.models import Usuario
from customers.factories import ClienteFactory
from privacy.models import ConsentimentoLGPD
from privacy.services import exportar_dados_do_titular

from .helpers import fluxo_checkout


class CheckoutPrivacidadeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_groups", verbosity=0)
        cls.vitima = ClienteFactory(
            nome="Vítima Confidencial",
            documento="52998224725",
            email="vitima@example.com",
        )

    def test_visitante_com_documento_alheio_nao_expoe_nome_canonico(self):
        pedido = fluxo_checkout(
            self.client,
            quantidade=1,
            dados_extra={
                "nome": "Visitante do Checkout",
                "email": "visitante@example.com",
                "aceita_marketing": "on",
            },
        )

        self.assertEqual(pedido.nome_contato, "Visitante do Checkout")
        self.assertFalse(pedido.identidade_verificada)
        self.assertTrue(pedido.consentimento_compras)
        self.assertTrue(pedido.consentimento_marketing)
        self.assertEqual(
            ConsentimentoLGPD.objects.filter(cliente=self.vitima).count(), 0
        )

        pagina = self.client.get(
            reverse("sales:pedido_token", args=[pedido.token_acesso])
        )
        texto = pagina.content.decode()
        self.assertIn("Visitante do Checkout", texto)
        self.assertNotIn("Vítima Confidencial", texto)

        corpo = "\n".join(email.body for email in mail.outbox)
        self.assertIn("Visitante do Checkout", corpo)
        self.assertNotIn("Vítima Confidencial", corpo)

        exportado = exportar_dados_do_titular(self.vitima)
        self.assertEqual(exportado["pedidos"], [])

    def test_cliente_vinculado_ainda_nao_ve_pedido_nao_verificado(self):
        usuario = Usuario.objects.create_user(
            username="vitima", password="senha-forte-123"
        )
        self.vitima.usuario = usuario
        self.vitima.save(update_fields=["usuario"])
        pedido = fluxo_checkout(self.client, quantidade=1)

        self.client.force_login(usuario)
        resposta = self.client.get(reverse("sales:meus_pedidos"))

        self.assertNotContains(resposta, pedido.numero)
        self.assertEqual(list(resposta.context["pedidos"]), [])

    def test_cliente_autenticado_vinculado_tem_identidade_verificada(self):
        usuario = Usuario.objects.create_user(
            username="cliente-verificado",
            email="vitima@example.com",
            password="senha-forte-123",
        )
        self.vitima.usuario = usuario
        self.vitima.vinculo_verificado = True
        self.vitima.save(update_fields=["usuario", "vinculo_verificado"])
        self.client.force_login(usuario)

        pedido = fluxo_checkout(
            self.client,
            quantidade=1,
            dados_extra={"aceita_marketing": "on"},
        )

        self.assertTrue(pedido.identidade_verificada)
        self.assertTrue(
            ConsentimentoLGPD.objects.filter(
                cliente=self.vitima, finalidade="compras", aceito=True
            ).exists()
        )
        self.assertTrue(
            ConsentimentoLGPD.objects.filter(
                cliente=self.vitima, finalidade="marketing", aceito=True
            ).exists()
        )
        resposta = self.client.get(reverse("sales:meus_pedidos"))
        self.assertContains(resposta, pedido.numero)

    def test_vendedor_criando_pedido_nao_gera_consentimento_no_cliente(self):
        vendedor = Usuario.objects.create_user(
            username="vendedor-r4", password="senha-forte-123"
        )
        vendedor.groups.add(Group.objects.get(name="Vendedor"))
        self.client.force_login(vendedor)

        pedido = fluxo_checkout(
            self.client,
            quantidade=1,
            dados_extra={"aceita_marketing": "on"},
        )

        self.assertEqual(pedido.usuario_criador, vendedor)
        self.assertFalse(pedido.identidade_verificada)
        self.assertFalse(pedido.consentimento_marketing)
        self.assertEqual(
            ConsentimentoLGPD.objects.filter(cliente=self.vitima).count(), 0
        )
