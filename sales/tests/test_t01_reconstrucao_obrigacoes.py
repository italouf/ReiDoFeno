"""T01: reconstrução de obrigações por evidência, sem dupla baixa."""

from decimal import Decimal
from io import StringIO

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase

from catalog.factories import ProdutoFactory
from core.factories import UnidadeFactory
from sales.factories import ItemPedidoFactory, PedidoFactory
from sales.models import ObrigacaoEstoquePedido, Pedido
from sales.obrigacoes import reconstruir_obrigacao_evidencia
from stock.factories import EstoqueFactory
from stock.models import MovimentoEstoque
from stock.services import registrar_movimento


class ReconstrucaoObrigacaoTests(TestCase):
    def setUp(self):
        self.produto = ProdutoFactory()
        self.unidade = UnidadeFactory()
        EstoqueFactory(
            produto=self.produto, unidade=self.unidade, quantidade="100.00"
        )
        self.pedido = PedidoFactory(
            unidade=self.unidade,
            status=Pedido.Status.AGUARDANDO_PAGAMENTO,
            status_financeiro=Pedido.StatusFinanceiro.PENDENTE,
        )
        self.item = ItemPedidoFactory(
            pedido=self.pedido,
            produto=self.produto,
            quantidade=Decimal("3.00"),
        )
        self.obrigacao = ObrigacaoEstoquePedido.objects.create(
            pedido=self.pedido,
            produto=self.produto,
            unidade=self.unidade,
            quantidade_devida=Decimal("3.00"),
            quantidade_baixada=Decimal("0.00"),
            status=ObrigacaoEstoquePedido.Status.PENDENTE,
        )

    def _movimento(self, delta="-3.00", motivo=None, tipo=None, **kwargs):
        return registrar_movimento(
            produto=self.produto,
            unidade=self.unidade,
            tipo=tipo or MovimentoEstoque.Tipo.BAIXA_DEFINITIVA,
            delta=Decimal(delta),
            motivo=motivo or f"Baixa definitiva por pedido {self.pedido.numero}",
            **kwargs,
        )

    def _reconstruir(self):
        dados = reconstruir_obrigacao_evidencia(
            self.obrigacao,
            Pedido=Pedido,
            Movimento=MovimentoEstoque,
        )
        for campo, valor in dados.items():
            setattr(self.obrigacao, campo, valor)
        self.obrigacao.save()
        self.obrigacao.refresh_from_db()
        return dados

    def test_baixa_legitima_por_texto_nao_duplica(self):
        movimento = self._movimento()
        self._reconstruir()
        self.assertEqual(
            self.obrigacao.status, ObrigacaoEstoquePedido.Status.RESOLVIDA
        )
        self.assertEqual(self.obrigacao.quantidade_baixada, Decimal("3.00"))
        self.assertEqual(self.obrigacao.evidencia_baixada, Decimal("3.00"))
        self.assertEqual(
            [item["movimento_id"] for item in self.obrigacao.evidencia_detalhe["movimentos"]],
            [movimento.pk],
        )

    def test_sem_movimento_nao_presume_baixa(self):
        self.obrigacao.status = ObrigacaoEstoquePedido.Status.RESOLVIDA
        self.obrigacao.quantidade_baixada = Decimal("3.00")
        self.obrigacao.save()
        self._reconstruir()
        self.assertEqual(
            self.obrigacao.status, ObrigacaoEstoquePedido.Status.PENDENTE
        )
        self.assertEqual(self.obrigacao.quantidade_baixada, Decimal("0.00"))
        self.assertIn("não comprovada", self.obrigacao.motivo_pendencia)

    def test_baixa_parcial_fica_pendente_com_evidencia(self):
        self._movimento(delta="-2.00")
        self._reconstruir()
        self.assertEqual(
            self.obrigacao.status, ObrigacaoEstoquePedido.Status.PENDENTE
        )
        self.assertEqual(self.obrigacao.quantidade_baixada, Decimal("2.00"))
        self.assertEqual(self.obrigacao.evidencia_baixada, Decimal("2.00"))

    def test_evidencia_excedente_fica_pendente_para_revisao(self):
        self._movimento(delta="-4.00")
        self._reconstruir()
        self.assertEqual(
            self.obrigacao.status, ObrigacaoEstoquePedido.Status.PENDENTE
        )
        self.assertEqual(self.obrigacao.quantidade_baixada, Decimal("3.00"))
        self.assertEqual(self.obrigacao.evidencia_baixada, Decimal("4.00"))
        self.assertIn("excede", self.obrigacao.motivo_pendencia)

    def test_motivo_com_dois_pedidos_e_ambiguo(self):
        self._movimento(
            motivo=(
                f"Baixa manual pedido {self.pedido.numero} "
                "e pedido PF999999"
            )
        )
        self._reconstruir()
        self.assertEqual(self.obrigacao.quantidade_baixada, Decimal("0.00"))
        self.assertTrue(self.obrigacao.evidencia_detalhe["ambiguos"])

    def test_evidencia_por_fk_tem_prioridade(self):
        movimento = self._movimento(
            motivo="baixa sem número de pedido", obrigacao=self.obrigacao
        )
        self._reconstruir()
        self.assertEqual(self.obrigacao.quantidade_baixada, Decimal("3.00"))
        self.assertEqual(
            self.obrigacao.evidencia_detalhe["movimentos"][0]["movimento_id"],
            movimento.pk,
        )
        self.assertEqual(
            self.obrigacao.evidencia_detalhe["movimentos"][0]["origem"], "fk"
        )

    def test_reconstrucao_e_idempotente(self):
        self._movimento(delta="-2.00")
        self._reconstruir()
        primeiro = (
            self.obrigacao.quantidade_baixada,
            self.obrigacao.evidencia_baixada,
            self.obrigacao.status,
        )
        self._reconstruir()
        self.assertEqual(
            primeiro,
            (
                self.obrigacao.quantidade_baixada,
                self.obrigacao.evidencia_baixada,
                self.obrigacao.status,
            ),
        )

    def test_movimento_tipo_saida_legado_e_aceito(self):
        self._movimento(tipo=MovimentoEstoque.Tipo.SAIDA)
        self._reconstruir()
        self.assertEqual(self.obrigacao.quantidade_baixada, Decimal("3.00"))

    def test_pedido_cancelado_nao_bloqueia_por_reconstrucao(self):
        self.pedido.status = Pedido.Status.CANCELADO
        self.pedido.status_financeiro = Pedido.StatusFinanceiro.CANCELADO
        self.pedido.save(update_fields=["status", "status_financeiro"])
        self._reconstruir()
        self.assertEqual(
            self.obrigacao.status, ObrigacaoEstoquePedido.Status.CANCELADA
        )

    def _comando(self, *args):
        return call_command(
            "reconstruir_obrigacoes_estoque",
            *args,
            stdout=StringIO(),
        )

    def test_comando_aplica_evidencia_e_nao_duplica_saida(self):
        movimento = self._movimento()
        movimentos_antes = MovimentoEstoque.objects.count()

        self._comando("--aplicar")

        self.obrigacao.refresh_from_db()
        self.assertEqual(
            self.obrigacao.status, ObrigacaoEstoquePedido.Status.RESOLVIDA
        )
        self.assertEqual(self.obrigacao.evidencia_baixada, Decimal("3.00"))
        self.assertEqual(MovimentoEstoque.objects.count(), movimentos_antes)
        self.assertTrue(
            movimento.pk
            in [
                item["movimento_id"]
                for item in self.obrigacao.evidencia_detalhe["movimentos"]
            ]
        )

    def test_comando_reverte_obrigacao_resolvida_sem_evidencia(self):
        self.obrigacao.status = ObrigacaoEstoquePedido.Status.RESOLVIDA
        self.obrigacao.quantidade_baixada = Decimal("3.00")
        self.obrigacao.save()

        self._comando("--aplicar")

        self.obrigacao.refresh_from_db()
        self.assertEqual(
            self.obrigacao.status, ObrigacaoEstoquePedido.Status.PENDENTE
        )
        self.assertEqual(self.obrigacao.quantidade_baixada, Decimal("0.00"))

        self.pedido.definir_status_financeiro(
            Pedido.StatusFinanceiro.PAGO, motivo="teste"
        )
        self.pedido.financeiro_conciliado = True
        self.pedido.save(update_fields=["financeiro_conciliado"])
        with self.assertRaises(ValidationError):
            self.pedido.transicionar(Pedido.Status.EM_SEPARACAO)

    def test_comando_dry_run_nao_altera(self):
        self._movimento()
        self._comando()
        self.obrigacao.refresh_from_db()
        self.assertEqual(
            self.obrigacao.status, ObrigacaoEstoquePedido.Status.PENDENTE
        )
        self.assertEqual(self.obrigacao.quantidade_baixada, Decimal("0.00"))

    def test_comando_idempotente(self):
        self._movimento()
        self._comando("--aplicar")
        movimentos = MovimentoEstoque.objects.count()
        self._comando("--aplicar")
        self.assertEqual(MovimentoEstoque.objects.count(), movimentos)
