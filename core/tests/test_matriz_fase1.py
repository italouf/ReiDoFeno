"""Matriz consolidada de acesso para todas as URLs internas da Fase 1.

Espec access-control: cada URL é testada diretamente para cada perfil.
"""
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from accounts.models import Usuario
from catalog.factories import CategoriaFactory, ProdutoFactory
from core.factories import UnidadeFactory
from costs.factories import DespesaFactory
from customers.factories import ClienteFactory

# (nome_url, kwargs, perfis com acesso 200)
URLS_INTERNAS = (
    ("core:painel", {}, {"administrador", "gestor", "vendedor"}),
    (
        "core:unidade_lista",
        {},
        {"administrador", "gestor"},
    ),
    ("core:unidade_novo", {}, {"administrador", "gestor"}),
    ("catalog:produto_lista", {}, {"administrador", "gestor"}),
    ("catalog:produto_novo", {}, {"administrador", "gestor"}),
    ("catalog:categoria_lista", {}, {"administrador", "gestor"}),
    ("catalog:categoria_novo", {}, {"administrador", "gestor"}),
    (
        "customers:cliente_lista",
        {},
        {"administrador", "gestor", "vendedor"},
    ),
    (
        "customers:cliente_novo",
        {},
        {"administrador", "gestor"},
    ),
    ("stock:estoque_lista", {}, {"administrador", "gestor"}),
    ("stock:movimento_lista", {}, {"administrador", "gestor"}),
    ("stock:movimento_entrada", {}, {"administrador", "gestor"}),
    ("stock:movimento_saida", {}, {"administrador", "gestor"}),
    ("stock:movimento_ajuste", {}, {"administrador", "gestor"}),
    ("stock:movimento_transferencia", {}, {"administrador", "gestor"}),
    ("costs:despesa_lista", {}, {"administrador", "gestor"}),
    ("costs:despesa_novo", {}, {"administrador", "gestor"}),
)

PERFIS = ("administrador", "gestor", "vendedor", "cliente")


class MatrizCompletaFase1Tests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_groups", verbosity=0)
        cls.senha = "senha-forte-123"
        cls.usuarios = {}
        for perfil in PERFIS:
            usuario = Usuario.objects.create_user(
                username=perfil, password=cls.senha
            )
            usuario.groups.add(Group.objects.get(name=perfil.capitalize()))
            cls.usuarios[perfil] = usuario

        cls.produto = ProdutoFactory()
        cls.categoria = CategoriaFactory()
        cls.unidade = UnidadeFactory()
        cls.cliente_obj = ClienteFactory()
        cls.despesa = DespesaFactory()

        cls.urls_com_pk = {
            "core:unidade_editar": {"pk": cls.unidade.pk},
            "catalog:produto_editar": {"pk": cls.produto.pk},
            "catalog:categoria_editar": {"pk": cls.categoria.pk},
            "customers:cliente_detalhe": {"pk": cls.cliente_obj.pk},
            "customers:cliente_editar": {"pk": cls.cliente_obj.pk},
            "costs:despesa_editar": {"pk": cls.despesa.pk},
        }

    def _todas_urls(self):
        yield from ((nome, kwargs) for nome, kwargs, _ in URLS_INTERNAS)
        yield from self.urls_com_pk.items()

    def _acesso_esperado(self, nome_url):
        for nome, _, acessos in URLS_INTERNAS:
            if nome == nome_url:
                return acessos
        # URLs de edição/detalhe seguem o mesmo recorte da lista correspondente
        if nome_url.startswith("catalog"):
            return {"administrador", "gestor"}
        if nome_url.startswith("customers") and "detalhe" in nome_url:
            return {"administrador", "gestor", "vendedor"}
        if nome_url.startswith("customers"):
            return {"administrador", "gestor"}
        return {"administrador", "gestor"}

    def test_matriz_por_perfil(self):
        for perfil in PERFIS:
            with self.subTest(perfil=perfil):
                self.client.force_login(self.usuarios[perfil])
                for nome_url, kwargs in self._todas_urls():
                    with self.subTest(url=nome_url):
                        resposta = self.client.get(reverse(nome_url, kwargs=kwargs))
                        esperado = (
                            200
                            if perfil in self._acesso_esperado(nome_url)
                            else 403
                        )
                        self.assertEqual(
                            resposta.status_code,
                            esperado,
                            f"{perfil} em {nome_url}",
                        )
                self.client.logout()

    def test_anonimo_redirecionado_em_todas_as_urls(self):
        for nome_url, kwargs in self._todas_urls():
            with self.subTest(url=nome_url):
                resposta = self.client.get(reverse(nome_url, kwargs=kwargs))
                self.assertEqual(resposta.status_code, 302, nome_url)

    def test_healthz_continua_publico(self):
        resposta = self.client.get("/healthz/")
        self.assertEqual(resposta.status_code, 200)
