from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from accounts.models import Usuario
from customers.factories import ClienteFactory
from customers.models import Cliente


class ClienteCrudTests(TestCase):
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

    def dados_validos(self, **overrides):
        dados = {
            "nome": "João Fazendeiro",
            "tipo_pessoa": "fisica",
            "documento": "529.982.247-25",
            "categoria": "varejo",
            "telefone": "(75) 99999-0001",
            "email": "joao@example.com",
            "logradouro": "Rua das Pastagens",
            "numero": "100",
            "bairro": "Centro",
            "cidade": "Feira de Santana",
            "uf": "BA",
            "cep": "44000-000",
            "preferencia": "Feno em sacas, retira na loja",
        }
        dados.update(overrides)
        return dados

    def test_gestor_cadastra_cliente_com_cpf_valido(self):
        self.client.force_login(self.usuarios["gestor"])
        resposta = self.client.post(
            reverse("customers:cliente_novo"),
            self.dados_validos(),
            follow=True,
        )
        self.assertRedirects(resposta, reverse("customers:cliente_lista"))
        self.assertTrue(Cliente.objects.filter(documento="52998224725").exists())

    def test_rejeita_cpf_invalido_com_mensagem_especifica(self):
        self.client.force_login(self.usuarios["gestor"])
        resposta = self.client.post(
            reverse("customers:cliente_novo"),
            self.dados_validos(documento="111.444.777-34"),
        )
        self.assertEqual(resposta.status_code, 200)
        texto = resposta.content.decode()
        self.assertIn("CPF inválido", texto)

    def test_rejeita_cnpj_invalido_com_mensagem_especifica(self):
        self.client.force_login(self.usuarios["gestor"])
        resposta = self.client.post(
            reverse("customers:cliente_novo"),
            self.dados_validos(
                tipo_pessoa="juridica", documento="11.222.333/0001-82"
            ),
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertIn("CNPJ inválido", resposta.content.decode())

    def test_documento_obrigatorio(self):
        self.client.force_login(self.usuarios["gestor"])
        resposta = self.client.post(
            reverse("customers:cliente_novo"), self.dados_validos(documento="")
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(Cliente.objects.filter(nome="João Fazendeiro").exists())

    def test_documento_duplicado_e_rejeitado(self):
        ClienteFactory(documento="52998224725")
        self.client.force_login(self.usuarios["gestor"])
        resposta = self.client.post(
            reverse("customers:cliente_novo"), self.dados_validos()
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertIn("já está cadastrado", resposta.content.decode())

    def test_vendedor_consulta_mas_nao_edita_clientes(self):
        cliente = ClienteFactory()
        self.client.force_login(self.usuarios["vendedor"])

        lista = self.client.get(reverse("customers:cliente_lista"))
        self.assertEqual(lista.status_code, 200)

        detalhe = self.client.get(
            reverse("customers:cliente_detalhe", args=[cliente.pk])
        )
        self.assertEqual(detalhe.status_code, 200)

        novo = self.client.post(
            reverse("customers:cliente_novo"), self.dados_validos()
        )
        self.assertEqual(novo.status_code, 403)

        editar = self.client.post(
            reverse("customers:cliente_editar", args=[cliente.pk]),
            {"nome": "Alterado"},
        )
        self.assertEqual(editar.status_code, 403)
        cliente.refresh_from_db()
        self.assertNotEqual(cliente.nome, "Alterado")

    def test_cliente_final_nao_acessa_fichas_de_outros(self):
        cliente = ClienteFactory()
        self.client.force_login(self.usuarios["cliente"])
        resposta = self.client.get(
            reverse("customers:cliente_detalhe", args=[cliente.pk])
        )
        self.assertEqual(resposta.status_code, 403)

    def test_whatsapp_url_montada_do_telefone(self):
        cliente = ClienteFactory(telefone="(75) 98888-1234")
        self.assertEqual(
            cliente.whatsapp_url, "https://wa.me/5575988881234"
        )

    def test_whatsapp_vazio_sem_telefone(self):
        cliente = ClienteFactory(telefone="")
        self.assertEqual(cliente.whatsapp_url, "")
