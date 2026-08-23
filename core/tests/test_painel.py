from datetime import date
from decimal import Decimal

from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from accounts.models import Usuario
from catalog.factories import ProdutoFactory
from core.factories import UnidadeFactory
from costs.factories import DespesaFactory
from stock.factories import EstoqueFactory
from stock.models import MovimentoEstoque


class PainelConteudoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_groups", verbosity=0)
        cls.gestor = Usuario.objects.create_user(
            username="gestor", password="senha-forte-123"
        )
        cls.gestor.groups.add(Group.objects.get(name="Gestor"))

    def test_painel_vazio_mostra_estados_vazios(self):
        self.client.force_login(self.gestor)
        resposta = self.client.get(reverse("core:painel"))
        self.assertEqual(resposta.status_code, 200)
        texto = resposta.content.decode()
        self.assertIn("Nenhum item abaixo do mínimo", texto)
        self.assertIn("Sem movimentações registradas ainda", texto)

    def test_painel_exibe_dados_reais(self):
        produto = ProdutoFactory(nome="Feno Tifton 85")
        unidade = UnidadeFactory(nome="Feira de Santana")
        EstoqueFactory(
            produto=produto,
            unidade=unidade,
            quantidade="5.00",
            quantidade_minima="10.00",
        )
        registrar_entrada(produto, unidade, 3)
        DespesaFactory(
            fornecedor="Transportadora Vale",
            data=date(2026, 8, 20),
            recorrencia="unica",
            valor=Decimal("90.00"),
        )

        self.client.force_login(self.gestor)
        resposta = self.client.get(reverse("core:painel"))

        texto = resposta.content.decode()
        self.assertContains(resposta, "Feno Tifton 85")
        self.assertIn("Estoque baixo", texto)
        self.assertIn("Entrada", texto)
        self.assertIn("Transportadora Vale", texto)


def registrar_entrada(produto, unidade, quantidade):
    from stock.services import registrar_movimento

    return registrar_movimento(
        produto=produto,
        unidade=unidade,
        tipo=MovimentoEstoque.Tipo.ENTRADA,
        quantidade=quantidade,
    )
