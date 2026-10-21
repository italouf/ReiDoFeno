from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from .exceptions import ImutabilidadeViolation

TIPOS_DELTA_POSITIVO = (
    "entrada",
    "entrada_inicial",
    "transferencia_entrada",
    "ajuste_positivo",
)
TIPOS_DELTA_NEGATIVO = (
    "saida",
    "transferencia_saida",
    "ajuste_negativo",
    "baixa_definitiva",
)
TIPOS_DELTA_LEGADOS = ("ajuste", "transferencia")


class MovimentoEstoqueQuerySet(models.QuerySet):
    """Ledger append-only: mutações em massa também são proibidas."""

    def update(self, **kwargs):
        raise ImutabilidadeViolation(
            "Movimentos de estoque não podem ser alterados em massa; "
            "crie um movimento de compensação."
        )

    def delete(self):
        raise ImutabilidadeViolation(
            "Movimentos de estoque não podem ser excluídos em massa; "
            "crie um movimento de compensação."
        )

    def bulk_create(self, objs, *args, **kwargs):
        raise ImutabilidadeViolation(
            "Movimentos de estoque devem ser criados individualmente para "
            "validar delta, tipo e saldo."
        )

    def bulk_update(self, objs, fields, *args, **kwargs):
        raise ImutabilidadeViolation(
            "Movimentos de estoque não podem ser alterados em massa; "
            "crie um movimento de compensação."
        )

    def _update_permitido(self, **kwargs):
        """Operação interna restrita ao vínculo recíproco de transferência."""
        if set(kwargs) != {"movimento_par"}:
            raise ImutabilidadeViolation(
                "Somente o vínculo de movimento_par pode ser atualizado."
            )
        return super().update(**kwargs)


class Estoque(models.Model):
    """Saldo de um produto em uma unidade, com mínimo e reserva."""

    produto = models.ForeignKey(
        "catalog.Produto",
        on_delete=models.PROTECT,
        related_name="estoques",
        verbose_name="produto",
    )
    unidade = models.ForeignKey(
        "core.Unidade",
        on_delete=models.PROTECT,
        related_name="estoques",
        verbose_name="unidade",
    )
    quantidade = models.DecimalField(
        "quantidade", max_digits=12, decimal_places=2, default=0
    )
    quantidade_minima = models.DecimalField(
        "quantidade mínima", max_digits=12, decimal_places=2, default=0
    )
    quantidade_bloqueada = models.DecimalField(
        "quantidade bloqueada", max_digits=12, decimal_places=2, default=0,
        help_text="Reservada para pedidos em andamento; não está disponível.",
    )

    class Meta:
        verbose_name = "estoque"
        verbose_name_plural = "estoques"
        constraints = [
            models.UniqueConstraint(
                fields=("produto", "unidade"), name="uniq_estoque_produto_unidade"
            ),
            models.CheckConstraint(
                condition=models.Q(quantidade__gte=0),
                name="estoque_quantidade_nao_negativa",
            ),
            models.CheckConstraint(
                condition=models.Q(quantidade_bloqueada__gte=0),
                name="estoque_bloqueada_nao_negativa",
            ),
            models.CheckConstraint(
                condition=models.Q(quantidade__gte=models.F("quantidade_bloqueada")),
                name="estoque_bloqueada_dentro_do_saldo",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    quantidade__lt=Decimal("10000000000.00")
                ),
                name="estoque_quantidade_dentro_do_limite",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    quantidade_bloqueada__lt=Decimal("10000000000.00")
                ),
                name="estoque_bloqueada_dentro_do_limite",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    quantidade_minima__lt=Decimal("10000000000.00")
                ),
                name="estoque_minima_dentro_do_limite",
            ),
        ]

    def __str__(self):
        return f"{self.produto} @ {self.unidade}: {self.quantidade}"

    def clean(self):
        super().clean()
        for campo in ("quantidade", "quantidade_minima", "quantidade_bloqueada"):
            valor = getattr(self, campo)
            if valor is not None and not Decimal(valor).is_finite():
                raise ValidationError(
                    {campo: "Valor deve ser finito."}
                )

    @property
    def disponivel(self) -> bool:
        return self.quantidade - self.quantidade_bloqueada


