"""STO-01: ledger imutável, delta assinado e reconciliação de saldo."""

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.db import DatabaseError, IntegrityError, connection
from django.db.models import Sum
from django.test import TestCase, TransactionTestCase

from catalog.factories import ProdutoFactory
from core.factories import UnidadeFactory
from stock.factories import EstoqueFactory
from stock.models import Estoque, MovimentoEstoque
from stock.services import (
    ImutabilidadeViolation,
    registrar_ajuste,
    registrar_movimento,
    transferir_estoque,
)


class LedgerImutavelTests(TransactionTestCase):
    """Valida que o ledger preserva trilha e sinal."""

    def setUp(self):
        self.produto = ProdutoFactory()
        self.unidade = UnidadeFactory()
        self.outra_unidade = UnidadeFactory(nome="Unidade Secundária")
        self.admin = get_user_model().objects.create_user(
            username="admin-sto01", password="senha-forte-123"
        )

    def test_ajuste_negativo_grava_delta_negativo(self):
        """Ajuste de -2 grava delta=-2 (não +2)."""
        EstoqueFactory(
            produto=self.produto,
            unidade=self.unidade,
            quantidade="10.00",
        )
        movimento = registrar_ajuste(
            produto=self.produto,
            unidade=self.unidade,
            delta=Decimal("-2.00"),
            motivo="perda",
            usuario=self.admin,
        )
        movimento.refresh_from_db()
        assert movimento.delta == Decimal("-2.00")
        assert movimento.quantidade == Decimal("2.00")  # abs

    def test_reconciliacao_saldo_via_deltas(self):
        """Saldo atual = soma de deltas de todos os movimentos."""
        for delta in ("10.00", "-3.00", "2.00", "-1.00"):
            registrar_movimento(
                produto=self.produto,
                unidade=self.unidade,
                tipo=(
                    MovimentoEstoque.Tipo.AJUSTE_POSITIVO
                    if Decimal(delta) > 0
                    else MovimentoEstoque.Tipo.AJUSTE_NEGATIVO
                ),
                delta=Decimal(delta),
                motivo="sequência STO-01",
            )

        saldo_calculado = MovimentoEstoque.objects.filter(
            produto=self.produto,
            unidade=self.unidade,
        ).aggregate(total=Sum("delta"))["total"]
        estoque = Estoque.objects.get(
            produto=self.produto,
            unidade=self.unidade,
        )
        assert estoque.quantidade == saldo_calculado == Decimal("8.00")

    def test_mutacao_direta_queryset_eh_bloqueada(self):
        """QuerySet.update() em movimento existente deve falhar."""
        movimento = registrar_movimento(
            produto=self.produto,
            unidade=self.unidade,
            tipo=MovimentoEstoque.Tipo.ENTRADA,
            delta=Decimal("5.00"),
        )
        with pytest.raises((ImutabilidadeViolation, IntegrityError)):
            MovimentoEstoque.objects.filter(pk=movimento.pk).update(
                delta=Decimal("999.00")
            )
        movimento.refresh_from_db()
        assert movimento.delta == Decimal("5.00")

    def test_delete_direto_queryset_eh_bloqueado(self):
        movimento = registrar_movimento(
            produto=self.produto,
            unidade=self.unidade,
            tipo=MovimentoEstoque.Tipo.ENTRADA,
            delta=Decimal("5.00"),
        )
        with pytest.raises((ImutabilidadeViolation, IntegrityError)):
            MovimentoEstoque.objects.filter(pk=movimento.pk).delete()
        assert MovimentoEstoque.objects.filter(pk=movimento.pk).exists()

    def test_transferencia_usa_tipos_especificos_e_par_reciproco(self):
        EstoqueFactory(
            produto=self.produto,
            unidade=self.unidade,
            quantidade="50.00",
        )
        saida, entrada = transferir_estoque(
            produto=self.produto,
            unidade_origem=self.unidade,
            unidade_destino=self.outra_unidade,
            quantidade=Decimal("12.00"),
        )
        saida.refresh_from_db()
        entrada.refresh_from_db()
        assert saida.tipo == MovimentoEstoque.Tipo.TRANSFERENCIA_SAIDA
        assert entrada.tipo == MovimentoEstoque.Tipo.TRANSFERENCIA_ENTRADA
        assert saida.delta == Decimal("-12.00")
        assert entrada.delta == Decimal("12.00")
        assert saida.movimento_par_id == entrada.pk
        assert entrada.movimento_par_id == saida.pk

    @pytest.mark.postgres
    def test_trigger_postgres_bloqueia_update_delete(self):
        """Trigger SQL do Postgres impede mutação direta."""
        if connection.vendor != "postgresql":  # pragma: no cover - defesa local
            pytest.skip("Trigger SQL existe apenas no PostgreSQL.")

        movimento = registrar_movimento(
            produto=self.produto,
            unidade=self.unidade,
            tipo=MovimentoEstoque.Tipo.ENTRADA,
            delta=Decimal("5.00"),
        )
        with pytest.raises(DatabaseError):
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE stock_movimentoestoque SET delta = 999 "
                    f"WHERE id = {movimento.pk}"
                )
        with pytest.raises(DatabaseError):
            with connection.cursor() as cursor:
                cursor.execute(
                    f"DELETE FROM stock_movimentoestoque WHERE id = {movimento.pk}"
                )
        assert MovimentoEstoque.objects.filter(pk=movimento.pk).exists()


