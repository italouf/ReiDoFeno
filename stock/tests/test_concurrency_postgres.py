"""H02: ordem global de locks evita deadlock em transferências inversas."""

import threading

import pytest
from django.db import close_old_connections
from django.test import TransactionTestCase

from catalog.factories import ProdutoFactory
from core.factories import UnidadeFactory
from stock.factories import EstoqueFactory
from stock.models import Estoque
from stock.services import transferir_estoque

pytestmark = pytest.mark.postgres


class TransferenciaDeadlockTests(TransactionTestCase):
    def test_transferencias_inversas_nao_geram_deadlock(self):
        produto = ProdutoFactory()
        unidade_a = UnidadeFactory(nome="Unidade A")
        unidade_b = UnidadeFactory(nome="Unidade B")
        EstoqueFactory(
            produto=produto, unidade=unidade_a, quantidade="100.00"
        )
        EstoqueFactory(
            produto=produto, unidade=unidade_b, quantidade="100.00"
        )
        barreira = threading.Barrier(2)
        erros = []

        def transferir(origem, destino):
            close_old_connections()
            try:
                barreira.wait(timeout=10)
                transferir_estoque(
                    produto=produto,
                    unidade_origem=origem,
                    unidade_destino=destino,
                    quantidade=10,
                )
            except Exception as erro:  # captura para diagnóstico
                erros.append(erro)
            finally:
                close_old_connections()

        threads = [
            threading.Thread(
                target=transferir, args=(unidade_a, unidade_b)
            ),
            threading.Thread(
                target=transferir, args=(unidade_b, unidade_a)
            ),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=20)

        self.assertFalse(erros, erros)
        self.assertEqual(
            Estoque.objects.get(
                produto=produto, unidade=unidade_a
            ).quantidade,
            100,
        )
        self.assertEqual(
            Estoque.objects.get(
                produto=produto, unidade=unidade_b
            ).quantidade,
            100,
        )
