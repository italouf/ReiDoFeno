from django.test import TestCase
from django.urls import reverse

from catalog.factories import ProdutoFactory
from catalog.models import Produto
from core.factories import UnidadeFactory
from stock.factories import EstoqueFactory


class CarrinhoTests(TestCase):
    def setUp(self):
        self.produto = ProdutoFactory(nome="Feno Tifton 85", preco_online="10.00")
        self.feira = UnidadeFactory(nome="Feira de Santana")
        EstoqueFactory(
            produto=self.produto,
            unidade=self.feira,
            quantidade="20.00",
            quantidade_bloqueada="2.00",
        )

    def adicionar(self, quantidade=3, follow=False):
        return self.client.post(
            reverse("sales:adicionar"),
            {"produto_id": self.produto.pk, "quantidade": str(quantidade)},
            follow=follow,
        )

    def test_adicionar_item_ao_carrinho(self):
        resposta = self.adicionar(quantidade=3)
        self.assertRedirects(resposta, reverse("sales:carrinho"))
        carrinho_page = self.client.get(reverse("sales:carrinho"))
        self.assertContains(carrinho_page, "Feno Tifton 85")
        # Total calculado no servidor: 3 × R$ 10,00
        self.assertContains(carrinho_page, "30")

    def test_alterar_quantidade_recalcula_total_no_servidor(self):
        self.adicionar(quantidade=1)
        self.client.post(
            reverse("sales:alterar_item", args=[self.produto.pk]),
            {"quantidade": "5"},
        )
        carrinho_page = self.client.get(reverse("sales:carrinho"))
        self.assertContains(carrinho_page, "50")

    def test_remover_item_do_carrinho(self):
        self.adicionar(quantidade=2)
        self.client.post(reverse("sales:remover_item", args=[self.produto.pk]))
        carrinho_page = self.client.get(reverse("sales:carrinho"))
        self.assertContains(carrinho_page, "está vazio")

    def test_quantidade_acima_do_disponivel_e_rejeitada(self):
        # Disponível = 18 (20 - 2 reservadas)
        self.adicionar(quantidade=19)
        page = self.client.get(reverse("sales:carrinho"))
        self.assertContains(page, "está vazio")

        resposta = self.adicionar(quantidade=25, follow=True)
        texto = resposta.content.decode()
        self.assertIn("Quantidade indisponível", texto)

    def test_produto_inativo_nao_pode_ser_adicionado(self):
        inativo = ProdutoFactory(ativo=False)
        resposta = self.client.post(
            reverse("sales:adicionar"),
            {"produto_id": inativo.pk, "quantidade": "1"},
        )
        self.assertEqual(resposta.status_code, 404)

    def test_itens_inativos_sumiram_do_carrinho(self):
        self.adicionar(quantidade=2)
        Produto.objects.filter(pk=self.produto.pk).update(ativo=False)
        # Primeiro GET consome as mensagens pendentes da sessão.
        self.client.get(reverse("sales:carrinho"))
        page = self.client.get(reverse("sales:carrinho"))
        self.assertNotContains(page, "Feno Tifton 85")
