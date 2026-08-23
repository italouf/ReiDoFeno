from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

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
