from decimal import Decimal

from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from accounts.models import Usuario
from catalog.factories import ProdutoFactory
from core.auditoria import _serializar, registrar_auditoria
from core.models import LogAuditoria
from stock.models import MovimentoEstoque
from stock.services import registrar_movimento


class LogAuditoriaModelTests(TestCase):
    def test_registro_e_imutavel(self):
        produto = ProdutoFactory()
        registro = registrar_auditoria(
            acao="produto.criado", instancia=produto
        )
        with self.assertRaises(ValidationError):
            registro.acao = "hack"
            registro.save()
        with self.assertRaises(ValidationError):
            registro.delete()


class SerializacaoTests(TestCase):
    def test_serializa_apenas_campos_primitivos(self):
        produto = ProdutoFactory(nome="Tifton", custo="80.00")
        dados = _serializar(produto)
        self.assertEqual(dados["nome"], "Tifton")
        self.assertIn("custo", dados)
        # FK vira id primitivo; campos não primitivos são descartados.
        self.assertIsInstance(dados["nome"], str)


class AuditoriaIntegracaoTests(TestCase):
    def test_ajuste_manual_de_estoque_e_auditado(self):
        from core.factories import UnidadeFactory
        from stock.factories import EstoqueFactory

        produto = ProdutoFactory()
        unidade = UnidadeFactory()
        EstoqueFactory(
            produto=produto, unidade=unidade, quantidade="10"
        )
        registrar_movimento(
            produto=produto,
            unidade=unidade,
            tipo=MovimentoEstoque.Tipo.AJUSTE,
            quantidade=-Decimal("3"),
            motivo="Inventário",
        )
        registro = LogAuditoria.objects.filter(
            acao="estoque.ajuste_manual"
        ).latest("id")
        self.assertIn("motivo", (registro.depois or {}))


class AuditoriaCrudUnidadeTests(TestCase):
    def test_criacao_de_unidade_e_auditada(self):
        call_command("seed_groups", verbosity=0)
        admin = Usuario.objects.create_user(
            username="admin-auditoria", password="senha-forte-123"
        )
        admin.groups.add(Group.objects.get(name="Administrador"))
        self.client.force_login(admin)

        resposta = self.client.post(
            reverse("core:unidade_novo"),
            {
                "nome": "Unidade Auditada",
                "cidade": "Feira de Santana",
                "tipo": "loja",
                "ativa": "on",
            },
        )

        self.assertEqual(resposta.status_code, 302)
        self.assertTrue(
            LogAuditoria.objects.filter(
                acao="unidade.criado",
            ).exists()
        )
