from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from accounts.models import Usuario
from core.models import LogAuditoria
from fiscal.models import NotaFiscal
from sales.factories import PedidoFactory
from sales.models import Pedido


class NotaManualTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_groups", verbosity=0)
        cls.senha = "senha-forte-123"
        cls.usuarios = {}
        for perfil in ("administrador", "gestor", "vendedor"):
            usuario = Usuario.objects.create_user(
                username=perfil, password=cls.senha
            )
            usuario.groups.add(Group.objects.get(name=perfil.capitalize()))
            cls.usuarios[perfil] = usuario

    def test_gestor_registra_nota_manual_auditable(self):
        pedido = PedidoFactory(status=Pedido.Status.PAGO)
        self.client.force_login(self.usuarios["gestor"])

        resposta = self.client.post(
            reverse("fiscal:nota_manual", args=[pedido.pk]),
            {
                "numero": "123456",
                "chave_acesso": "29260812345678901234567890123456789012345678",
                "link_documento": "https://exemplo.com/danfe.pdf",
            },
        )
        self.assertEqual(resposta.status_code, 302)

        nota = NotaFiscal.objects.get(pedido=pedido)
        self.assertEqual(nota.origem, NotaFiscal.Origem.MANUAL)
        self.assertEqual(nota.status, NotaFiscal.Status.AUTORIZADA)
        registro = LogAuditoria.objects.get(acao="fiscal.nota_manual_registrada")
        self.assertEqual(registro.depois["numero"], "123456")

    def test_vendedor_negado(self):
        pedido = PedidoFactory(status=Pedido.Status.PAGO)
        self.client.force_login(self.usuarios["vendedor"])
        resposta = self.client.get(reverse("fiscal:nota_manual", args=[pedido.pk]))
        self.assertEqual(resposta.status_code, 403)
