"""Workflow fiscal: listagem, autorização e cancelamento."""

from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from accounts.models import Usuario
from core.models import LogAuditoria
from fiscal.models import NotaFiscal
from sales.factories import PedidoFactory
from sales.models import Pedido


def chave(n: int) -> str:
    return str(n).zfill(44)


class WorkflowFiscalTests(TestCase):
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

    def criar_nota(self, *, status, numero="123", chave_acesso=None):
        pedido = PedidoFactory(status=Pedido.Status.PAGO)
        return NotaFiscal.objects.create(
            pedido=pedido,
            tipo=NotaFiscal.Tipo.SAIDA,
            status=status,
            numero=numero,
            chave_acesso=chave_acesso or chave(pedido.pk),
        )

    def test_listagem_e_filtro_por_status(self):
        pendente = self.criar_nota(status=NotaFiscal.Status.PENDENTE, numero="")
        anexada = self.criar_nota(status=NotaFiscal.Status.ANEXADA, numero="2")
        autorizada = self.criar_nota(
            status=NotaFiscal.Status.AUTORIZADA, numero="3"
        )
        self.client.force_login(self.emissor)

        resposta = self.client.get(reverse("fiscal:nota_lista"))
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(
            set(resposta.context["notas"]),
            {pendente, anexada, autorizada},
        )

        resposta = self.client.get(
            reverse("fiscal:nota_lista") + "?status=anexada"
        )
        self.assertEqual(list(resposta.context["notas"]), [anexada])

    def test_filtro_invalido_retorna_400(self):
        self.client.force_login(self.emissor)

        resposta = self.client.get(
            reverse("fiscal:nota_lista") + "?status=invalido"
        )

        self.assertEqual(resposta.status_code, 400)

    def test_confirmar_nota_anexada(self):
        nota = self.criar_nota(status=NotaFiscal.Status.ANEXADA)
        self.client.force_login(self.emissor)

        resposta = self.client.post(
            reverse("fiscal:nota_autorizar", args=[nota.pk])
        )

        self.assertEqual(resposta.status_code, 302)
        nota.refresh_from_db()
        self.assertEqual(nota.status, NotaFiscal.Status.AUTORIZADA)
        log = LogAuditoria.objects.filter(
            acao="fiscal.nota_autorizada_manual",
            objeto_id=str(nota.pk),
        ).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.usuario, self.emissor)
        self.assertEqual(log.antes["status"], NotaFiscal.Status.ANEXADA)

    def test_confirmar_sem_numero_ou_chave_retorna_400(self):
        nota = self.criar_nota(
            status=NotaFiscal.Status.ANEXADA, numero="", chave_acesso=""
        )
        self.client.force_login(self.emissor)

        resposta = self.client.post(
            reverse("fiscal:nota_autorizar", args=[nota.pk])
        )

        self.assertEqual(resposta.status_code, 400)
        nota.refresh_from_db()
        self.assertEqual(nota.status, NotaFiscal.Status.ANEXADA)

    def test_confirmar_nota_cancelada_retorna_400(self):
        nota = self.criar_nota(status=NotaFiscal.Status.CANCELADA)
        self.client.force_login(self.emissor)

        resposta = self.client.post(
            reverse("fiscal:nota_autorizar", args=[nota.pk])
        )

        self.assertEqual(resposta.status_code, 400)

    def test_confirmar_nota_ja_autorizada_e_idempotente(self):
        nota = self.criar_nota(status=NotaFiscal.Status.AUTORIZADA)
        self.client.force_login(self.emissor)

        resposta = self.client.post(
            reverse("fiscal:nota_autorizar", args=[nota.pk])
        )

        self.assertEqual(resposta.status_code, 302)
        self.assertFalse(
            LogAuditoria.objects.filter(
                acao="fiscal.nota_autorizada_manual",
                objeto_id=str(nota.pk),
            ).exists()
        )

    def test_cancelar_nota_com_justificativa(self):
        nota = self.criar_nota(status=NotaFiscal.Status.AUTORIZADA)
        self.client.force_login(self.emissor)

        resposta = self.client.post(
            reverse("fiscal:nota_cancelar", args=[nota.pk]),
            {"justificativa": "Erro de emissão"},
        )

        self.assertEqual(resposta.status_code, 302)
        nota.refresh_from_db()
        self.assertEqual(nota.status, NotaFiscal.Status.CANCELADA)
        log = LogAuditoria.objects.filter(
            acao="fiscal.nota_cancelada",
            objeto_id=str(nota.pk),
        ).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.depois["motivo"], "Erro de emissão")

    def test_cancelar_sem_justificativa_retorna_400(self):
        nota = self.criar_nota(status=NotaFiscal.Status.AUTORIZADA)
        self.client.force_login(self.emissor)

        resposta = self.client.post(
            reverse("fiscal:nota_cancelar", args=[nota.pk]),
            {"justificativa": "   "},
        )

        self.assertEqual(resposta.status_code, 400)
        nota.refresh_from_db()
        self.assertEqual(nota.status, NotaFiscal.Status.AUTORIZADA)

    def test_vendedor_nao_acessa_workflow(self):
        nota = self.criar_nota(status=NotaFiscal.Status.ANEXADA)
        self.client.force_login(self.vendedor)

        self.assertEqual(
            self.client.get(reverse("fiscal:nota_lista")).status_code, 403
        )
        self.assertEqual(
            self.client.post(
                reverse("fiscal:nota_autorizar", args=[nota.pk])
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                reverse("fiscal:nota_cancelar", args=[nota.pk]),
                {"justificativa": "tentativa"},
            ).status_code,
            403,
        )
