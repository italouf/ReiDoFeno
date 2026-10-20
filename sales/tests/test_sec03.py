"""SEC-03: transições e pagamentos auditados na mesma transação."""

from unittest import mock

from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from accounts.models import Usuario
from core.models import LogAuditoria
from sales.factories import PedidoFactory
from sales.models import Pagamento, Pedido
from sales.services import marcar_pagamento_aprovado
from stock.models import Estoque, MovimentoEstoque

from .helpers import DADOS_BASE, fluxo_checkout


class AuditoriaStatusTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_groups", verbosity=0)
        cls.senha = "senha-forte-123"
        cls.vendedor = Usuario.objects.create_user(
            username="vendedor-sec03", password=cls.senha
        )
        cls.vendedor.groups.add(Group.objects.get(name="Vendedor"))

    def test_transicao_operacional_e_auditada(self):
        pedido = PedidoFactory(
            usuario_criador=self.vendedor,
            status=Pedido.Status.PAGO,
        )
        self.client.force_login(self.vendedor)

        self.client.post(
            reverse("sales:pedido_atualizar_status", args=[pedido.pk]),
            {"status": Pedido.Status.EM_SEPARACAO},
        )

        log = LogAuditoria.objects.filter(
            acao="pedido.status_alterado",
            objeto_id=str(pedido.pk),
        ).latest("id")
        self.assertEqual(log.usuario, self.vendedor)
        self.assertEqual(log.antes["status"], Pedido.Status.PAGO)
        self.assertEqual(log.depois["status"], Pedido.Status.EM_SEPARACAO)

    def test_falha_na_auditoria_reverte_transicao_de_status(self):
        pedido = PedidoFactory(
            usuario_criador=self.vendedor,
            status=Pedido.Status.PAGO,
        )
        self.client.force_login(self.vendedor)

        with mock.patch(
            "core.auditoria.LogAuditoria.objects.create",
            side_effect=RuntimeError("auditoria indisponível"),
        ):
            with self.assertRaises(RuntimeError):
                self.client.post(
                    reverse(
                        "sales:pedido_atualizar_status", args=[pedido.pk]
                    ),
                    {"status": Pedido.Status.EM_SEPARACAO},
                )

        pedido.refresh_from_db()
        self.assertEqual(pedido.status, Pedido.Status.PAGO)


class AuditoriaCriacaoPedidoTests(TestCase):
    def test_falha_na_auditoria_reverte_pedido_itens_e_reserva(self):
        from catalog.factories import ProdutoFactory
        from core.factories import UnidadeFactory
        from stock.factories import EstoqueFactory

        produto = ProdutoFactory(preco_online="10.00")
        unidade = UnidadeFactory()
        EstoqueFactory(
            produto=produto, unidade=unidade, quantidade="10.00"
        )
        self.client.post(
            reverse("sales:adicionar"),
            {"produto_id": produto.pk, "quantidade": "2"},
        )
        dados = dict(DADOS_BASE)
        dados["unidade"] = unidade.pk

        with mock.patch(
            "core.auditoria.LogAuditoria.objects.create",
            side_effect=RuntimeError("auditoria indisponível"),
        ):
            with self.assertRaises(RuntimeError):
                self.client.post(reverse("sales:checkout"), dados)

        self.assertFalse(Pedido.objects.exists())
        self.assertFalse(
            Estoque.objects.filter(
                produto=produto, unidade=unidade, quantidade_bloqueada__gt=0
            ).exists()
        )


class AuditoriaPagamentoTests(TestCase):
    def test_pagamento_aprovado_e_auditado(self):
        pedido = fluxo_checkout(self.client, quantidade=2)

        marcar_pagamento_aprovado(pedido, id_externo="pay-sec03")

        log = LogAuditoria.objects.filter(
            acao="pedido.pagamento_aprovado",
            objeto_id=str(pedido.pk),
        ).latest("id")
        self.assertEqual(log.depois["id_externo"], "pay-sec03")

    def test_falha_na_auditoria_reverte_pagamento_e_estoque(self):
        pedido = fluxo_checkout(self.client, quantidade=2)
        pagamento = Pagamento.objects.create(
            pedido=pedido, valor=pedido.total
        )
        item = pedido.itens.first()
        estoque = Estoque.objects.get(
            produto=item.produto, unidade=pedido.unidade
        )

        from core import auditoria as modulo_auditoria

        registrar_real = modulo_auditoria.registrar_auditoria

        def falhar_apenas_na_aprovacao(*args, **kwargs):
            if kwargs.get("acao") == "pedido.pagamento_aprovado":
                raise RuntimeError("auditoria indisponível")
            return registrar_real(*args, **kwargs)

        with mock.patch(
            "core.auditoria.registrar_auditoria",
            side_effect=falhar_apenas_na_aprovacao,
        ):
            with self.assertRaises(RuntimeError):
                marcar_pagamento_aprovado(pedido, id_externo="pay-sec03")

        pedido.refresh_from_db()
        pagamento.refresh_from_db()
        estoque.refresh_from_db()
        self.assertEqual(
            pedido.status_financeiro, Pedido.StatusFinanceiro.PENDENTE
        )
        self.assertEqual(pedido.status, Pedido.Status.AGUARDANDO_PAGAMENTO)
        self.assertEqual(pagamento.status, Pagamento.Status.PENDENTE)
        self.assertEqual(estoque.quantidade, 100)
        self.assertEqual(estoque.quantidade_bloqueada, 2)
        self.assertFalse(
            MovimentoEstoque.objects.filter(
                produto=item.produto, unidade=pedido.unidade
            ).exists()
        )
        self.assertFalse(
            LogAuditoria.objects.filter(
                acao="pedido.pagamento_aprovado",
                objeto_id=str(pedido.pk),
            ).exists()
        )
        self.assertFalse(
            LogAuditoria.objects.filter(
                acao="pedido.status_financeiro_alterado",
                objeto_id=str(pedido.pk),
            ).exists()
        )
