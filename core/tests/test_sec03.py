"""SEC-03: auditoria atômica e captura confiável de IP."""

from unittest import mock

from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from accounts.models import Usuario
from catalog.factories import ProdutoFactory
from core.models import LogAuditoria
from stock.factories import EstoqueFactory
from stock.models import Estoque, MovimentoEstoque
from stock.services import registrar_movimento


class AuditoriaAtomicaCrudTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_groups", verbosity=0)
        cls.senha = "senha-forte-123"
        cls.admin = Usuario.objects.create_user(
            username="admin-sec03", password=cls.senha
        )
        cls.admin.groups.add(Group.objects.get(name="Administrador"))

    def _dados_produto(self, produto, nome="Novo Nome"):
        return {
            "nome": nome,
            "categoria": produto.categoria.pk,
            "ncm": "",
            "unidade_medida": produto.unidade_medida,
            "custo": produto.custo,
            "preco_balcao": produto.preco_balcao,
            "preco_online": produto.preco_online,
            "ativo": "on",
        }

    def test_falha_na_auditoria_reverte_alteracao_do_produto(self):
        produto = ProdutoFactory(nome="Antigo")
        self.client.force_login(self.admin)

        with mock.patch(
            "core.auditoria.LogAuditoria.objects.create",
            side_effect=RuntimeError("auditoria indisponível"),
        ):
            with self.assertRaises(RuntimeError):
                self.client.post(
                    reverse("catalog:produto_editar", args=[produto.pk]),
                    self._dados_produto(produto),
                )

        produto.refresh_from_db()
        self.assertEqual(produto.nome, "Antigo")
        self.assertFalse(
            LogAuditoria.objects.filter(
                acao="produto.alterado", objeto_id=str(produto.pk)
            ).exists()
        )

    def test_ip_vem_do_remote_addr_e_ignora_forwarded_for(self):
        produto = ProdutoFactory(nome="Antigo")
        self.client.force_login(self.admin)

        self.client.post(
            reverse("catalog:produto_editar", args=[produto.pk]),
            self._dados_produto(produto),
            REMOTE_ADDR="192.168.1.100",
            HTTP_X_FORWARDED_FOR="10.0.0.1, 10.0.0.2",
        )

        log = LogAuditoria.objects.filter(
            acao="produto.alterado", objeto_id=str(produto.pk)
        ).latest("id")
        self.assertEqual(str(log.ip), "192.168.1.100")
        self.assertEqual(str(log.usuario), str(self.admin))


class AuditoriaAtomicaEstoqueTests(TestCase):
    def test_falha_na_auditoria_reverte_movimento_de_estoque(self):
        from core.factories import UnidadeFactory

        produto = ProdutoFactory()
        unidade = UnidadeFactory()
        EstoqueFactory(produto=produto, unidade=unidade, quantidade="10")

        with mock.patch(
            "core.auditoria.LogAuditoria.objects.create",
            side_effect=RuntimeError("auditoria indisponível"),
        ):
            with self.assertRaises(RuntimeError):
                registrar_movimento(
                    produto=produto,
                    unidade=unidade,
                    tipo=MovimentoEstoque.Tipo.ENTRADA,
                    quantidade=5,
                )

        estoque = Estoque.objects.get(produto=produto, unidade=unidade)
        self.assertEqual(estoque.quantidade, 10)
        self.assertFalse(
            MovimentoEstoque.objects.filter(
                produto=produto, unidade=unidade
            ).exists()
        )
