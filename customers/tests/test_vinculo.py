"""SEC-02: vínculo cliente/usuário somente após comprovação por e-mail."""

import re
from datetime import timedelta
from unittest import mock

from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Usuario
from core.models import LogAuditoria
from customers.factories import ClienteFactory
from customers.models import VinculoClienteToken
from sales.factories import PedidoFactory

DOCUMENTO = "52998224725"


class VinculoClienteTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.senha = "senha-forte-123"
        cls.usuario = Usuario.objects.create_user(
            username="titular",
            email="titular@example.com",
            password=cls.senha,
        )
        cls.outro_usuario = Usuario.objects.create_user(
            username="outro",
            email="outro@example.com",
            password=cls.senha,
        )

    def _criar_cliente(self, **overrides):
        dados = {
            "documento": DOCUMENTO,
            "email": self.usuario.email,
            "usuario": None,
        }
        dados.update(overrides)
        return ClienteFactory(**dados)

    def _solicitar(self):
        return self.client.post(
            reverse("accounts:vincular_cliente"),
            {"documento": DOCUMENTO},
        )

    @staticmethod
    def _link_do_email():
        corpo = mail.outbox[-1].body
        caminho = re.search(
            r"(/accounts/vincular-cliente/confirmar/[^\s]+)", corpo
        )
        assert caminho is not None, corpo
        return caminho.group(1)

    def test_solicitacao_envia_email_e_nao_vincula_imediatamente(self):
        cliente = self._criar_cliente()
        self.client.force_login(self.usuario)

        resposta = self._solicitar()

        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        cliente.refresh_from_db()
        self.assertIsNone(cliente.usuario)
        self.assertIn("vínculo", mail.outbox[0].subject.lower())

    def test_confirmacao_por_email_vincula_e_audita(self):
        cliente = self._criar_cliente()
        pedido = PedidoFactory(
            cliente=cliente,
            usuario_criador=self.usuario,
            identidade_verificada=False,
        )
        self.client.force_login(self.usuario)
        self._solicitar()
        link = self._link_do_email()

        previa = self.client.get(link)
        self.assertEqual(previa.status_code, 200)
        cliente.refresh_from_db()
        self.assertIsNone(cliente.usuario)

        resposta = self.client.post(link)

        self.assertEqual(resposta.status_code, 302)
        cliente.refresh_from_db()
        pedido.refresh_from_db()
        self.assertEqual(cliente.usuario, self.usuario)
        self.assertTrue(cliente.vinculo_verificado)
        self.assertTrue(pedido.identidade_verificada)
        log = LogAuditoria.objects.filter(
            acao="cliente.vinculo_confirmado",
            objeto_id=str(cliente.pk),
        ).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.usuario, self.usuario)

    def test_get_nao_consome_a_prova(self):
        cliente = self._criar_cliente()
        self.client.force_login(self.usuario)
        self._solicitar()
        link = self._link_do_email()

        for _ in range(2):
            self.assertEqual(self.client.get(link).status_code, 200)
        cliente.refresh_from_db()
        self.assertIsNone(cliente.usuario)

        self.assertEqual(self.client.post(link).status_code, 302)
        cliente.refresh_from_db()
        self.assertEqual(cliente.usuario, self.usuario)

    def test_prova_e_de_uso_unico(self):
        cliente = self._criar_cliente()
        self.client.force_login(self.usuario)
        self._solicitar()
        link = self._link_do_email()

        self.assertEqual(self.client.post(link).status_code, 302)
        self.assertEqual(self.client.post(link).status_code, 404)
        cliente.refresh_from_db()
        self.assertEqual(cliente.usuario, self.usuario)

    def test_email_diferente_nao_recebe_link(self):
        cliente = self._criar_cliente(email="outro@example.com")
        self.client.force_login(self.usuario)

        resposta = self._solicitar()

        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(len(mail.outbox), 0)
        cliente.refresh_from_db()
        self.assertIsNone(cliente.usuario)

    def test_documento_inexistente_tem_resposta_generica(self):
        self.client.force_login(self.usuario)

        resposta = self._solicitar()

        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(len(mail.outbox), 0)

    def test_cliente_ja_vinculado_nao_recebe_novo_link(self):
        cliente = self._criar_cliente(usuario=self.outro_usuario)
        self.client.force_login(self.usuario)

        self._solicitar()

        self.assertEqual(len(mail.outbox), 0)
        cliente.refresh_from_db()
        self.assertEqual(cliente.usuario, self.outro_usuario)

    def test_link_nao_pode_ser_usado_por_outro_usuario(self):
        cliente = self._criar_cliente()
        self.client.force_login(self.usuario)
        self._solicitar()
        link = self._link_do_email()

        self.client.force_login(self.outro_usuario)
        resposta = self.client.get(link)

        self.assertEqual(resposta.status_code, 403)
        cliente.refresh_from_db()
        self.assertIsNone(cliente.usuario)

    def test_link_expirado_e_rejeitado(self):
        cliente = self._criar_cliente()
        self.client.force_login(self.usuario)
        self._solicitar()
        link = self._link_do_email()
        VinculoClienteToken.objects.filter(cliente=cliente).update(
            expira_em=timezone.now() - timedelta(minutes=1)
        )

        resposta = self.client.get(link)

        self.assertEqual(resposta.status_code, 404)
        cliente.refresh_from_db()
        self.assertIsNone(cliente.usuario)

    def test_email_alterado_invalida_prova(self):
        cliente = self._criar_cliente()
        self.client.force_login(self.usuario)
        self._solicitar()
        link = self._link_do_email()
        cliente.email = "novo-titular@example.com"
        cliente.save(update_fields=["email"])

        resposta = self.client.get(link)

        self.assertEqual(resposta.status_code, 403)
        cliente.refresh_from_db()
        self.assertIsNone(cliente.usuario)

    def test_email_alterado_e_restaurado_nao_ressuscita_prova(self):
        cliente = self._criar_cliente()
        email_original = cliente.email
        self.client.force_login(self.usuario)
        self._solicitar()
        link = self._link_do_email()
        cliente.email = "intermediario@example.com"
        cliente.save(update_fields=["email"])
        cliente.email = email_original
        cliente.save(update_fields=["email"])

        resposta = self.client.get(link)

        self.assertEqual(resposta.status_code, 403)
        cliente.refresh_from_db()
        self.assertIsNone(cliente.usuario)

    def test_falha_na_auditoria_reverte_vinculo(self):
        cliente = self._criar_cliente()
        self.client.force_login(self.usuario)
        self._solicitar()
        link = self._link_do_email()
        self.assertEqual(self.client.get(link).status_code, 200)

        with mock.patch(
            "customers.services.registrar_auditoria",
            side_effect=RuntimeError("auditoria indisponível"),
        ):
            with self.assertRaises(RuntimeError):
                self.client.post(link)

        cliente.refresh_from_db()
        self.assertIsNone(cliente.usuario)
        self.assertFalse(cliente.vinculo_verificado)

    def test_anonimo_e_redirecionado_para_login(self):
        resposta = self.client.get(reverse("accounts:vincular_cliente"))
        self.assertEqual(resposta.status_code, 302)
        self.assertIn(reverse("accounts:login"), resposta["Location"])

    def test_vinculo_pendente_nao_le_nem_edita_cadastro(self):
        cliente = self._criar_cliente(
            usuario=self.usuario, vinculo_verificado=False
        )
        self.client.force_login(self.usuario)

        leitura = self.client.get(
            reverse("customers:cliente_editar", args=[cliente.pk])
        )
        escrita = self.client.post(
            reverse("customers:cliente_editar", args=[cliente.pk]),
            {
                "nome": cliente.nome,
                "tipo_pessoa": cliente.tipo_pessoa,
                "documento": cliente.documento,
                "categoria": cliente.categoria,
                "telefone": cliente.telefone,
                "email": "atacante@example.com",
                "logradouro": "",
                "numero": "",
                "bairro": "",
                "cidade": "",
                "uf": "",
                "cep": "",
                "preferencia": "",
            },
        )

        self.assertEqual(leitura.status_code, 403)
        self.assertEqual(escrita.status_code, 403)
        cliente.refresh_from_db()
        self.assertEqual(cliente.email, self.usuario.email)

    def test_titular_verificado_troca_email_e_recupera_por_nova_prova(self):
        cliente = self._criar_cliente(
            usuario=self.usuario, vinculo_verificado=True
        )
        self.client.force_login(self.usuario)
        novo_email = "novo-titular@example.com"

        resposta = self.client.post(
            reverse("customers:cliente_editar", args=[cliente.pk]),
            {
                "nome": cliente.nome,
                "tipo_pessoa": cliente.tipo_pessoa,
                "documento": cliente.documento,
                "categoria": cliente.categoria,
                "telefone": cliente.telefone,
                "email": novo_email,
                "logradouro": "",
                "numero": "",
                "bairro": "",
                "cidade": "",
                "uf": "",
                "cep": "",
                "preferencia": "",
            },
        )

        self.assertEqual(resposta.status_code, 302)
        cliente.refresh_from_db()
        self.assertFalse(cliente.vinculo_verificado)
        self.assertEqual(cliente.email, novo_email)

        self._solicitar()
        self.assertEqual(mail.outbox[-1].to, [novo_email])
        link = self._link_do_email()
        self.assertEqual(self.client.post(link).status_code, 302)
        cliente.refresh_from_db()
        self.assertTrue(cliente.vinculo_verificado)
