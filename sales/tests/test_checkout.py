from decimal import Decimal

from django.core import mail
from django.test import TestCase
from django.urls import reverse

from customers.models import Cliente
from sales.models import Pedido
from stock.models import Estoque

from .helpers import criar_produto_com_estoque, fluxo_checkout


class CheckoutTests(TestCase):
    def test_checkout_cria_pedido_com_itens_e_reserva_estoque(self):
        pedido = fluxo_checkout(self.client, quantidade=4)

        self.assertEqual(pedido.status, Pedido.Status.AGUARDANDO_PAGAMENTO)
        item = pedido.itens.first()
        self.assertEqual(item.quantidade, Decimal("4"))
        # Preço capturado no servidor no momento do checkout
        self.assertEqual(item.preco_unitario, Decimal("10.00"))

        estoque = Estoque.objects.get(
            produto=item.produto, unidade=pedido.unidade
        )
        self.assertEqual(estoque.quantidade_bloqueada, Decimal("4"))
        self.assertEqual(pedido.total, Decimal("40.00"))
        self.assertEqual(pedido.canal, Pedido.Canal.LOJA)

    def test_documento_invalido_impede_pedido(self):
        produto, _unidade = criar_produto_com_estoque()
        self.client.post(
            reverse("sales:adicionar"),
            {"produto_id": produto.pk, "quantidade": "1"},
        )
        resposta = self.client.post(
            reverse("sales:checkout"),
            {
                "nome": "Alguém",
                "documento": "111.111.111-11",
                "email": "a@b.com",
                "modalidade": "retirada",
                "unidade": "1",
            },
        )
        self.assertEqual(resposta.status_code, 200)
        texto = resposta.content.decode()
        self.assertIn("CPF inválido", texto)
        self.assertFalse(Pedido.objects.exists())

    def test_retirada_vincula_unidade_escolhida(self):
        pedido = fluxo_checkout(self.client, quantidade=2)
        self.assertEqual(pedido.modalidade, Pedido.Modalidade.RETIRADA)
        self.assertTrue(pedido.unidade.ativa)

    def test_entrega_exige_endereco_completo(self):
        produto, unidade = criar_produto_com_estoque()
        self.client.post(
            reverse("sales:adicionar"),
            {"produto_id": produto.pk, "quantidade": "1"},
        )
        dados = {
            "nome": "Maria",
            "documento": "529.982.247-25",
            "email": "maria@example.com",
            "modalidade": "entrega",
            "unidade": unidade.pk,
            # sem logradouro/cidade/uf
        }
        resposta = self.client.post(reverse("sales:checkout"), dados)
        self.assertEqual(resposta.status_code, 200)
        self.assertIn("endereço completo", resposta.content.decode())
        self.assertFalse(Pedido.objects.exists())

    def test_quantidade_maior_que_saldo_da_unidade_bloqueia(self):
        produto, _unidade = criar_produto_com_estoque(saldo="3.00")
        self.client.post(
            reverse("sales:adicionar"),
            {"produto_id": produto.pk, "quantidade": "10"},
        )
        resposta = self.client.post(
            reverse("sales:checkout"),
            {
                "nome": "João",
                "documento": "529.982.247-25",
                "email": "j@example.com",
                "modalidade": "retirada",
                "unidade": "1",
            },
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertIn("indisponível", resposta.content.decode())
        self.assertFalse(Pedido.objects.exists())

    def test_cliente_e_reutilizado_pelo_documento(self):
        fluxo_checkout(self.client, quantidade=1)
        fluxo_checkout(self.client, quantidade=2)
        self.assertEqual(Cliente.objects.count(), 1)
        self.assertEqual(Pedido.objects.count(), 2)

    def test_carrinho_e_limpo_apos_checkout(self):
        fluxo_checkout(self.client, quantidade=2)
        page = self.client.get(reverse("sales:carrinho"))
        self.assertContains(page, "está vazio")

    def test_email_de_pedido_criado_e_enviado(self):
        mail.outbox.clear()
        pedido = fluxo_checkout(self.client, quantidade=1)
        self.assertEqual(len(mail.outbox), 1)
        corpo = mail.outbox[0].body
        self.assertIn(pedido.numero, corpo)
