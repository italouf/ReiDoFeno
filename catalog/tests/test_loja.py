from django.test import TestCase
from django.urls import reverse

from catalog.factories import CategoriaFactory, ProdutoFactory


class VitrinePublicaTests(TestCase):
    def test_produto_ativo_aparece_na_vitrine_sem_login(self):
        ProdutoFactory(nome="Feno Tifton 85")
        resposta = self.client.get(reverse("loja:catalogo"))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Feno Tifton 85")
        self.assertContains(resposta, "110,00")

    def test_produto_inativo_nao_aparece(self):
        ProdutoFactory(nome="Produto Oculto", ativo=False)
        resposta = self.client.get(reverse("loja:catalogo"))
        self.assertEqual(resposta.status_code, 200)
        self.assertNotContains(resposta, "Produto Oculto")

    def test_pagina_do_produto_inativo_retorna_404(self):
        inativo = ProdutoFactory(ativo=False)
        resposta = self.client.get(reverse("loja:produto", args=[inativo.pk]))
        self.assertEqual(resposta.status_code, 404)

    def test_detalhe_publico_exibe_preco_online(self):
        produto = ProdutoFactory(nome="Feno Costela", preco_online="89.90")
        resposta = self.client.get(reverse("loja:produto", args=[produto.pk]))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "89,90")

    def test_filtro_por_categoria(self):
        categoria_a = CategoriaFactory(nome="Fenos")
        categoria_b = CategoriaFactory(nome="Rações")
        ProdutoFactory(categoria=categoria_a, nome="Tifton A")
        ProdutoFactory(categoria=categoria_b, nome="Ração B")

        resposta = self.client.get(
            reverse("loja:catalogo"), {"categoria": categoria_b.pk}
        )
        self.assertContains(resposta, "Ração B")
        self.assertNotContains(resposta, "Tifton A")

    def test_vitrine_vazia_mostra_estado_vazio(self):
        resposta = self.client.get(reverse("loja:catalogo"))
        self.assertContains(resposta, "Nenhum produto disponível")
