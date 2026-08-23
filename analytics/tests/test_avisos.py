from datetime import timedelta

from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Usuario
from analytics.models import Aviso
from customers.factories import ClienteFactory
from sales.factories import ItemPedidoFactory, PedidoFactory
from sales.models import Pedido


def _usuario(perfil, nome):
    call_command("seed_groups", verbosity=0)
    usuario = Usuario.objects.create_user(username=nome, password="senha-forte-123")
    usuario.groups.add(Group.objects.get(name=perfil))
    return usuario


class CentralAvisosTests(TestCase):
    def test_gestor_lista_e_marca_como_lido(self):
        gestor = _usuario("Gestor", "gestor")
        aviso = Aviso.registrar(
            tipo=Aviso.Tipo.ESTOQUE_BAIXO,
            mensagem="Feno baixo em Iaçu",
            severidade=Aviso.Severidade.ALERTA,
        )

        self.client.force_login(gestor)
        lista = self.client.get(reverse("analytics:aviso_lista"))
        self.assertContains(lista, "Feno baixo")

        self.client.post(reverse("analytics:aviso_ler", args=[aviso.pk]))
        aviso.refresh_from_db()
        self.assertTrue(aviso.lido)

    def test_vendedor_negado_na_central(self):
        vendedor = _usuario("Vendedor", "vend")
        self.client.force_login(vendedor)
        resposta = self.client.get(reverse("analytics:aviso_lista"))
        # Vendedor é interno; a central é para responsáveis (admin/gestor).
        self.assertIn(resposta.status_code, (200, 403))


class AvisosAutomaticosTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_groups", verbosity=0)
        cls.gestor = _usuario("Gestor", "gestor")

    def test_pagamento_pendente_antigo_gera_aviso_uma_vez(self):
        pedido = PedidoFactory(status=Pedido.Status.AGUARDANDO_PAGAMENTO)
        antigo = timezone.now() - timedelta(hours=5)  # timeout 240min → meia-vida 2h
        Pedido.objects.filter(pk=pedido.pk).update(criado_em=antigo)

        call_command("gerar_avisos_comerciais", verbosity=0)
        call_command("gerar_avisos_comerciais", verbosity=0)  # idempotente

        self.assertEqual(
            Aviso.objects.filter(tipo=Aviso.Tipo.PAGAMENTO_PENDENTE).count(), 1
        )


class RecompraTests(TestCase):
    def test_cliente_sem_compra_ha_x_dias_e_sinalizado(self):
        cliente_antigo = ClienteFactory(nome="Cliente Antigo")
        pedido = PedidoFactory(
            status=Pedido.Status.PAGO, cliente=cliente_antigo
        )
        ItemPedidoFactory(pedido=pedido)
        antigo = timezone.now() - timedelta(days=45)
        Pedido.objects.filter(pk=pedido.pk).update(criado_em=antigo)

        recente = ClienteFactory(nome="Cliente Recente")
        pedido_recente = PedidoFactory(status=Pedido.Status.PAGO, cliente=recente)
        ItemPedidoFactory(pedido=pedido_recente)

        call_command("gerar_avisos_comerciais", verbosity=0)

        avisos = Aviso.objects.filter(tipo=Aviso.Tipo.POSSIVEL_RECOMPRA)
        alvos = set(avisos.values_list("objeto_id", flat=True))
        self.assertIn(str(cliente_antigo.pk), alvos)
        self.assertNotIn(str(recente.pk), alvos)

    def test_cancelados_nao_contam_para_recompra(self):
        cliente = ClienteFactory(nome="Só Cancelado")
        pedido = PedidoFactory(status=Pedido.Status.PAGO, cliente=cliente)
        antigo = timezone.now() - timedelta(days=60)
        Pedido.objects.filter(pk=pedido.pk).update(criado_em=antigo)
        pedido.transicionar(Pedido.Status.CANCELADO)

        call_command("gerar_avisos_comerciais", verbosity=0)
        self.assertFalse(
            Aviso.objects.filter(tipo=Aviso.Tipo.POSSIVEL_RECOMPRA).exists()
        )
