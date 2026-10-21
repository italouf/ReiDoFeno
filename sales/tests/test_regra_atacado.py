"""Regra de atacado: cliente ATACADO + mais de 50 fardos."""

from decimal import Decimal

from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import RequestFactory, TestCase
from django.urls import reverse

from accounts.models import Usuario
from catalog.factories import ProdutoFactory
from catalog.models import Produto
from core.factories import UnidadeFactory
from core.models import Unidade
from customers.factories import ClienteFactory
from customers.models import Cliente
from sales.cart import Carrinho
from sales.models import Pedido
from sales.services import calcular_item_pedido, calcular_preco_unitario
from stock.factories import EstoqueFactory

from .helpers import DADOS_BASE


def _produto_fardo(**kwargs):
    dados = {
        "unidade_medida": Produto.UnidadeMedida.FARDO,
        "preco_balcao": Decimal("100.00"),
        "preco_online": Decimal("110.00"),
        "preco_atacado": Decimal("80.00"),
    }
    dados.update(kwargs)
    return ProdutoFactory(**dados)


class RegraAtacadoTests(TestCase):
    def test_cliente_atacado_com_51_fardos_usa_preco_atacado(self):
        produto = _produto_fardo()
        cliente = ClienteFactory(categoria=Cliente.Categoria.ATACADO)

        item = calcular_item_pedido(
            produto=produto,
            cliente=cliente,
            quantidade=Decimal("51.00"),
        )

        assert item.preco_unitario == Decimal("80.00")

    def test_cliente_atacado_com_50_fardos_usa_preco_balcao(self):
        """Limiar é >50, não >=50."""
        produto = _produto_fardo()
        cliente = ClienteFactory(categoria=Cliente.Categoria.ATACADO)

        item = calcular_item_pedido(
            produto=produto,
            cliente=cliente,
            quantidade=Decimal("50.00"),
        )

        assert item.preco_unitario == Decimal("100.00")

    def test_cliente_varejo_sempre_usa_preco_balcao_na_regra(self):
        produto = _produto_fardo()
        cliente = ClienteFactory(categoria=Cliente.Categoria.VAREJO)

        item = calcular_item_pedido(
            produto=produto,
            cliente=cliente,
            quantidade=Decimal("100.00"),
        )

        assert item.preco_unitario == Decimal("100.00")

    def test_produto_sem_preco_atacado_usa_balcao(self):
        produto = _produto_fardo(preco_atacado=None)
        cliente = ClienteFactory(categoria=Cliente.Categoria.ATACADO)

        item = calcular_item_pedido(
            produto=produto,
            cliente=cliente,
            quantidade=Decimal("100.00"),
        )

        assert item.preco_unitario == Decimal("100.00")

    def test_produto_que_nao_e_fardo_nao_aplica_atacado(self):
        produto = _produto_fardo(unidade_medida=Produto.UnidadeMedida.SACA)
        cliente = ClienteFactory(categoria=Cliente.Categoria.ATACADO)

        item = calcular_item_pedido(
            produto=produto,
            cliente=cliente,
            quantidade=Decimal("100.00"),
        )

        assert item.preco_unitario == Decimal("100.00")

    def test_limiar_com_fracao_acima_de_50_aplica_atacado(self):
        produto = _produto_fardo()
        cliente = ClienteFactory(categoria=Cliente.Categoria.ATACADO)

        preco = calcular_preco_unitario(
            produto=produto,
            cliente=cliente,
            quantidade=Decimal("50.01"),
        )

        assert preco == Decimal("80.00")

    def test_preco_base_do_canal_e_preservado_sem_atacado(self):
        produto = _produto_fardo(preco_atacado=None)
        cliente = ClienteFactory(categoria=Cliente.Categoria.VAREJO)

        preco = calcular_preco_unitario(
            produto=produto,
            cliente=cliente,
            quantidade=Decimal("51.00"),
            preco_base=produto.preco_online,
        )

        assert preco == Decimal("110.00")