class DeltaCoerenciaTests(TestCase):
    """Valida coerência entre tipo e sinal do delta."""

    def setUp(self):
        self.produto = ProdutoFactory()
        self.unidade = UnidadeFactory()
        EstoqueFactory(
            produto=self.produto,
            unidade=self.unidade,
            quantidade="100.00",
        )

    def test_entrada_exige_delta_positivo(self):
        from django.core.exceptions import ValidationError

        with pytest.raises(ValidationError):
            registrar_movimento(
                produto=self.produto,
                unidade=self.unidade,
                tipo=MovimentoEstoque.Tipo.ENTRADA,
                delta=Decimal("-1.00"),
            )

    def test_saida_exige_delta_negativo(self):
        from django.core.exceptions import ValidationError

        with pytest.raises(ValidationError):
            registrar_movimento(
                produto=self.produto,
                unidade=self.unidade,
                tipo=MovimentoEstoque.Tipo.SAIDA,
                delta=Decimal("1.00"),
            )

    def test_delta_zero_eh_rejeitado_pelo_servico(self):
        from django.core.exceptions import ValidationError

        with pytest.raises(ValidationError):
            registrar_movimento(
                produto=self.produto,
                unidade=self.unidade,
                tipo=MovimentoEstoque.Tipo.AJUSTE_POSITIVO,
                delta=Decimal("0.00"),
            )

    def test_delta_zero_eh_rejeitado_pela_constraint(self):
        with pytest.raises(IntegrityError):
            MovimentoEstoque.objects.create(
                produto=self.produto,
                unidade=self.unidade,
                tipo=MovimentoEstoque.Tipo.AJUSTE_POSITIVO,
                delta=Decimal("0.00"),
                quantidade=Decimal("0.00"),
            )

    def test_transferencia_sem_par_eh_rejeitada(self):
        from django.core.exceptions import ValidationError

        with pytest.raises(ValidationError):
            registrar_movimento(
                produto=self.produto,
                unidade=self.unidade,
                tipo=MovimentoEstoque.Tipo.TRANSFERENCIA_SAIDA,
                delta=Decimal("-1.00"),
            )

    def test_movimento_existente_nao_pode_ser_salvo(self):
        movimento = registrar_movimento(
            produto=self.produto,
            unidade=self.unidade,
            tipo=MovimentoEstoque.Tipo.ENTRADA,
            delta=Decimal("1.00"),
        )
        movimento.delta = Decimal("2.00")
        with pytest.raises(ImutabilidadeViolation):
            movimento.save()
