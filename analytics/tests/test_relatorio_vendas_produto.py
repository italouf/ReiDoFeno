"""Relatório de vendas por produto, dia e unidade."""

from datetime import date, datetime, time
from decimal import Decimal

from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Usuario
from analytics.services import vendas_por_produto
from catalog.factories import ProdutoFactory
from core.factories import UnidadeFactory, UnidadeIacuFactory
from sales.factories import ItemPedidoFactory, PagamentoFactory, PedidoFactory
from sales.models import Pagamento, Pedido

DIA = date(2026, 10, 1)


def _pedido_pago(
    *,
    produto,
    unidade,
    quantidade: int,
    preco: Decimal,
    dia: date = DIA,
    custo: Decimal | None = None,
):
    pedido = PedidoFactory(
        status=Pedido.Status.PAGO,
        unidade=unidade,
        subtotal=preco * quantidade,
        total=preco * quantidade,
    )
    ItemPedidoFactory(
        pedido=pedido,
        produto=produto,
        quantidade=quantidade,
        preco_unitario=preco,
        custo_unitario=custo if custo is not None else produto.custo,
    )
    aprovado_em = timezone.make_aware(datetime.combine(dia, time.min))
    PagamentoFactory(
        pedido=pedido,
        valor=preco * quantidade,
        status=Pagamento.Status.APROVADO,
        aprovado_em=aprovado_em,
    )
    return pedido


class RelatorioVendasProdutoTests(TestCase):
    def test_vendas_agrupadas_por_produto_dia_unidade(self):
        produto1 = ProdutoFactory(nome="Feno A", custo=Decimal("10.00"))
        produto2 = ProdutoFactory(nome="Feno B", custo=Decimal("5.00"))
        unidade_fs = UnidadeFactory(nome="Feira de Santana")

        _pedido_pago(
            produto=produto1, unidade=unidade_fs, quantidade=10,
            preco=Decimal("10.00"),
        )
        _pedido_pago(
            produto=produto1, unidade=unidade_fs, quantidade=5,
            preco=Decimal("10.00"),
        )
        _pedido_pago(
            produto=produto2, unidade=unidade_fs, quantidade=3,
            preco=Decimal("10.00"),
        )

        relatorio = vendas_por_produto(DIA, DIA, unidade=unidade_fs)

        self.assertEqual(len(relatorio), 2)
        feno_a = next(r for r in relatorio if r["produto"] == "Feno A")
        self.assertEqual(feno_a["quantidade"], Decimal("15.00"))
        self.assertEqual(feno_a["receita"], Decimal("150.00"))
        self.assertEqual(feno_a["cmv"], Decimal("150.00"))
        self.assertEqual(feno_a["lucro_bruto"], Decimal("0.00"))

    def test_filtro_por_unidade(self):
        fs = UnidadeFactory(nome="Feira de Santana")
        iacu = UnidadeIacuFactory()
        produto = ProdutoFactory()

        _pedido_pago(
            produto=produto, unidade=fs, quantidade=1,
            preco=Decimal("100.00"),
        )
        _pedido_pago(
            produto=produto, unidade=iacu, quantidade=1,
            preco=Decimal("200.00"),
        )

        relatorio_fs = vendas_por_produto(DIA, DIA, unidade=fs)

        self.assertEqual(
            sum(r["receita"] for r in relatorio_fs), Decimal("100.00")
        )

    def test_cmv_e_lucro_por_linha(self):
        produto = ProdutoFactory(custo=Decimal("30.00"))
        unidade = UnidadeFactory()

        _pedido_pago(
            produto=produto, unidade=unidade, quantidade=2,
            preco=Decimal("50.00"), custo=Decimal("30.00"),
        )

        linha = vendas_por_produto(DIA, DIA, unidade=unidade)[0]

        self.assertEqual(linha["receita"], Decimal("100.00"))
        self.assertEqual(linha["cmv"], Decimal("60.00"))
        self.assertEqual(linha["lucro_bruto"], Decimal("40.00"))

    def test_produtos_homonimos_nao_sao_mesclados(self):
        unidade = UnidadeFactory()
        produto_a = ProdutoFactory(nome="Feno Homonimo")
        produto_b = ProdutoFactory(nome="Feno Homonimo")
        _pedido_pago(
            produto=produto_a, unidade=unidade, quantidade=1,
            preco=Decimal("10.00"),
        )
        _pedido_pago(
            produto=produto_b, unidade=unidade, quantidade=2,
            preco=Decimal("10.00"),
        )

        relatorio = vendas_por_produto(DIA, DIA, unidade=unidade)

        self.assertEqual(len(relatorio), 2)
        self.assertEqual(
            {linha["produto_id"] for linha in relatorio},
            {produto_a.pk, produto_b.pk},
        )

    def test_renomeacao_preserva_snapshot_do_item(self):
        produto = ProdutoFactory(nome="Nome no Checkout")
        unidade = UnidadeFactory()
        _pedido_pago(
            produto=produto, unidade=unidade, quantidade=1,
            preco=Decimal("10.00"),
        )
        produto.nome = "Nome Novo no Catalogo"
        produto.save(update_fields=["nome"])

        relatorio = vendas_por_produto(DIA, DIA, unidade=unidade)

        self.assertEqual(relatorio[0]["produto"], "Nome no Checkout")

    def test_periodo_fora_nao_aparece(self):
        produto = ProdutoFactory()
        unidade = UnidadeFactory()
        _pedido_pago(
            produto=produto, unidade=unidade, quantidade=1,
            preco=Decimal("100.00"), dia=date(2026, 9, 1),
        )

        self.assertEqual(vendas_por_produto(DIA, DIA, unidade=unidade), [])

    def test_exportacao_csv(self):
        produto = ProdutoFactory(nome="Feno CSV")
        unidade = UnidadeFactory()
        _pedido_pago(
            produto=produto, unidade=unidade, quantidade=1,
            preco=Decimal("100.00"),
        )

        call_command("seed_groups", verbosity=0)
        gestor = Usuario.objects.create_user(
            username="gestor_csv", password="senha-forte-123"
        )
        gestor.groups.add(Group.objects.get(name="Gestor"))
        self.client.force_login(gestor)

        resposta = self.client.get(
            reverse("analytics:relatorio_vendas_produto"),
            {"formato": "csv", "inicio": DIA.isoformat(), "fim": DIA.isoformat()},
        )

        self.assertEqual(resposta["Content-Type"], "text/csv")
        self.assertIn("Feno CSV", resposta.content.decode("utf-8"))

    def test_vendedor_recebe_403_no_relatorio(self):
        call_command("seed_groups", verbosity=0)
        vendedor = Usuario.objects.create_user(
            username="vend_csv", password="senha-forte-123"
        )
        vendedor.groups.add(Group.objects.get(name="Vendedor"))
        self.client.force_login(vendedor)

        resposta = self.client.get(
            reverse("analytics:relatorio_vendas_produto")
        )

        self.assertEqual(resposta.status_code, 403)