class CheckoutAtacadoTests(TestCase):
    def _preparar(self, *, categoria, verificado=True, **produto_kwargs):
        cliente = ClienteFactory(
            documento="52998224725",
            categoria=categoria,
        )
        if verificado:
            usuario = Usuario.objects.create_user(
                username=f"atacado-{cliente.pk}",
                password="senha-forte-123",
            )
            cliente.usuario = usuario
            cliente.vinculo_verificado = True
            cliente.save(update_fields=["usuario", "vinculo_verificado"])
            self.client.force_login(usuario)
        produto = _produto_fardo(**produto_kwargs)
        unidade = UnidadeFactory(nome="Feira de Santana")
        EstoqueFactory(
            produto=produto, unidade=unidade, quantidade="200.00"
        )
        return cliente, produto, unidade

    def test_checkout_atacado_51_fardos_captura_preco_atacado(self):
        cliente, produto, unidade = self._preparar(
            categoria=Cliente.Categoria.ATACADO
        )
        self.client.post(
            reverse("sales:adicionar"),
            {"produto_id": produto.pk, "quantidade": "51"},
        )
        dados = dict(DADOS_BASE)
        dados["unidade"] = unidade.pk
        resposta = self.client.post(reverse("sales:checkout"), dados)
        assert resposta.status_code == 302
        pedido = Pedido.objects.latest("pk")
        item = pedido.itens.get()
        assert item.preco_unitario == Decimal("80.00")
        assert pedido.total == Decimal("4080.00")

    def test_checkout_atacado_50_fardos_usa_preco_balcao(self):
        cliente, produto, unidade = self._preparar(
            categoria=Cliente.Categoria.ATACADO
        )
        self.client.post(
            reverse("sales:adicionar"),
            {"produto_id": produto.pk, "quantidade": "50"},
        )
        dados = dict(DADOS_BASE)
        dados["unidade"] = unidade.pk
        resposta = self.client.post(reverse("sales:checkout"), dados)
        assert resposta.status_code == 302
        pedido = Pedido.objects.latest("pk")
        assert pedido.itens.get().preco_unitario == Decimal("100.00")

    def test_checkout_varejo_usa_preco_online(self):
        cliente, produto, unidade = self._preparar(
            categoria=Cliente.Categoria.VAREJO
        )
        self.client.post(
            reverse("sales:adicionar"),
            {"produto_id": produto.pk, "quantidade": "51"},
        )
        dados = dict(DADOS_BASE)
        dados["unidade"] = unidade.pk
        resposta = self.client.post(reverse("sales:checkout"), dados)
        assert resposta.status_code == 302
        pedido = Pedido.objects.latest("pk")
        assert pedido.itens.get().preco_unitario == Decimal("110.00")

    def test_checkout_atacado_sem_preco_atacado_usa_balcao(self):
        cliente, produto, unidade = self._preparar(
            categoria=Cliente.Categoria.ATACADO, preco_atacado=None
        )
        self.client.post(
            reverse("sales:adicionar"),
            {"produto_id": produto.pk, "quantidade": "51"},
        )
        dados = dict(DADOS_BASE)
        dados["unidade"] = unidade.pk
        resposta = self.client.post(reverse("sales:checkout"), dados)
        assert resposta.status_code == 302
        pedido = Pedido.objects.latest("pk")
        assert pedido.itens.get().preco_unitario == Decimal("100.00")

    def test_unidade_do_checkout_e_a_escolhida(self):
        _cliente, produto, unidade = self._preparar(
            categoria=Cliente.Categoria.ATACADO
        )
        self.client.post(
            reverse("sales:adicionar"),
            {"produto_id": produto.pk, "quantidade": "51"},
        )
        dados = dict(DADOS_BASE)
        dados["unidade"] = unidade.pk
        self.client.post(reverse("sales:checkout"), dados)
        pedido = Pedido.objects.latest("pk")
        assert pedido.unidade_id == unidade.pk
        assert Unidade.objects.filter(pk=unidade.pk).exists()

    def test_visitante_com_documento_atacado_paga_preco_online(self):
        cliente, produto, unidade = self._preparar(
            categoria=Cliente.Categoria.ATACADO, verificado=False
        )
        self.client.post(
            reverse("sales:adicionar"),
            {"produto_id": produto.pk, "quantidade": "51"},
        )
        dados = dict(DADOS_BASE)
        dados["unidade"] = unidade.pk
        resposta = self.client.post(reverse("sales:checkout"), dados)
        assert resposta.status_code == 302
        pedido = Pedido.objects.latest("pk")
        assert pedido.identidade_verificada is False
        assert pedido.itens.get().preco_unitario == Decimal("110.00")
        cliente.refresh_from_db()
        assert cliente.categoria == Cliente.Categoria.ATACADO

    def test_vendedor_interno_aplica_atacado_para_cliente_cadastrado(self):
        call_command("seed_groups", verbosity=0)
        vendedor = Usuario.objects.create_user(
            username="vendedor-atacado", password="senha-forte-123"
        )
        vendedor.groups.add(Group.objects.get(name="Vendedor"))
        self.client.force_login(vendedor)
        cliente, produto, unidade = self._preparar(
            categoria=Cliente.Categoria.ATACADO, verificado=False
        )
        # _preparar não loga quando verificado=False; restaura o vendedor.
        self.client.force_login(vendedor)
        self.client.post(
            reverse("sales:adicionar"),
            {"produto_id": produto.pk, "quantidade": "51"},
        )
        dados = dict(DADOS_BASE)
        dados["unidade"] = unidade.pk
        resposta = self.client.post(reverse("sales:checkout"), dados)
        assert resposta.status_code == 302
        pedido = Pedido.objects.latest("pk")
        assert pedido.canal == Pedido.Canal.VENDEDOR
        assert pedido.itens.get().preco_unitario == Decimal("80.00")
        assert cliente.categoria == Cliente.Categoria.ATACADO

    def test_carrinho_de_atacadista_verificado_mostra_preco_final(self):
        cliente, produto, _unidade = self._preparar(
            categoria=Cliente.Categoria.ATACADO
        )
        request = RequestFactory().get("/carrinho/")
        request.session = self.client.session
        request.user = cliente.usuario
        carrinho = Carrinho(request)
        carrinho.adicionar(produto.pk, 51)
        item = carrinho.itens()[0]
        assert item["subtotal"] == Decimal("4080.00")

    def test_carrinho_de_visitante_mostra_preco_online(self):
        _cliente, produto, _unidade = self._preparar(
            categoria=Cliente.Categoria.ATACADO, verificado=False
        )
        request = RequestFactory().get("/carrinho/")
        request.session = self.client.session
        request.user = type(
            "Anonimo", (), {"is_authenticated": False}
        )()
        carrinho = Carrinho(request)
        carrinho.adicionar(produto.pk, 51)
        item = carrinho.itens()[0]
        assert item["subtotal"] == Decimal("5610.00")
