import threading
import time
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import OperationalError, connections
from django.test import TestCase, TransactionTestCase

from analytics.models import Aviso
from catalog.factories import ProdutoFactory
from core.factories import UnidadeFactory
from stock.factories import EstoqueFactory
from stock.models import Estoque, MovimentoEstoque
from stock.services import (
    dar_baixa_definitiva,
    liberar_reserva,
    registrar_movimento,
    reservar,
    transferir_estoque,
)


class RegistrarMovimentoTests(TestCase):
    def setUp(self):
        self.produto = ProdutoFactory()
        self.feira = UnidadeFactory(nome="Feira de Santana")
        self.iacu = UnidadeFactory(nome="Iaçu")

    def test_entrada_aumenta_saldo(self):
        registrar_movimento(
            produto=self.produto, unidade=self.feira,
            tipo=MovimentoEstoque.Tipo.ENTRADA, quantidade=50,
        )
        estoque = EstoqueFactory(produto=self.produto, unidade=self.feira)
        # get_or_create do serviço já criou; recarrega valores atuais.
        estoque.refresh_from_db()
        self.assertEqual(estoque.quantidade, Decimal("50"))

    def test_saida_diminui_saldo(self):
        EstoqueFactory(
            produto=self.produto, unidade=self.feira, quantidade="100"
        )
        registrar_movimento(
            produto=self.produto, unidade=self.feira,
            tipo=MovimentoEstoque.Tipo.SAIDA, quantidade=30,
        )
        estoque = Estoque.objects.get(
            produto=self.produto, unidade=self.feira
        )
        self.assertEqual(estoque.quantidade, Decimal("70"))

    def test_saida_acima_do_saldo_e_bloqueada(self):
        EstoqueFactory(
            produto=self.produto, unidade=self.feira, quantidade="10"
        )
        with self.assertRaises(ValidationError):
            registrar_movimento(
                produto=self.produto, unidade=self.feira,
                tipo=MovimentoEstoque.Tipo.SAIDA, quantidade=11,
            )
        estoque = Estoque.objects.get(produto=self.produto, unidade=self.feira)
        self.assertEqual(estoque.quantidade, Decimal("10"))
        self.assertEqual(MovimentoEstoque.objects.count(), 0)

    def test_saida_nao_consome_quantidade_reservada(self):
        EstoqueFactory(
            produto=self.produto, unidade=self.feira,
            quantidade="10", quantidade_bloqueada="4",
        )
        with self.assertRaises(ValidationError):
            registrar_movimento(
                produto=self.produto, unidade=self.feira,
                tipo=MovimentoEstoque.Tipo.SAIDA, quantidade=7,
            )

    def test_ajuste_sem_motivo_e_rejeitado(self):
        with self.assertRaises(ValidationError):
            registrar_movimento(
                produto=self.produto, unidade=self.feira,
                tipo=MovimentoEstoque.Tipo.AJUSTE, quantidade=-5,
                motivo="",
            )

    def test_ajuste_negativo_com_motivo_funciona(self):
        EstoqueFactory(
            produto=self.produto, unidade=self.feira, quantidade="20"
        )
        movimento = registrar_movimento(
            produto=self.produto, unidade=self.feira,
            tipo=MovimentoEstoque.Tipo.AJUSTE, quantidade=-5,
            motivo="Quebra no manuseio",
        )
        estoque = Estoque.objects.get(
            produto=self.produto, unidade=self.feira
        )
        self.assertEqual(estoque.quantidade, Decimal("15"))
        self.assertEqual(movimento.quantidade, Decimal("5"))

    def test_transferencia_gera_dois_movimentos_vinculados(self):
        EstoqueFactory(
            produto=self.produto, unidade=self.feira, quantidade="50"
        )
        saida, entrada = transferir_estoque(
            produto=self.produto,
            unidade_origem=self.feira,
            unidade_destino=self.iacu,
            quantidade=12,
        )
        origem = Estoque.objects.get(produto=self.produto, unidade=self.feira)
        destino = Estoque.objects.get(produto=self.produto, unidade=self.iacu)
        self.assertEqual(origem.quantidade, Decimal("38"))
        self.assertEqual(destino.quantidade, Decimal("12"))
        self.assertEqual(saida.movimento_par, entrada)
        self.assertEqual(entrada.movimento_par, saida)
        self.assertEqual(saida.tipo, MovimentoEstoque.Tipo.SAIDA)
        self.assertEqual(entrada.tipo, MovimentoEstoque.Tipo.ENTRADA)

    def test_movimento_registra_usuario(self):
        from accounts.models import Usuario

        usuario = Usuario.objects.create_user(username="gestor2")
        movimento = registrar_movimento(
            produto=self.produto, unidade=self.feira,
            tipo=MovimentoEstoque.Tipo.ENTRADA, quantidade=1,
            usuario=usuario,
        )
        self.assertEqual(movimento.usuario, usuario)

    def test_estoque_minimo_gera_aviso_uma_vez(self):
        registrar_movimento(
            produto=self.produto, unidade=self.feira,
            tipo=MovimentoEstoque.Tipo.ENTRADA, quantidade=8,
            quantidade_minima=Decimal("10"),
        )
        avisos = Aviso.objects.filter(tipo=Aviso.Tipo.ESTOQUE_BAIXO)
        self.assertEqual(avisos.count(), 1)


