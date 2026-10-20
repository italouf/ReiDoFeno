
from django.test import TestCase
from django.urls import reverse

from customers.factories import ClienteFactory
from customers.models import Cliente
from privacy.models import ConsentimentoLGPD
from privacy.services import (
    registrar_consentimento,
    tem_consentimento_ativo,
)
from sales.tests.helpers import fluxo_checkout


class PoliticaPublicaTests(TestCase):
    def test_acesso_anonimo_as_paginas(self):
        for url in (
            reverse("privacy:politica"),
            reverse("privacy:termos"),
        ):
            resposta = self.client.get(url)
            self.assertEqual(resposta.status_code, 200, url)


class ConsentimentoTests(TestCase):
    def test_checkout_anonimo_registra_consentimento_no_pedido(self):
        pedido = fluxo_checkout(self.client, quantidade=1)
        cliente = Cliente.objects.get(documento="52998224725")

        self.assertTrue(pedido.consentimento_compras)
        self.assertFalse(pedido.identidade_verificada)
        self.assertEqual(
            ConsentimentoLGPD.objects.filter(
                cliente=cliente,
                finalidade=ConsentimentoLGPD.Finalidade.COMPRAS,
            ).count(),
            0,
        )

    def test_marketing_anonimo_fica_no_pedido_nao_no_cadastro(self):
        pedido = fluxo_checkout(
            self.client,
            quantidade=1,
            dados_extra={
                "nome": "Ana",
                "documento": "111.444.777-35",
                "email": "ana@example.com",
                "aceita_marketing": "on",
            },
        )
        cliente = Cliente.objects.get(documento="11144477735")

        self.assertTrue(pedido.consentimento_marketing)
        self.assertFalse(
            tem_consentimento_ativo(
                cliente, ConsentimentoLGPD.Finalidade.MARKETING
            )
        )

    def test_revogacao_interrompe_uso_da_finalidade(self):
        cliente = ClienteFactory()
        registrar_consentimento(cliente=cliente, finalidade="marketing")
        self.assertTrue(
            tem_consentimento_ativo(cliente, ConsentimentoLGPD.Finalidade.MARKETING)
        )

        registrar_consentimento(
            cliente=cliente, finalidade="marketing", aceito=False
        )
        self.assertFalse(
            tem_consentimento_ativo(cliente, ConsentimentoLGPD.Finalidade.MARKETING)
        )


