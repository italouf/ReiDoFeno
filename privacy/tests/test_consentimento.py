
from django.test import TestCase
from django.urls import reverse

from customers.factories import ClienteFactory
from customers.models import Cliente
from privacy.models import ConsentimentoLGPD
from privacy.services import (
    registrar_consentimento,
    tem_consentimento_ativo,
)
from sales.tests.helpers import criar_produto_com_estoque, fluxo_checkout


class PoliticaPublicaTests(TestCase):
    def test_acesso_anonimo_as_paginas(self):
        for url in (
            reverse("privacy:politica"),
            reverse("privacy:termos"),
        ):
            resposta = self.client.get(url)
            self.assertEqual(resposta.status_code, 200, url)


class ConsentimentoTests(TestCase):
    def test_checkout_registra_consentimento_de_compras_com_ip(self):
        fluxo_checkout(self.client, quantidade=1)
        cliente = Cliente.objects.get(documento="52998224725")
        consentimentos = ConsentimentoLGPD.objects.filter(
            cliente=cliente,
            finalidade=ConsentimentoLGPD.Finalidade.COMPRAS,
        )
        self.assertEqual(consentimentos.count(), 1)
        self.assertTrue(consentimentos.first().aceito)
        self.assertIsNotNone(consentimentos.first().ip)

    def test_marketing_somente_quando_marcado(self):
        produto, _unidade = criar_produto_com_estoque()
        self.client.post(
            reverse("sales:adicionar"),
            {"produto_id": produto.pk, "quantidade": "1"},
        )
        from core.models import Unidade

        self.client.post(
            reverse("sales:checkout"),
            {
                "nome": "Ana", "documento": "111.444.777-35",
                "email": "ana@example.com", "modalidade": "retirada",
                "unidade": Unidade.objects.get().pk,
                "aceita_marketing": "on",
            },
        )
        cliente = Cliente.objects.get(documento="11144477735")
        self.assertTrue(
            tem_consentimento_ativo(cliente, ConsentimentoLGPD.Finalidade.MARKETING)
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


