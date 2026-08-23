from decimal import Decimal

from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from accounts.models import Usuario
from catalog.factories import ProdutoFactory
from core.factories import UnidadeFactory, UnidadeIacuFactory
from stock.factories import EstoqueFactory
from stock.models import Estoque, MovimentoEstoque

URLS_ESTOQUE = (
    "stock:estoque_lista",
    "stock:movimento_lista",
    "stock:movimento_entrada",
    "stock:movimento_saida",
    "stock:movimento_ajuste",
    "stock:movimento_transferencia",
)


class EstoqueAcessoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_groups", verbosity=0)
        cls.senha = "senha-forte-123"
        cls.usuarios = {}
        for perfil in ("administrador", "gestor", "vendedor", "cliente"):
            usuario = Usuario.objects.create_user(
                username=perfil, password=cls.senha
            )
            usuario.groups.add(Group.objects.get(name=perfil.capitalize()))
            cls.usuarios[perfil] = usuario

    def test_admin_e_gestor_acessam_telas_de_estoque(self):
        for perfil in ("administrador", "gestor"):
            with self.subTest(perfil=perfil):
                self.client.force_login(self.usuarios[perfil])
                for nome_url in URLS_ESTOQUE:
                    resposta = self.client.get(reverse(nome_url))
                    self.assertEqual(resposta.status_code, 200, nome_url)
                self.client.logout()

    def test_vendedor_e_cliente_negados_no_estoque_administrativo(self):
        for perfil, status in (("vendedor", 403), ("cliente", 403)):
            with self.subTest(perfil=perfil):
                self.client.force_login(self.usuarios[perfil])
                for nome_url in URLS_ESTOQUE:
                    resposta = self.client.get(reverse(nome_url))
                    self.assertEqual(resposta.status_code, status, nome_url)
                self.client.logout()

    def test_anonimo_redirecionado_para_login(self):
        resposta = self.client.get(reverse("stock:estoque_lista"))
        self.assertEqual(resposta.status_code, 302)
        self.assertIn("/accounts/login/", resposta["Location"])


class MovimentacaoFluxoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_groups", verbosity=0)
        cls.gestor = Usuario.objects.create_user(
            username="gestor", password="senha-forte-123"
        )
        cls.gestor.groups.add(Group.objects.get(name="Gestor"))
        cls.produto = ProdutoFactory()
        cls.feira = UnidadeFactory(nome="Feira de Santana")
        cls.iacu = UnidadeIacuFactory()

    def setUp(self):
        self.client.force_login(self.gestor)

    def test_entrada_via_post_aumenta_saldo(self):
        resposta = self.client.post(
            reverse("stock:movimento_entrada"),
            {
                "tipo": "entrada",
                "produto": self.produto.pk,
                "unidade": self.feira.pk,
                "quantidade": "40.00",
            },
            follow=True,
        )
        self.assertRedirects(resposta, reverse("stock:movimento_lista"))
        estoque = Estoque.objects.get(
            produto=self.produto, unidade=self.feira
        )
        self.assertEqual(estoque.quantidade, Decimal("40"))

    def test_saida_acima_do_saldo_mostra_erro(self):
        resposta = self.client.post(
            reverse("stock:movimento_saida"),
            {
                "tipo": "saida",
                "produto": self.produto.pk,
                "unidade": self.feira.pk,
                "quantidade": "5.00",
            },
        )
        self.assertEqual(resposta.status_code, 200)
        texto = resposta.content.decode()
        self.assertIn("Saída acima do saldo disponível", texto)

    def test_ajuste_sem_motivo_mostra_erro_campo(self):
        resposta = self.client.post(
            reverse("stock:movimento_ajuste"),
            {
                "produto": self.produto.pk,
                "unidade": self.feira.pk,
                "quantidade": "-2.00",
                "motivo": "",
            },
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertIn("obrigat", resposta.content.decode())

    def test_transferencia_via_post(self):
        EstoqueFactory(
            produto=self.produto, unidade=self.feira, quantidade="50"
        )
        resposta = self.client.post(
            reverse("stock:movimento_transferencia"),
            {
                "produto": self.produto.pk,
                "unidade_origem": self.feira.pk,
                "unidade_destino": self.iacu.pk,
                "quantidade": "15.00",
            },
            follow=True,
        )
        self.assertRedirects(resposta, reverse("stock:movimento_lista"))
        origem = Estoque.objects.get(produto=self.produto, unidade=self.feira)
        destino = Estoque.objects.get(produto=self.produto, unidade=self.iacu)
        self.assertEqual(origem.quantidade, Decimal("35"))
        self.assertEqual(destino.quantidade, Decimal("15"))
        saida = MovimentoEstoque.objects.filter(tipo="saida").latest("id")
        entrada = MovimentoEstoque.objects.filter(tipo="entrada").latest("id")
        self.assertEqual(saida.movimento_par, entrada)

    def test_ledger_exibe_movimentos(self):
        EstoqueFactory(produto=self.produto, unidade=self.feira)
        self.client.post(
            reverse("stock:movimento_entrada"),
            {
                "tipo": "entrada",
                "produto": self.produto.pk,
                "unidade": self.feira.pk,
                "quantidade": "7.00",
            },
        )
        resposta = self.client.get(reverse("stock:movimento_lista"))
        self.assertContains(resposta, self.produto.nome)
