from django.core.validators import MinValueValidator
from django.db import models


class Categoria(models.Model):
    nome = models.CharField("nome", max_length=80, unique=True)
    descricao = models.TextField("descrição", blank=True)
    ativa = models.BooleanField("ativa", default=True)

    class Meta:
        verbose_name = "categoria"
        verbose_name_plural = "categorias"
        ordering = ["nome"]

    def __str__(self):
        return self.nome


class Produto(models.Model):
    class UnidadeMedida(models.TextChoices):
        KILO = "kg", "Quilograma"
        SACA = "saca", "Saca"
        FARDO = "fardo", "Fardo"
        UNIDADE = "un", "Unidade"

    nome = models.CharField("nome", max_length=120)
    categoria = models.ForeignKey(
        Categoria,
        on_delete=models.PROTECT,
        related_name="produtos",
        verbose_name="categoria",
    )
    ncm = models.CharField(
        "NCM",
        max_length=10,
        blank=True,
        help_text="Nomenclatura Comum do Mercosul (usada na emissão fiscal).",
    )
    unidade_medida = models.CharField(
        "unidade de medida",
        max_length=10,
        choices=UnidadeMedida.choices,
    )
    custo = models.DecimalField(
        "custo", max_digits=10, decimal_places=2,
        validators=[MinValueValidator(0)],
    )
    preco_balcao = models.DecimalField(
        "preço balcão", max_digits=10, decimal_places=2,
        validators=[MinValueValidator(0)],
    )
    preco_online = models.DecimalField(
        "preço online", max_digits=10, decimal_places=2,
        validators=[MinValueValidator(0)],
    )
    ativo = models.BooleanField("ativo", default=True)
    criado_em = models.DateTimeField("criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        verbose_name = "produto"
        verbose_name_plural = "produtos"
        ordering = ["nome"]

    def __str__(self):
        return f"{self.nome} ({self.unidade_medida})"
