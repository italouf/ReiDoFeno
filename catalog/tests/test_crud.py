from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from accounts.models import Usuario
from catalog.factories import CategoriaFactory, ProdutoFactory
from catalog.models import Produto

URLS_PROTEGIDAS = (
    ("catalog:produto_lista", {}),
    ("catalog:produto_novo", {}),
    ("catalog:categoria_lista", {}),
    ("catalog:categoria_novo", {}),
    ("core:unidade_lista", {}),
    ("core:unidade_novo", {}),
)


class CrudPermissaoTests(TestCase):
    """Somente administrador e gestor acessam os cadastros (espec access-control)."""

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

    def test_admin_e_gestor_acessam_cadastros(self):
        for perfil in ("administrador", "gestor"):
            with self.subTest(perfil=perfil):
                self.client.force_login(self.usuarios[perfil])
                for nome_url, kwargs in URLS_PROTEGIDAS:
                    resposta = self.client.get(reverse(nome_url, kwargs=kwargs))
                    self.assertEqual(resposta.status_code, 200, nome_url)
                self.client.logout()

    def test_vendedor_cliente_e_anonimo_negados(self):
        esperado = {
            "vendedor": 403,
            "cliente": 403,
        }
        for perfil, status in esperado.items():
            with self.subTest(perfil=perfil):
                self.client.force_login(self.usuarios[perfil])
                for nome_url, kwargs in URLS_PROTEGIDAS:
                    resposta = self.client.get(reverse(nome_url, kwargs=kwargs))
                    self.assertEqual(resposta.status_code, status, nome_url)
                self.client.logout()

        for nome_url, kwargs in URLS_PROTEGIDAS:
            resposta = self.client.get(reverse(nome_url, kwargs=kwargs))
            self.assertEqual(resposta.status_code, 302, nome_url)

    def test_gestor_cadastra_produto_via_post(self):
        self.client.force_login(self.usuarios["gestor"])
        categoria = CategoriaFactory()
        dados = {
            "nome": "Feno Tifton 85",
            "categoria": categoria.pk,
            "ncm": "1214.90.00",
            "unidade_medida": "kg",
            "custo": "3.50",
            "preco_balcao": "6.00",
            "preco_online": "5.50",
            "ativo": "on",
        }
        resposta = self.client.post(
            reverse("catalog:produto_novo"), dados, follow=True
        )
        self.assertRedirects(resposta, reverse("catalog:produto_lista"))
        self.assertTrue(Produto.objects.filter(nome="Feno Tifton 85").exists())

    def test_vendedor_nao_cadastra_produto_via_post(self):
        self.client.force_login(self.usuarios["vendedor"])
        categoria = CategoriaFactory()
        resposta = self.client.post(
            reverse("catalog:produto_novo"),
            {
                "nome": "Feno Proibido",
                "categoria": categoria.pk,
                "unidade_medida": "kg",
                "custo": "1.00",
                "preco_balcao": "2.00",
                "preco_online": "2.00",
            },
        )
        self.assertEqual(resposta.status_code, 403)
        self.assertFalse(Produto.objects.filter(nome="Feno Proibido").exists())

    def test_edicao_de_produto_funciona_para_gestor(self):
        self.client.force_login(self.usuarios["gestor"])
        produto = ProdutoFactory(nome="Antigo")
        resposta = self.client.post(
            reverse("catalog:produto_editar", args=[produto.pk]),
            {
                "nome": "Novo Nome",
                "categoria": produto.categoria.pk,
                "ncm": "",
                "unidade_medida": produto.unidade_medida,
                "custo": produto.custo,
                "preco_balcao": produto.preco_balcao,
                "preco_online": produto.preco_online,
                "ativo": "on",
            },
            follow=True,
        )
        self.assertRedirects(resposta, reverse("catalog:produto_lista"))
        produto.refresh_from_db()
        self.assertEqual(produto.nome, "Novo Nome")

    def test_alteracao_de_preco_gera_auditoria_com_antes_e_depois(self):
        from core.models import LogAuditoria

        self.client.force_login(self.usuarios["gestor"])
        produto = ProdutoFactory(preco_online="100.00")
        self.client.post(
            reverse("catalog:produto_editar", args=[produto.pk]),
            {
                "nome": produto.nome,
                "categoria": produto.categoria.pk,
                "ncm": "",
                "unidade_medida": produto.unidade_medida,
                "custo": produto.custo,
                "preco_balcao": produto.preco_balcao,
                "preco_online": "150.00",
                "ativo": "on",
            },
            follow=True,
        )
        registro = (
            LogAuditoria.objects.filter(acao="produto.alterado")
            .order_by("-criado_em")
            .first()
        )
        self.assertIsNotNone(registro)
        self.assertEqual(registro.antes.get("preco_online"), "100.00")
        self.assertEqual(registro.depois.get("preco_online"), "150.00")
        self.assertIsNotNone(registro.ip)