class MovimentoEstoque(models.Model):
    """Ledger append-only: toda alteração de saldo gera um movimento."""

    class Tipo(models.TextChoices):
        ENTRADA = "entrada", "Entrada"
        ENTRADA_INICIAL = "entrada_inicial", "Entrada inicial (migração)"
        SAIDA = "saida", "Saída"
        AJUSTE = "ajuste", "Ajuste (legado)"
        AJUSTE_POSITIVO = "ajuste_positivo", "Ajuste positivo"
        AJUSTE_NEGATIVO = "ajuste_negativo", "Ajuste negativo"
        TRANSFERENCIA = "transferencia", "Transferência (legado)"
        TRANSFERENCIA_ENTRADA = "transferencia_entrada", "Entrada por transferência"
        TRANSFERENCIA_SAIDA = "transferencia_saida", "Saída por transferência"
        BAIXA_DEFINITIVA = "baixa_definitiva", "Baixa definitiva"

    produto = models.ForeignKey(
        "catalog.Produto",
        on_delete=models.PROTECT,
        related_name="movimentos",
        verbose_name="produto",
    )
    unidade = models.ForeignKey(
        "core.Unidade",
        on_delete=models.PROTECT,
        related_name="movimentos",
        verbose_name="unidade",
    )
    tipo = models.CharField("tipo", max_length=30, choices=Tipo.choices)
    delta = models.DecimalField(
        "delta",
        max_digits=12,
        decimal_places=2,
        help_text="Sinal e magnitude: positivo entra, negativo sai.",
    )
    quantidade = models.DecimalField(
        "quantidade", max_digits=12, decimal_places=2,
        help_text="Derivado de abs(delta); mantido para leitura.",
    )
    motivo = models.TextField("motivo", blank=True)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="movimentos_estoque",
        verbose_name="usuário",
    )
    movimento_par = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="contrapartes",
        help_text="Movimento vinculado (saída/entrada de uma transferência).",
    )
    obrigacao = models.ForeignKey(
        "sales.ObrigacaoEstoquePedido",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="movimentos",
        verbose_name="obrigação de estoque",
        help_text="Obrigação do pedido que esta baixa atende, quando aplicável.",
    )
    criado_em = models.DateTimeField("criado em", auto_now_add=True)

    objects = MovimentoEstoqueQuerySet.as_manager()

    class Meta:
        verbose_name = "movimento de estoque"
        verbose_name_plural = "movimentos de estoque"
        ordering = ["-criado_em"]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(delta=Decimal("0.00")),
                name="movimento_delta_nao_zero",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        tipo__in=TIPOS_DELTA_POSITIVO,
                        delta__gt=Decimal("0.00"),
                    )
                    | models.Q(
                        tipo__in=TIPOS_DELTA_NEGATIVO,
                        delta__lt=Decimal("0.00"),
                    )
                    | models.Q(tipo__in=TIPOS_DELTA_LEGADOS)
                ),
                name="movimento_delta_coerente_com_tipo",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    delta__gt=Decimal("-10000000000.00"),
                    delta__lt=Decimal("10000000000.00"),
                ),
                name="movimento_delta_dentro_do_limite",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    quantidade__lt=Decimal("10000000000.00")
                ),
                name="movimento_quantidade_dentro_do_limite",
            ),
        ]

    def __str__(self):
        return (
            f"{self.get_tipo_display()} {self.delta} "
            f"{self.produto} @ {self.unidade}"
        )

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ImutabilidadeViolation(
                f"Movimento {self.pk} não pode ser alterado. "
                "Crie um movimento de compensação."
            )
        if self.delta is None:
            raise ValidationError("Delta é obrigatório.")
        self.delta = Decimal(self.delta)
        if not self.delta.is_finite():
            raise ValidationError("Delta deve ser finito.")
        self.quantidade = abs(self.delta)
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ImutabilidadeViolation(
            f"Movimento {self.pk} não pode ser deletado. "
            "Crie um movimento de compensação."
        )


