"""Cobertura das decisões de identidade/vínculo (R4/R5/R10)."""

import hashlib
from datetime import timedelta

from django.contrib.auth.models import AnonymousUser
from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404
from django.test import RequestFactory, TestCase
from django.utils import timezone

from accounts.models import Usuario
from core.models import LogAuditoria
from customers.factories import ClienteFactory
from customers.models import VinculoClienteToken
from customers.services import (
    SALT_VINCULO,
    obter_token_vinculo,
    revisar_vinculo_cliente,
    solicitar_vinculo_cliente,
)

DOC = "52998224725"


class SolicitacaoVinculoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = Usuario.objects.create_user(
            username="solicitante",
            email="solicitante@example.com",
            password="senha-forte-123",
        )

    def _request(self, usuario=None):
        request = RequestFactory().post("/accounts/vincular-cliente/")
        request.user = usuario or self.usuario
        return request

    def _solicitar(self, usuario=None, documento=DOC):
        return solicitar_vinculo_cliente(
            usuario=usuario or self.usuario,
            documento=documento,
            request=self._request(usuario),
        )

    def test_anonimo_sem_email_verificado_ou_vinculo_nao_recebe_prova(self):
        self.assertFalse(
            solicitar_vinculo_cliente(
                usuario=AnonymousUser(),
                documento=DOC,
                request=self._request(AnonymousUser()),
            )
        )
        sem_email = Usuario.objects.create_user(
            username="sem-email", password="senha-forte-123"
        )
        self.assertFalse(self._solicitar(usuario=sem_email))
        ClienteFactory(
            documento=DOC,
            email=self.usuario.email,
            vinculo_verificado=True,
        )
        self.assertFalse(self._solicitar())

    def test_cliente_de_outro_usuario_nao_recebe_prova(self):
        outro = Usuario.objects.create_user(
            username="outro-doc", password="senha-forte-123"
        )
        ClienteFactory(
            documento=DOC,
            email=self.usuario.email,
            usuario=outro,
        )
        self.assertFalse(self._solicitar())

    def test_usuario_ja_vinculado_a_outro_cliente_nao_recebe_prova(self):
        ClienteFactory(usuario=self.usuario, vinculo_verificado=True)
        ClienteFactory(documento=DOC, email=self.usuario.email)
        self.assertFalse(self._solicitar())

    def test_email_divergente_nao_recebe_prova(self):
        ClienteFactory(documento=DOC, email="outro@example.com")
        self.assertFalse(self._solicitar())

    def test_solicitacao_valida_cria_token_e_envia_email(self):
        ClienteFactory(documento=DOC, email=self.usuario.email)
        self.assertTrue(self._solicitar())
        self.assertEqual(
            VinculoClienteToken.objects.filter(
                usuario=self.usuario
            ).count(),
            1,
        )


class TokenVinculoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = Usuario.objects.create_user(
            username="token-user",
            email="token@example.com",
            password="senha-forte-123",
        )
        cls.outro = Usuario.objects.create_user(
            username="token-outro",
            email="outro-token@example.com",
            password="senha-forte-123",
        )
        cls.cliente = ClienteFactory(
            documento=DOC, email=cls.usuario.email
        )

    def _prova(self, usuario=None):
        nonce = "nonce-de-teste"
        VinculoClienteToken.objects.create(
            cliente=self.cliente,
            usuario=usuario or self.usuario,
            nonce_hash=hashlib.sha256(nonce.encode()).hexdigest(),
            email_hash=hashlib.sha256(
                self.cliente.email.casefold().encode()
            ).hexdigest(),
            expira_em=timezone.now() + timedelta(hours=1),
        )
        return signing.dumps({"nonce": nonce}, salt=SALT_VINCULO)

    def test_assinatura_invalida_e_404(self):
        with self.assertRaises(Http404):
            obter_token_vinculo("invalido", self.usuario)

    def test_nonce_vazio_e_404(self):
        token = signing.dumps({}, salt=SALT_VINCULO)
        with self.assertRaises(Http404):
            obter_token_vinculo(token, self.usuario)

    def test_token_de_outro_usuario_e_403(self):
        with self.assertRaises(PermissionDenied):
            obter_token_vinculo(self._prova(), self.outro)

    def test_cliente_ja_vinculado_a_outro_e_403(self):
        self.cliente.usuario = self.outro
        self.cliente.save(update_fields=["usuario"])
        with self.assertRaises(PermissionDenied):
            obter_token_vinculo(self._prova(), self.usuario)

    def test_usuario_com_outro_cliente_e_403(self):
        ClienteFactory(usuario=self.usuario)
        with self.assertRaises(PermissionDenied):
            obter_token_vinculo(self._prova(), self.usuario)


class RevisaoAdministrativaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = Usuario.objects.create_user(
            username="revisao", password="senha-forte-123"
        )
        cls.cliente = ClienteFactory(
            documento=DOC, email="revisao@example.com", usuario=cls.usuario
        )

    def test_exige_justificativa(self):
        with self.assertRaises(ValidationError):
            revisar_vinculo_cliente(
                cliente=self.cliente,
                verificado=False,
                justificativa="",
                request=None,
            )

    def test_verificar_sem_usuario_falha(self):
        cliente = ClienteFactory(documento="11144477735")
        with self.assertRaises(ValidationError):
            revisar_vinculo_cliente(
                cliente=cliente,
                verificado=True,
                justificativa="Tentativa inválida",
                request=None,
            )

    def test_revogar_desvincula_revoga_tokens_e_audita(self):
        self.cliente.vinculo_verificado = True
        self.cliente.save(update_fields=["vinculo_verificado"])
        VinculoClienteToken.objects.create(
            cliente=self.cliente,
            usuario=self.usuario,
            nonce_hash="a" * 64,
            email_hash="b" * 64,
            expira_em=timezone.now(),
        )

        revisar_vinculo_cliente(
            cliente=self.cliente,
            verificado=False,
            justificativa="Suspeita de fraude",
            request=None,
        )

        self.cliente.refresh_from_db()
        self.assertFalse(self.cliente.vinculo_verificado)
        self.assertIsNone(self.cliente.usuario)
        self.assertTrue(
            VinculoClienteToken.objects.filter(
                cliente=self.cliente, revogado_em__isnull=False
            ).exists()
        )
        self.assertTrue(
            LogAuditoria.objects.filter(
                acao="cliente.vinculo_revisado_admin",
                objeto_id=str(self.cliente.pk),
            ).exists()
        )
