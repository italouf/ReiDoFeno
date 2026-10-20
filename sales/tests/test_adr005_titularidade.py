"""ADR-005: titularidade sem vazamento de histórico e exportação."""

import pytest
from django.core.exceptions import PermissionDenied
from django.test import TestCase
from django.urls import reverse

from accounts.models import Usuario
from customers.factories import ClienteFactory
from privacy.models import SolicitacaoTitular
from privacy.services import exportar_dados_do_titular
from sales.factories import ItemPedidoFactory, PedidoFactory
from sales.models import Pedido


class TitularidadeSemVazamentoTests(TestCase):
    def setUp(self):
        self.user = Usuario.objects.create_user(
            username="titular-adr005", password="senha-forte-123"
        )
        self.client.force_login(self.user)

    def _cliente(self, **kwargs):
        return ClienteFactory(usuario=self.user, **kwargs)

    def _pedido(self, cliente, **kwargs):
        dados = {"cliente": cliente, "identidade_verificada": True}
        dados.update(kwargs)
        pedido = PedidoFactory(**dados)
        ItemPedidoFactory(pedido=pedido)
        return pedido

    def test_meus_pedidos_somente_vinculo_verificado(self):
        cliente_sem_vinculo = self._cliente(vinculo_verificado=False)
        self._pedido(cliente_sem_vinculo)

        response = self.client.get(reverse("sales:meus_pedidos"))

        assert response.status_code == 200
        assert list(response.context["pedidos"]) == []
        assert response.context["vinculo_pendente"] is True

    def test_meus_pedidos_cliente_comprovado_ve_proprios(self):
        cliente = self._cliente(vinculo_verificado=True)
        pedido = self._pedido(cliente)

        response = self.client.get(reverse("sales:meus_pedidos"))

        assert list(response.context["pedidos"]) == [pedido]
        assert response.context["vinculo_pendente"] is False

    def test_meus_pedidos_nao_mostra_pedido_de_outro_cliente(self):
        outro_user = Usuario.objects.create_user(
            username="outro-adr005", password="senha-forte-123"
        )
        outro_cliente = ClienteFactory(
            usuario=outro_user, vinculo_verificado=True
        )
        self._pedido(outro_cliente)

        response = self.client.get(reverse("sales:meus_pedidos"))

        assert list(response.context["pedidos"]) == []

    def test_meus_pedidos_nao_mostra_pedido_nao_verificado(self):
        cliente = self._cliente(vinculo_verificado=True)
        self._pedido(cliente, identidade_verificada=False)

        response = self.client.get(reverse("sales:meus_pedidos"))

        assert list(response.context["pedidos"]) == []

    def test_exportacao_bloqueada_sem_vinculo(self):
        self._cliente(vinculo_verificado=False)

        response = self.client.post(
            reverse("privacy:nova_solicitacao"),
            {"tipo": SolicitacaoTitular.Tipo.EXPORTACAO},
        )

        assert response.status_code == 403
        assert not SolicitacaoTitular.objects.filter(
            tipo=SolicitacaoTitular.Tipo.EXPORTACAO
        ).exists()

    def test_exportacao_service_bloqueada_sem_vinculo(self):
        cliente = self._cliente(vinculo_verificado=False)
        with pytest.raises(PermissionDenied):
            exportar_dados_do_titular(cliente)

    def test_exportacao_verificada_funciona(self):
        cliente = self._cliente(vinculo_verificado=True)
        self._pedido(cliente)

        response = self.client.post(
            reverse("privacy:nova_solicitacao"),
            {"tipo": SolicitacaoTitular.Tipo.EXPORTACAO},
        )

        assert response.status_code == 200
        assert response["Content-Type"] == "application/json"
        solicitacao = SolicitacaoTitular.objects.get(
            cliente=cliente, tipo=SolicitacaoTitular.Tipo.EXPORTACAO
        )
        assert solicitacao.status == SolicitacaoTitular.Status.CONCLUIDA

    def test_meus_pedidos_mostra_mensagem_orientativa(self):
        self._cliente(vinculo_verificado=False)

        response = self.client.get(reverse("sales:meus_pedidos"))

        assert response.status_code == 200
        assert "vínculo" in response.content.decode().lower()

    def test_pedido_de_outro_cliente_nao_aparece_nem_no_conteudo(self):
        outro_user = Usuario.objects.create_user(
            username="alheio-adr005", password="senha-forte-123"
        )
        outro_cliente = ClienteFactory(
            usuario=outro_user, vinculo_verificado=True
        )
        alheio = self._pedido(outro_cliente)

        response = self.client.get(reverse("sales:meus_pedidos"))

        assert alheio.numero not in response.content.decode()
        assert Pedido.objects.filter(pk=alheio.pk).exists()