class ReservaEstoque(models.Model):
    """Reserva identificada de estoque, vinculada a um pedido."""

    class Status(models.TextChoices):
        ATIVA = "ativa", "Ativa"
        CONSUMIDA = "consumida", "Consumida"
        LIBERADA = "liberada", "Liberada"
        EXPIRADA = "expirada", "Expirada"

    pedido = models.ForeignKey(
        "sales.Pedido",
        on_delete=models.PROTECT,
        related_name="reservas",
        verbose_name="pedido",
    )
    item_pedido = models.ForeignKey(
        "sales.ItemPedido",
        on_delete=models.PROTECT,
        related_name="reservas",
        null=True,
        blank=True,
        verbose_name="item do pedido",
    )
    produto = models.ForeignKey(
        "catalog.Produto",
        on_delete=models.PROTECT,
        related_name="reservas",
        verbose_name="produto",
    )
    unidade = models.ForeignKey(
        "core.Unidade",
        on_delete=models.PROTECT,
        related_name="reservas",
        verbose_name="unidade",
    )
    quantidade = models.DecimalField(
        "quantidade", max_digits=12, decimal_places=2
    )
    status = models.CharField(
        "status",
        max_length=20,
        choices=Status.choices,
        default=Status.ATIVA,
        db_index=True,
    )
    criado_em = models.DateTimeField("criado em", auto_now_add=True)
    consumida_em = models.DateTimeField("consumida em", null=True, blank=True)
    liberada_em = models.DateTimeField("liberada em", null=True, blank=True)

    class Meta:
        verbose_name = "reserva de estoque"
        verbose_name_plural = "reservas de estoque"
        ordering = ["-criado_em"]
        constraints = [
            models.UniqueConstraint(
                fields=("pedido", "produto", "unidade"),
                condition=models.Q(status="ativa"),
                name="reserva_ativa_unica_por_pedido_produto_unidade",
            ),
            models.CheckConstraint(
                condition=models.Q(quantidade__gt=Decimal("0.00")),
                name="reserva_quantidade_positiva",
            ),
            models.CheckConstraint(
                condition=models.Q(quantidade__lt=Decimal("10000000000.00")),
                name="reserva_quantidade_dentro_do_limite",
            ),
        ]
        indexes = [
            models.Index(
                fields=("produto", "unidade", "status"),
                name="reserva_estoque_idx",
            ),
        ]

    def __str__(self):
        return (
            f"Reserva {self.pk or '(nova)'} pedido={self.pedido_id} "
            f"{self.quantidade} {self.produto} @ {self.unidade} [{self.status}]"
        )

    def clean(self):
        super().clean()
        if self.quantidade is not None and not Decimal(
            self.quantidade
        ).is_finite():
            raise ValidationError({"quantidade": "Valor deve ser finito."})


