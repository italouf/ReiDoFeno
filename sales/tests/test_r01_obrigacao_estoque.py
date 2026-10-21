"""R01: obrigação persistente impede avanço sem baixa de estoque."""

from decimal import Decimal

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase

from accounts.models import Usuario
from catalog.factories import ProdutoFactory
from core.factories import UnidadeFactory
from sales.factories import ItemPedidoFactory, PagamentoFactory, PedidoFactory
from sales.models import ObrigacaoEstoquePedido, Pagamento, Pedido
from sales.services import (
    marcar_pagamento_aprovado,
    resolver_pendencia_estoque,
)
from stock.factories import EstoqueFactory
from stock.models import Estoque, MovimentoEstoque, ReservaEstoque
from stock.services import registrar_movimento, reservar


class ObrigacaoEstoqueTests(TestCase):
    def setUp(self):
        self.usuario = Usuario.objects.create_user(
            username="gestor-r01",
            password="senha-forte-123",
            is_superuser=True,
        )
        self.produto = ProdutoFactory()
        self.unidade = UnidadeFactory()
        self.estoque = EstoqueFactory(
            produto=self.produto, unidade=self.unidade, quantidade="10.00"
        )
        self.pedido_b = PedidoFactory(
            unidade=self.unidade,
            status=Pedido.Status.AGUARDANDO_PAGAMENTO,
            status_financeiro=Pedido.StatusFinanceiro.PENDENTE,
        )
        self.item_b = ItemPedidoFactory(
            pedido=self.pedido_b,
            produto=self.produto,
            quantidade=Decimal("10.00"),
        )
        self.reserva_b = reservar(
            produto=self.produto,
            unidade=self.unidade,
            quantidade=Decimal("10.00"),
            pedido=self.pedido_b,
            item_pedido=self.item_b,
        )

    def _pedido_legado(self, quantidade="3.00"):
        pedido = PedidoFactory(
            unidade=self.unidade,
            status=Pedido.Status.AGUARDANDO_PAGAMENTO,
            status_financeiro=Pedido.StatusFinanceiro.PENDENTE,
        )
        item = ItemPedidoFactory(
            pedido=pedido,
            produto=self.produto,
            quantidade=Decimal(quantidade),
        )
        return pedido, item

    def _obrigacao(self, pedido):
        return ObrigacaoEstoquePedido.objects.get(
            pedido=pedido, produto=self.produto, unidade=self.unidade
        )

    def test_pendencia_bloqueia_avanco_e_resolucao_libera(self):
        pedido_a, _item = self._pedido_legado("3.00")

        marcar_pagamento_aprovado(pedido_a, id_externo="pay-r01")

        pedido_a.refresh_from_db()
        obrigacao = self._obrigacao(pedido_a)
        self.assertEqual(obrigacao.status, ObrigacaoEstoquePedido.Status.PENDENTE)
        self.assertEqual(obrigacao.quantidade_devida, Decimal("3.00"))
        self.assertEqual(obrigacao.quantidade_baixada, Decimal("0.00"))
        with pytest.raises(ValidationError):
            pedido_a.transicionar(Pedido.Status.EM_SEPARACAO)

        registrar_movimento(
            produto=self.produto,
            unidade=self.unidade,
            tipo=MovimentoEstoque.Tipo.ENTRADA,
            delta=Decimal("3.00"),
            motivo="reposição para resolver pendência",
        )
        resolver_pendencia_estoque(
            obrigacao,
            usuario=self.usuario,
            justificativa="estoque reposto e conferido",
        )

        obrigacao.refresh_from_db()
        pedido_a.refresh_from_db()
        self.assertEqual(
            obrigacao.status, ObrigacaoEstoquePedido.Status.RESOLVIDA
        )
        self.assertEqual(obrigacao.quantidade_baixada, Decimal("3.00"))
        estoque = Estoque.objects.get(produto=self.produto, unidade=self.unidade)
        self.assertEqual(estoque.quantidade, Decimal("10.00"))
        self.assertEqual(estoque.quantidade_bloqueada, Decimal("10.00"))
        self.reserva_b.refresh_from_db()
        self.assertEqual(
            self.reserva_b.status, ReservaEstoque.Status.ATIVA
        )
        pedido_a.transicionar(Pedido.Status.EM_SEPARACAO)

    def test_resolucao_e_idempotente(self):
        pedido_a, _item = self._pedido_legado("3.00")
        marcar_pagamento_aprovado(pedido_a, id_externo="pay-r01-idem")
        obrigacao = self._obrigacao(pedido_a)
        registrar_movimento(
            produto=self.produto,
            unidade=self.unidade,
            tipo=MovimentoEstoque.Tipo.ENTRADA,
            delta=Decimal("3.00"),
            motivo="reposição",
        )
        resolver_pendencia_estoque(
            obrigacao,
            usuario=self.usuario,
            justificativa="primeira resolução",
        )
        movimentos = MovimentoEstoque.objects.count()
        resolver_pendencia_estoque(
            obrigacao,
            usuario=self.usuario,
            justificativa="segunda resolução",
        )
        self.assertEqual(MovimentoEstoque.objects.count(), movimentos)

    def test_multiplos_produtos_bloqueiam_ate_todos_resolverem(self):
        produto1 = ProdutoFactory()
        EstoqueFactory(
            produto=produto1, unidade=self.unidade, quantidade="5.00"
        )
        produto2 = ProdutoFactory()
        EstoqueFactory(
            produto=produto2, unidade=self.unidade, quantidade="0.00"
        )
        pedido = PedidoFactory(
            unidade=self.unidade,
            status=Pedido.Status.AGUARDANDO_PAGAMENTO,
            status_financeiro=Pedido.StatusFinanceiro.PENDENTE,
        )
        ItemPedidoFactory(
            pedido=pedido,
            produto=produto1,
            quantidade=Decimal("1.00"),
        )
        ItemPedidoFactory(
            pedido=pedido,
            produto=produto2,
            quantidade=Decimal("2.00"),
        )
        marcar_pagamento_aprovado(pedido, id_externo="pay-r01-multi")
        with pytest.raises(ValidationError):
            pedido.transicionar(Pedido.Status.EM_SEPARACAO)

        registrar_movimento(
            produto=produto2,
            unidade=self.unidade,
            tipo=MovimentoEstoque.Tipo.ENTRADA,
            delta=Decimal("2.00"),
            motivo="reposição produto 2",
        )
        obrigacao2 = ObrigacaoEstoquePedido.objects.get(
            pedido=pedido, produto=produto2, unidade=self.unidade
        )
        resolver_pendencia_estoque(
            obrigacao2,
            usuario=self.usuario,
            justificativa="reposição do segundo produto",
        )
        pedido.refresh_from_db()
        pedido.transicionar(Pedido.Status.EM_SEPARACAO)

    def test_cancelamento_cancela_obrigacao_pendente(self):
        from sales.services import cancelar_pedido

        pedido_a, _item = self._pedido_legado("3.00")
        ObrigacaoEstoquePedido.objects.create(
            pedido=pedido_a,
            produto=self.produto,
            unidade=self.unidade,
            quantidade_devida=Decimal("3.00"),
            status=ObrigacaoEstoquePedido.Status.PENDENTE,
        )
        cancelar_pedido(pedido_a, permitir_pago=True)
        obrigacao = self._obrigacao(pedido_a)
        self.assertEqual(
            obrigacao.status, ObrigacaoEstoquePedido.Status.CANCELADA
        )

    def _pedido_pago_com_pendencia(self, quantidade="3.00"):
        pedido, _item = self._pedido_legado(quantidade)
        pedido.definir_status_financeiro(
            Pedido.StatusFinanceiro.PAGO, motivo="teste"
        )
        pedido.financeiro_conciliado = True
        pedido.save(update_fields=["financeiro_conciliado"])
        obrigacao = ObrigacaoEstoquePedido.objects.create(
            pedido=pedido,
            produto=self.produto,
            unidade=self.unidade,
            quantidade_devida=Decimal(quantidade),
            status=ObrigacaoEstoquePedido.Status.PENDENTE,
        )
        return pedido, obrigacao

    def test_resolver_rejeita_unidade_divergente(self):
        pedido, _obrigacao = self._pedido_pago_com_pendencia()
        outra = UnidadeFactory(nome="Outra unidade")
        EstoqueFactory(
            produto=self.produto, unidade=outra, quantidade="10.00"
        )
        obrigacao_errada = ObrigacaoEstoquePedido.objects.create(
            pedido=pedido,
            produto=self.produto,
            unidade=outra,
            quantidade_devida=Decimal("3.00"),
            status=ObrigacaoEstoquePedido.Status.PENDENTE,
        )
        with pytest.raises(ValidationError):
            resolver_pendencia_estoque(
                obrigacao_errada,
                usuario=self.usuario,
                justificativa="tentativa inválida",
            )
        self.assertFalse(
            MovimentoEstoque.objects.filter(
                produto=self.produto, unidade=outra
            ).exists()
        )

    def test_resolver_rejeita_pedido_cancelado_pago(self):
        pedido, obrigacao = self._pedido_pago_com_pendencia()
        pedido.status = Pedido.Status.CANCELADO
        pedido.save(update_fields=["status"])
        with pytest.raises(ValidationError):
            resolver_pendencia_estoque(
                obrigacao,
                usuario=self.usuario,
                justificativa="pedido cancelado",
            )
        self.assertFalse(
            MovimentoEstoque.objects.filter(produto=self.produto).exists()
        )

    def test_resolver_rejeita_produto_fora_do_pedido(self):
        pedido, _obrigacao = self._pedido_pago_com_pendencia()
        outro_produto = ProdutoFactory(nome="Produto fora do pedido")
        EstoqueFactory(
            produto=outro_produto, unidade=self.unidade, quantidade="10.00"
        )
        obrigacao_errada = ObrigacaoEstoquePedido.objects.create(
            pedido=pedido,
            produto=outro_produto,
            unidade=self.unidade,
            quantidade_devida=Decimal("3.00"),
            status=ObrigacaoEstoquePedido.Status.PENDENTE,
        )
        with pytest.raises(ValidationError):
            resolver_pendencia_estoque(
                obrigacao_errada,
                usuario=self.usuario,
                justificativa="produto inválido",
            )
        self.assertFalse(
            MovimentoEstoque.objects.filter(produto=outro_produto).exists()
        )

    def test_resolver_rejeita_obrigacao_resolvida_com_reserva_ativa(self):
        produto = ProdutoFactory()
        unidade = UnidadeFactory(nome="Unidade reserva órfã")
        EstoqueFactory(
            produto=produto, unidade=unidade, quantidade="10.00"
        )
        pedido = PedidoFactory(
            unidade=unidade,
            status=Pedido.Status.AGUARDANDO_PAGAMENTO,
            status_financeiro=Pedido.StatusFinanceiro.PENDENTE,
        )
        item = ItemPedidoFactory(
            pedido=pedido, produto=produto, quantidade=Decimal("3.00")
        )
        reserva = reservar(
            produto=produto,
            unidade=unidade,
            quantidade=Decimal("3.00"),
            pedido=pedido,
            item_pedido=item,
        )
        pedido.definir_status_financeiro(
            Pedido.StatusFinanceiro.PAGO, motivo="teste"
        )
        pedido.financeiro_conciliado = True
        pedido.save(update_fields=["financeiro_conciliado"])
        obrigacao = ObrigacaoEstoquePedido.objects.create(
            pedido=pedido,
            produto=produto,
            unidade=unidade,
            quantidade_devida=Decimal("3.00"),
            quantidade_baixada=Decimal("3.00"),
            status=ObrigacaoEstoquePedido.Status.RESOLVIDA,
        )

        with pytest.raises(ValidationError):
            resolver_pendencia_estoque(
                obrigacao,
                usuario=self.usuario,
                justificativa="reserva órfã",
            )
        reserva.refresh_from_db()
        self.assertEqual(reserva.status, ReservaEstoque.Status.ATIVA)

    def test_aprovacao_repetida_libera_reserva_orfa_de_obrigacao_resolvida(self):
        produto = ProdutoFactory()
        unidade = UnidadeFactory(nome="Unidade T02-B")
        EstoqueFactory(
            produto=produto, unidade=unidade, quantidade="10.00"
        )
        pedido = PedidoFactory(
            unidade=unidade,
            status=Pedido.Status.AGUARDANDO_PAGAMENTO,
            status_financeiro=Pedido.StatusFinanceiro.PENDENTE,
        )
        item = ItemPedidoFactory(
            pedido=pedido, produto=produto, quantidade=Decimal("3.00")
        )
        reserva = reservar(
            produto=produto,
            unidade=unidade,
            quantidade=Decimal("3.00"),
            pedido=pedido,
            item_pedido=item,
        )
        pedido.definir_status_financeiro(
            Pedido.StatusFinanceiro.PAGO, motivo="teste"
        )
        pedido.financeiro_conciliado = True
        pedido.save(update_fields=["financeiro_conciliado"])
        PagamentoFactory(
            pedido=pedido,
            status=Pagamento.Status.APROVADO,
            valor=Decimal("9.00"),
        )
        ObrigacaoEstoquePedido.objects.create(
            pedido=pedido,
            produto=produto,
            unidade=unidade,
            quantidade_devida=Decimal("3.00"),
            quantidade_baixada=Decimal("3.00"),
            status=ObrigacaoEstoquePedido.Status.RESOLVIDA,
        )

        marcar_pagamento_aprovado(pedido, id_externo="pay-t02-b-reparo")

        reserva.refresh_from_db()
        estoque = Estoque.objects.get(produto=produto, unidade=unidade)
        self.assertEqual(reserva.status, ReservaEstoque.Status.LIBERADA)
        self.assertEqual(estoque.quantidade_bloqueada, Decimal("0.00"))

    def test_resolver_rejeita_pedido_nao_pago_com_reserva_ativa(self):
        produto = ProdutoFactory()
        unidade = UnidadeFactory()
        EstoqueFactory(
            produto=produto, unidade=unidade, quantidade="10.00"
        )
        pedido = PedidoFactory(
            unidade=unidade,
            status=Pedido.Status.AGUARDANDO_PAGAMENTO,
            status_financeiro=Pedido.StatusFinanceiro.PENDENTE,
        )
        item = ItemPedidoFactory(
            pedido=pedido, produto=produto, quantidade=Decimal("3.00")
        )
        reserva = reservar(
            produto=produto,
            unidade=unidade,
            quantidade=Decimal("3.00"),
            pedido=pedido,
            item_pedido=item,
        )
        obrigacao = ObrigacaoEstoquePedido.objects.create(
            pedido=pedido,
            produto=produto,
            unidade=unidade,
            quantidade_devida=Decimal("3.00"),
            status=ObrigacaoEstoquePedido.Status.PENDENTE,
        )
        with pytest.raises(ValidationError):
            resolver_pendencia_estoque(
                obrigacao,
                usuario=self.usuario,
                justificativa="tentativa prematura",
            )
        reserva.refresh_from_db()
        estoque = Estoque.objects.get(produto=produto, unidade=unidade)
        self.assertEqual(reserva.status, ReservaEstoque.Status.ATIVA)
        self.assertEqual(estoque.quantidade_bloqueada, Decimal("3.00"))

    def test_resolver_exige_usuario_ativo_e_autorizado(self):
        _pedido, obrigacao = self._pedido_pago_com_pendencia()
        for usuario in (None,):
            with pytest.raises(PermissionDenied):
                resolver_pendencia_estoque(
                    obrigacao,
                    usuario=usuario,
                    justificativa="sem ator",
                )
        inativo = Usuario.objects.create_user(
            username="inativo-r01",
            password="senha-forte-123",
            is_active=False,
            is_superuser=True,
        )
        with pytest.raises(PermissionDenied):
            resolver_pendencia_estoque(
                obrigacao,
                usuario=inativo,
                justificativa="inativo",
            )
        sem_grupo = Usuario.objects.create_user(
            username="sem-grupo-r01", password="senha-forte-123"
        )
        with pytest.raises(PermissionDenied):
            resolver_pendencia_estoque(
                obrigacao,
                usuario=sem_grupo,
                justificativa="sem grupo",
            )

    def test_resolver_consome_reserva_ativa_do_mesmo_pedido(self):
        produto = ProdutoFactory()
        unidade = UnidadeFactory()
        EstoqueFactory(
            produto=produto, unidade=unidade, quantidade="10.00"
        )
        pedido = PedidoFactory(
            unidade=unidade,
            status=Pedido.Status.AGUARDANDO_PAGAMENTO,
            status_financeiro=Pedido.StatusFinanceiro.PENDENTE,
        )
        item = ItemPedidoFactory(
            pedido=pedido, produto=produto, quantidade=Decimal("3.00")
        )
        reserva = reservar(
            produto=produto,
            unidade=unidade,
            quantidade=Decimal("3.00"),
            pedido=pedido,
            item_pedido=item,
        )
        pedido.definir_status_financeiro(
            Pedido.StatusFinanceiro.PAGO, motivo="teste"
        )
        pedido.financeiro_conciliado = True
        pedido.save(update_fields=["financeiro_conciliado"])
        obrigacao = ObrigacaoEstoquePedido.objects.create(
            pedido=pedido,
            produto=produto,
            unidade=unidade,
            quantidade_devida=Decimal("3.00"),
            status=ObrigacaoEstoquePedido.Status.PENDENTE,
        )

        resolver_pendencia_estoque(
            obrigacao,
            usuario=self.usuario,
            justificativa="consumo de reserva ativa",
        )

        reserva.refresh_from_db()
        obrigacao.refresh_from_db()
        estoque = Estoque.objects.get(produto=produto, unidade=unidade)
        self.assertEqual(reserva.status, ReservaEstoque.Status.CONSUMIDA)
        self.assertEqual(estoque.quantidade, Decimal("7.00"))
        self.assertEqual(estoque.quantidade_bloqueada, Decimal("0.00"))
        self.assertEqual(
            obrigacao.status, ObrigacaoEstoquePedido.Status.RESOLVIDA
        )
        self.assertEqual(obrigacao.resolvido_por, self.usuario)
        from core.models import LogAuditoria

        log = LogAuditoria.objects.filter(
            acao="pedido.estoque_pendente_resolvido",
            objeto_id=str(pedido.pk),
        ).latest("pk")
        self.assertEqual(log.usuario_id, self.usuario.pk)
        self.assertEqual(log.depois["quantidade"], "3.00")
        self.assertEqual(log.depois["unidade_id"], unidade.pk)

    def test_resolver_nao_cria_obrigacao_inexistente(self):
        pedido, _item = self._pedido_legado("1.00")
        inexistente = ObrigacaoEstoquePedido(
            pk=999999, pedido=pedido, produto=self.produto, unidade=self.unidade
        )
        with pytest.raises(ValidationError):
            resolver_pendencia_estoque(
                inexistente,
                usuario=self.usuario,
                justificativa="inexistente",
            )

    def test_falha_na_auditoria_reverte_resolucao(self):
        from unittest import mock

        pedido, _item = self._pedido_legado("3.00")
        marcar_pagamento_aprovado(pedido, id_externo="pay-r01-rollback")
        obrigacao = self._obrigacao(pedido)
        registrar_movimento(
            produto=self.produto,
            unidade=self.unidade,
            tipo=MovimentoEstoque.Tipo.ENTRADA,
            delta=Decimal("3.00"),
            motivo="reposição",
        )
        estoque_antes = Estoque.objects.get(
            produto=self.produto, unidade=self.unidade
        ).quantidade
        movimentos_antes = MovimentoEstoque.objects.count()

        def falhar(*args, **kwargs):
            if kwargs.get("acao") == "pedido.estoque_pendente_resolvido":
                raise RuntimeError("auditoria indisponível")
            return None

        with mock.patch(
            "core.auditoria.registrar_auditoria", side_effect=falhar
        ):
            with pytest.raises(RuntimeError):
                resolver_pendencia_estoque(
                    obrigacao,
                    usuario=self.usuario,
                    justificativa="tentativa com falha",
                )

        obrigacao.refresh_from_db()
        estoque = Estoque.objects.get(
            produto=self.produto, unidade=self.unidade
        )
        self.assertEqual(obrigacao.status, ObrigacaoEstoquePedido.Status.PENDENTE)
        self.assertEqual(estoque.quantidade, estoque_antes)
        self.assertEqual(MovimentoEstoque.objects.count(), movimentos_antes)