class ImutabilidadeMovimentoTests(TestCase):
    def test_movimento_nao_pode_ser_alterado_nem_excluido(self):
        produto = ProdutoFactory()
        unidade = UnidadeFactory()
        movimento = registrar_movimento(
            produto=produto, unidade=unidade,
            tipo=MovimentoEstoque.Tipo.ENTRADA, quantidade=5,
        )
        with self.assertRaises(ValidationError):
            movimento.quantidade = 999
            movimento.save()
        with self.assertRaises(ValidationError):
            movimento.delete()


class ReservaTests(TestCase):
    def test_reserva_bloqueia_disponibilidade(self):
        produto = ProdutoFactory()
        unidade = UnidadeFactory()
        EstoqueFactory(
            produto=produto, unidade=unidade, quantidade="10"
        )
        reservar(produto=produto, unidade=unidade, quantidade=6)
        estoque = Estoque.objects.get(produto=produto, unidade=unidade)
        self.assertEqual(estoque.disponivel, Decimal("4"))

    def test_reserva_acima_do_saldo_e_rejeitada(self):
        produto = ProdutoFactory()
        unidade = UnidadeFactory()
        EstoqueFactory(
            produto=produto, unidade=unidade, quantidade="3"
        )
        with self.assertRaises(ValidationError):
            reservar(produto=produto, unidade=unidade, quantidade=4)

    def test_liberar_reserva_devolve_disponibilidade(self):
        produto = ProdutoFactory()
        unidade = UnidadeFactory()
        EstoqueFactory(
            produto=produto, unidade=unidade,
            quantidade="10", quantidade_bloqueada="6",
        )
        liberar_reserva(produto=produto, unidade=unidade, quantidade=6)
        estoque = Estoque.objects.get(produto=produto, unidade=unidade)
        self.assertEqual(estoque.disponivel, Decimal("10"))

    def test_baixa_definitiva_apos_aprovacao(self):
        produto = ProdutoFactory()
        unidade = UnidadeFactory()
        EstoqueFactory(
            produto=produto, unidade=unidade,
            quantidade="10", quantidade_bloqueada="4",
        )
        dar_baixa_definitiva(
            produto=produto, unidade=unidade, quantidade=4, pedido="#123"
        )
        estoque = Estoque.objects.get(produto=produto, unidade=unidade)
        self.assertEqual(estoque.quantidade, Decimal("6"))
        self.assertEqual(estoque.quantidade_bloqueada, Decimal("0"))


class ConcurrencyStockTests(TransactionTestCase):
    """Concorrência: saídas simultâneas não podem ultrapassar o saldo."""

    def test_saidas_concorrentes_respeitam_o_saldo(self):
        produto = ProdutoFactory()
        unidade = UnidadeFactory()
        EstoqueFactory(
            produto=produto, unidade=unidade, quantidade="10"
        )
        trava = threading.Lock()
        resultados = {"ok": 0, "falha": 0}
        erros = []

        def tentar_saida():
            for tentativa in range(5):
                try:
                    registrar_movimento(
                        produto=produto,
                        unidade=unidade,
                        tipo=MovimentoEstoque.Tipo.SAIDA,
                        quantidade=3,
                    )
                    return "ok"
                except ValidationError:
                    return "falha"
                except OperationalError:
                    # Contenção no SQLite em ambiente de teste: aguarda e tenta
                    # novamente (em produção, busy_timeout/row-lock cobre isso).
                    time.sleep(0.05 * (tentativa + 1))
            return "falha"

        def retirar():
            try:
                resultado = tentar_saida()
                with trava:
                    resultados[resultado] += 1
            except Exception as erro:  # pragma: no cover - diagnóstico
                with trava:
                    erros.append(erro)
            finally:
                connections.close_all()

        threads = [threading.Thread(target=retirar) for _ in range(6)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertFalse(erros, f"Erros inesperados: {erros}")
        estoque = Estoque.objects.get(produto=produto, unidade=unidade)
        self.assertGreaterEqual(estoque.quantidade, 0)
        self.assertLessEqual(estoque.quantidade, Decimal("10"))
        # Cada aprovação baixa exatamente 3 unidades; nada além disso.
        self.assertEqual(
            estoque.quantidade, Decimal(10 - resultados["ok"] * 3)
        )
