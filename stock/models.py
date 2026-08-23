from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


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
        ]

    def __str__(self):
        return f"{self.produto} @ {self.unidade}: {self.quantidade}"

    @property
    def disponivel(self) -> bool:
        return self.quantidade - self.quantidade_bloqueada


class MovimentoEstoque(models.Model):
    """Ledger append-only: toda alteração de saldo gera um movimento."""

    class Tipo(models.TextChoices):
        ENTRADA = "entrada", "Entrada"
        SAIDA = "saida", "Saída"
        AJUSTE = "ajuste", "Ajuste"
        TRANSFERENCIA = "transferencia", "Transferência"

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
    tipo = models.CharField("tipo", max_length=15, choices=Tipo.choices)
    quantidade = models.DecimalField(
        "quantidade", max_digits=12, decimal_places=2,
        help_text="Valor absoluto da movimentação (ajustes usam sinal).",
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
    criado_em = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        verbose_name = "movimento de estoque"
        verbose_name_plural = "movimentos de estoque"
        ordering = ["-criado_em"]

    def __str__(self):
        return f"{self.get_tipo_display()} {self.quantidade} {self.produto} @ {self.unidade}"

    def save(self, *args, **kwargs):
        if self.pk and not kwargs.pop("_permitir_edicao", False):
            raise ValidationError(
                "Movimentos de estoque são imutáveis; faça um ajuste ou estorno."
            )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError(
            "Movimentos de estoque não podem ser excluídos; faça um estorno."
        )
