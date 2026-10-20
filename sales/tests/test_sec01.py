"""SEC-01: transições financeiras não podem ser forçadas pela área interna."""

from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from accounts.models import Usuario
from core.models import LogAuditoria
from sales.factories import PedidoFactory
from sales.models import Pedido


class StatusFinanceiroBloqueadoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_groups", verbosity=0)
        cls.senha = "senha-forte-123"
        cls.vendedor = Usuario.objects.create_user(
            username="vendedor-sec01", password=cls.senha
        )
        cls.vendedor.groups.add(Group.objects.get(name="Vendedor"))
        cls.gestor = Usuario.objects.create_user(
            username="gestor-sec01", password=cls.senha
        )
        cls.gestor.groups.add(Group.objects.get(name="Gestor"))

    def _pedido_aguardando(self, usuario=None):
        return PedidoFactory(
            usuario_criador=usuario or self.vendedor,
            status=Pedido.Status.AGUARDANDO_PAGAMENTO,
        )

    def test_vendedor_nao_pode_forcar_status_pago(self):
        pedido = self._pedido_aguardando()
        self.client.force_login(self.vendedor)

        resposta = self.client.post(
            reverse("sales:pedido_atualizar_status", args=[pedido.pk]),
            {"status": Pedido.Status.PAGO},
        )

        self.assertEqual(resposta.status_code, 403)
        pedido.refresh_from_db()
        self.assertEqual(pedido.status, Pedido.Status.AGUARDANDO_PAGAMENTO)

    def test_gestor_tambem_nao_pode_forcar_status_pago(self):
        pedido = self._pedido_aguardando()
        self.client.force_login(self.gestor)

        resposta = self.client.post(
            reverse("sales:pedido_atualizar_status", args=[pedido.pk]),
            {"status": Pedido.Status.PAGO},
        )

        self.assertEqual(resposta.status_code, 403)
        pedido.refresh_from_db()
        self.assertEqual(pedido.status, Pedido.Status.AGUARDANDO_PAGAMENTO)

    def test_todos_os_status_financeiros_sao_bloqueados(self):
        for status in (
            Pedido.Status.PAGO,
            Pedido.Status.PAGAMENTO_PENDENTE,
            Pedido.Status.FALHOU,
            Pedido.StatusFinanceiro.PENDENTE,
            Pedido.StatusFinanceiro.ESTORNADO,
        ):
            with self.subTest(status=status):
                pedido = self._pedido_aguardando()
                self.client.force_login(self.vendedor)

                resposta = self.client.post(
                    reverse("sales:pedido_atualizar_status", args=[pedido.pk]),
                    {"status": status},
                )

                self.assertEqual(resposta.status_code, 403)
                pedido.refresh_from_db()
                self.assertEqual(pedido.status, Pedido.Status.AGUARDANDO_PAGAMENTO)

    def test_tentativa_bloqueada_gera_auditoria(self):
        pedido = self._pedido_aguardando()
        self.client.force_login(self.vendedor)

        self.client.post(
            reverse("sales:pedido_atualizar_status", args=[pedido.pk]),
            {"status": Pedido.Status.PAGO},
        )

        log = LogAuditoria.objects.filter(
            acao="tentativa_bloqueada_transicao_financeira",
            objeto_id=str(pedido.pk),
        ).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.usuario, self.vendedor)
        self.assertEqual(log.depois["status_solicitado"], Pedido.Status.PAGO)

    def test_transicao_operacional_continua_funcionando(self):
        pedido = PedidoFactory(
            usuario_criador=self.vendedor,
            status=Pedido.Status.PAGO,
        )
        self.client.force_login(self.vendedor)

        resposta = self.client.post(
            reverse("sales:pedido_atualizar_status", args=[pedido.pk]),
            {"status": Pedido.Status.EM_SEPARACAO},
        )

        self.assertEqual(resposta.status_code, 302)
        pedido.refresh_from_db()
        self.assertEqual(pedido.status, Pedido.Status.EM_SEPARACAO)

    def test_cancelamento_operacional_continua_funcionando(self):
        pedido = self._pedido_aguardando()
        self.client.force_login(self.vendedor)

        resposta = self.client.post(
            reverse("sales:pedido_atualizar_status", args=[pedido.pk]),
            {"status": Pedido.Status.CANCELADO},
        )

        self.assertEqual(resposta.status_code, 302)
        pedido.refresh_from_db()
        self.assertEqual(pedido.status, Pedido.Status.CANCELADO)
