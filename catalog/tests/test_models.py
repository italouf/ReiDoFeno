from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase

from catalog.factories import ProdutoFactory
from catalog.models import Categoria, Produto


class ProdutoModelTest(TestCase):
    def test_cria_produto_com_dados_validos(self):
        produto = ProdutoFactory(nome="Feno Tifton 85", unidade_medida="kg")
        self.assertTrue(Produto.objects.filter(pk=produto.pk).exists())
        self.assertIn("Feno Tifton 85", str(produto))

    def test_rejeita_produto_sem_nome(self):
        produto = ProdutoFactory.build(nome="")
        with self.assertRaises(ValidationError):
            produto.full_clean()

    def test_rejeita_produto_sem_unidade_de_medida(self):
        produto = ProdutoFactory.build(unidade_medida="")
        with self.assertRaises(ValidationError):
            produto.full_clean()

    def test_rejeita_precos_negativos(self):
        produto = ProdutoFactory.build(preco_online=Decimal("-1.00"))
        with self.assertRaises(ValidationError):
            produto.full_clean()

    def test_categoria_unica_por_nome(self):
        Categoria.objects.create(nome="Fenos")
        with self.assertRaises(IntegrityError):
            Categoria.objects.create(nome="Fenos")