class BloqueioLegado(models.Model):
    """Bloqueio sem pedido identificável, mantido em quarentena.

    Reduz disponibilidade e é reconciliado manualmente; nunca é consumido por
    cancelamento/aprovação de um pedido sem vínculo comprovado.
    """

    produto = models.ForeignKey(
        "catalog.Produto",
        on_delete=models.PROTECT,
        related_name="bloqueios_legados",
        verbose_name="produto",
    )
    unidade = models.ForeignKey(
        "core.Unidade",
        on_delete=models.PROTECT,
        related_name="bloqueios_legados",
        verbose_name="unidade",
    )
    quantidade = models.DecimalField(
        "quantidade", max_digits=12, decimal_places=2
    )
    motivo = models.TextField("motivo")
    criado_em = models.DateTimeField("criado em", auto_now_add=True)
    resolvido_em = models.DateTimeField("resolvido em", null=True, blank=True)
    resolvido_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bloqueios_legados_resolvidos",
        verbose_name="resolvido por",
    )
    observacao_resolucao = models.TextField("observação da resolução", blank=True)

    class Meta:
        verbose_name = "bloqueio legado"
        verbose_name_plural = "bloqueios legados"
        ordering = ["-criado_em"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantidade__gt=Decimal("0.00")),
                name="bloqueio_legado_quantidade_positiva",
            ),
            models.CheckConstraint(
                condition=models.Q(quantidade__lt=Decimal("10000000000.00")),
                name="bloqueio_legado_quantidade_dentro_do_limite",
            ),
            models.UniqueConstraint(
                fields=("produto", "unidade"),
                condition=models.Q(resolvido_em__isnull=True),
                name="bloqueio_legado_ativo_unico_por_produto_unidade",
            ),
        ]
        indexes = [
            models.Index(
                fields=("produto", "unidade", "resolvido_em"),
                name="bloqueio_legado_idx",
            ),
        ]

    def __str__(self):
        return (
            f"Bloqueio legado {self.pk} {self.quantidade} "
            f"{self.produto} @ {self.unidade}"
        )

    def clean(self):
        super().clean()
        if self.quantidade is not None and not Decimal(
            self.quantidade
        ).is_finite():
            raise ValidationError({"quantidade": "Valor deve ser finito."})

    @property
    def ativo(self) -> bool:
        return self.resolvido_em is None


class ReconciliacaoEstoqueLegado(models.Model):
    """Evidência de inferência/baseline/quarentena aplicada ao legado."""

    class Tipo(models.TextChoices):
        AJUSTE_SEM_PROVA = "ajuste_sem_prova", "Ajuste sem prova de sinal"
        TRANSFERENCIA_AMBIGUA = (
            "transferencia_ambigua",
            "Transferência ambígua",
        )
        BASELINE = "baseline", "Baseline de abertura/reconciliação"
        BLOQUEIO_QUARENTENA = (
            "bloqueio_quarentena",
            "Bloqueio em quarentena",
        )
        RESERVA_PARCIAL = "reserva_parcial", "Reserva legada parcial"

    produto = models.ForeignKey(
        "catalog.Produto",
        on_delete=models.PROTECT,
        related_name="reconciliacoes_legado",
        verbose_name="produto",
    )
    unidade = models.ForeignKey(
        "core.Unidade",
        on_delete=models.PROTECT,
        related_name="reconciliacoes_legado",
        verbose_name="unidade",
    )
    movimento = models.ForeignKey(
        "stock.MovimentoEstoque",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reconciliacoes_legado",
        verbose_name="movimento",
    )
    tipo = models.CharField("tipo", max_length=30, choices=Tipo.choices)
    quantidade = models.DecimalField(
        "quantidade", max_digits=12, decimal_places=2
    )
    saldo_original = models.DecimalField(
        "saldo original", max_digits=12, decimal_places=2, null=True, blank=True
    )
    saldo_calculado = models.DecimalField(
        "saldo calculado", max_digits=12, decimal_places=2, null=True, blank=True
    )
    detalhe = models.JSONField("detalhe", default=dict, blank=True)
    criado_em = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        verbose_name = "reconciliação de estoque legado"
        verbose_name_plural = "reconciliações de estoque legado"
        ordering = ["-criado_em"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantidade__lt=Decimal("10000000000.00")),
                name="reconciliacao_quantidade_dentro_do_limite",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(saldo_original__lt=Decimal("10000000000.00"))
                    | models.Q(saldo_original__isnull=True)
                ),
                name="reconciliacao_saldo_original_dentro_do_limite",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(saldo_calculado__lt=Decimal("10000000000.00"))
                    | models.Q(saldo_calculado__isnull=True)
                ),
                name="reconciliacao_saldo_calculado_dentro_do_limite",
            ),
        ]

    def __str__(self):
        return (
            f"{self.get_tipo_display()} {self.quantidade} "
            f"{self.produto} @ {self.unidade}"
        )
