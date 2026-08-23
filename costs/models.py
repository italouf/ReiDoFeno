from django.core.validators import MinValueValidator
from django.db import models

from customers.validators import validar_cnpj


class Despesa(models.Model):
    """Custos e despesas operacionais do negócio."""

    class Categoria(models.TextChoices):
        OPERACIONAL = "operacional", "Operacional"
        TRANSPORTE = "transporte", "Transporte"
        ARMAZENAGEM = "armazenagem", "Armazenagem"
        MARKETING = "marketing", "Marketing"
        IMPOSTOS = "impostos", "Impostos"
        OUTROS = "outros", "Outros"

    class Recorrencia(models.TextChoices):
        UNICA = "unica", "Única"
        MENSAL = "mensal", "Mensal"
        ANUAL = "anual", "Anual"

    categoria = models.CharField(
        "categoria", max_length=20, choices=Categoria.choices
    )
    tipo = models.CharField("tipo", max_length=80, blank=True)
    fornecedor = models.CharField("fornecedor", max_length=120, blank=True)
    fornecedor_cnpj = models.CharField(
        "CNPJ do fornecedor",
        max_length=18,
        blank=True,
        validators=[validar_cnpj],
    )
    valor = models.DecimalField(
        "valor", max_digits=12, decimal_places=2,
        validators=[MinValueValidator(0)],
    )
    recorrencia = models.CharField(
        "recorrência",
        max_length=10,
        choices=Recorrencia.choices,
        default=Recorrencia.UNICA,
    )
    data = models.DateField("data")
    observacao = models.TextField("observação", blank=True)
    criado_em = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        verbose_name = "despesa"
        verbose_name_plural = "despesas"
        ordering = ["-data"]

    def __str__(self):
        return f"{self.get_categoria_display()} R$ {self.valor} ({self.data:%m/%Y})"
