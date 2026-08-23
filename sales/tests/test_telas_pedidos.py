from decimal import Decimal

from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from accounts.models import Usuario
from sales.factories import PedidoFactory
from sales.models import Pedido

from .helpers import fluxo_checkout


class MeusPedidosTests(TestCase):
    def test_cliente_ve_apenas_os_proprios_pedidos(self):
        pedido_meu = fluxo_checkout(self.client, quantidade=2)

        # Outro cliente faz um pedido em outra sessão
        from .helpers import DADOS_BASE, criar_produto_com_estoque

        produto, unidade = criar_produto_com_estoque()
        self.client.post(
            reverse("sales:adicionar"),
            {"produto_id": produto.pk, "quantidade": "1"},
        )
        dados = dict(DADOS_BASE)
        dados.update(
            {
                "nome": "Outro Cliente",
                "documento": "111.444.777-35",
                "email": "outro@example.com",
                "modalidade": "retirada",
                "unidade": unidade.pk,
            }
        )
        self.client.post(reverse("sales:checkout"), dados)

        # Cria usuário vinculado ao primeiro cliente e acessa a lista
        cliente = pedido_meu.cliente
        usuario = Usuario.objects.create_user(username="cli", password="senha-forte-123")
        cliente.usuario = usuario
        cliente.save()

        self.client.force_login(usuario)
        resposta = self.client.get(reverse("sales:meus_pedidos"))
        self.assertContains(resposta, pedido_meu.numero)


class PedidosInternosTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_groups", verbosity=0)
        cls.senha = "senha-forte-123"
        cls.usuarios = {}
        for perfil in ("administrador", "gestor", "vendedor"):
            usuario = Usuario.objects.create_user(
                username=perfil, password=cls.senha
            )
            usuario.groups.add(Group.objects.get(name=perfil.capitalize()))
            cls.usuarios[perfil] = usuario

    def test_vendedor_ve_somente_pedidos_que_criou(self):
        meu = PedidoFactory(usuario_criador=self.usuarios["vendedor"])
        de_outro = PedidoFactory(usuario_criador=self.usuarios["gestor"])

        self.client.force_login(self.usuarios["vendedor"])
        lista = self.client.get(reverse("sales:pedidos_internos"))
        texto = lista.content.decode()
        self.assertIn(meu.numero, texto)
        self.assertNotIn(de_outro.numero, texto)

    def test_gestor_ve_todos_os_pedidos(self):
        pedido_a = PedidoFactory(usuario_criador=self.usuarios["vendedor"])
        pedido_b = PedidoFactory()
        self.client.force_login(self.usuarios["gestor"])
        texto = self.client.get(reverse("sales:pedidos_internos")).content.decode()
        self.assertIn(pedido_a.numero, texto)
        self.assertIn(pedido_b.numero, texto)

    def test_vendedor_nao_abre_pedido_de_outro_vendedor(self):
        alheio = PedidoFactory(usuario_criador=self.usuarios["gestor"])
        self.client.force_login(self.usuarios["vendedor"])
        resposta = self.client.get(
            reverse("sales:pedido_interno_detail", args=[alheio.pk])
        )
        self.assertEqual(resposta.status_code, 404)

    def test_cliente_final_negado_na_area_interna(self):
        usuario = Usuario.objects.create_user(username="cli", password=self.senha)
        usuario.groups.add(Group.objects.get(name="Cliente"))
        self.client.force_login(usuario)
        resposta = self.client.get(reverse("sales:pedidos_internos"))
        self.assertEqual(resposta.status_code, 403)

    def test_transicao_por_gestor_avanca_pedido(self):
        pedido = fluxo_checkout(self.client, quantidade=1)
        pedido.transicionar(Pedido.Status.PAGO)
        self.client.force_login(self.usuarios["gestor"])
        resposta = self.client.post(
            reverse("sales:pedido_atualizar_status", args=[pedido.pk]),
            {"status": Pedido.Status.EM_SEPARACAO},
        )
        self.assertEqual(resposta.status_code, 302)
        pedido.refresh_from_db()
        self.assertEqual(pedido.status, Pedido.Status.EM_SEPARACAO)

    def test_cancelamento_via_view_libera_reserva(self):
        pedido = fluxo_checkout(self.client, quantidade=3)
        self.client.force_login(self.usuarios["gestor"])
        self.client.post(
            reverse("sales:pedido_atualizar_status", args=[pedido.pk]),
            {"status": Pedido.Status.CANCELADO},
        )
        item = pedido.itens.first()
        from stock.models import Estoque

        estoque = Estoque.objects.get(produto=item.produto, unidade=pedido.unidade)
        self.assertEqual(estoque.quantidade_bloqueada, Decimal("0"))

    def test_detalhe_interno_mostra_link_whatsapp_do_cliente(self):
        pedido = fluxo_checkout(self.client, quantidade=1)
        pedido.cliente.telefone = "(75) 98888-7777"
        pedido.cliente.save()

        self.client.force_login(self.usuarios["gestor"])
        resposta = self.client.get(
            reverse("sales:pedido_interno_detail", args=[pedido.pk])
        )
        self.assertContains(resposta, "https://wa.me/5575988887777")
