from django.conf import settings
from django.db import models

from .validators import DocumentoValidator


def normalizar_documento(valor: str) -> str:
    """Remove pontuação; documentos são armazenados apenas com dígitos."""
    import re

    return re.sub(r"\D", "", str(valor))


class Cliente(models.Model):
    """Cliente da loja, pessoa física ou jurídica."""

    class TipoPessoa(models.TextChoices):
        FISICA = "fisica", "Pessoa física"
        JURIDICA = "juridica", "Pessoa jurídica"

    class Categoria(models.TextChoices):
        ATACADO = "atacado", "Atacado"
        VAREJO = "varejo", "Varejo"

    nome = models.CharField("nome", max_length=120)
    tipo_pessoa = models.CharField(
        "tipo", max_length=10, choices=TipoPessoa.choices
    )
    documento = models.CharField(
        "CPF/CNPJ",
        max_length=18,
        unique=True,
        validators=[DocumentoValidator()],
    )
    categoria = models.CharField(
        "categoria",
        max_length=10,
        choices=Categoria.choices,
        default=Categoria.VAREJO,
    )
    telefone = models.CharField("telefone", max_length=20, blank=True)
    email = models.EmailField("e-mail", blank=True)
    logradouro = models.CharField("logradouro", max_length=120, blank=True)
    numero = models.CharField("número", max_length=10, blank=True)
    bairro = models.CharField("bairro", max_length=60, blank=True)
    cidade = models.CharField("cidade", max_length=60, blank=True)
    uf = models.CharField("UF", max_length=2, blank=True)
    cep = models.CharField("CEP", max_length=9, blank=True)
    preferencia = models.TextField(
        "preferência de compra", blank=True,
        help_text="Produtos habituais, forma de pagamento preferida etc.",
    )
    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cliente",
        verbose_name="usuário vinculado",
    )
    criado_em = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        verbose_name = "cliente"
        verbose_name_plural = "clientes"
        ordering = ["nome"]

    def __str__(self):
        return self.nome

    def save(self, *args, **kwargs):
        self.documento = normalizar_documento(self.documento)
        super().save(*args, **kwargs)

    @property
    def whatsapp_url(self) -> str:
        """Link manual de WhatsApp a partir do telefone cadastrado."""
        digitos = "".join(c for c in self.telefone if c.isdigit())
        if not digitos:
            return ""
        return f"https://wa.me/55{digitos}"


class InteracaoVendedor(models.Model):
    """Registro de atendimento do vendedor com o cliente."""

    class Tipo(models.TextChoices):
        LIGACAO = "ligacao", "Ligação"
        VISITA = "visita", "Visita"
        WHATSAPP = "whatsapp", "WhatsApp"
        OUTRO = "outro", "Outro"

    vendedor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="interacoes",
        verbose_name="vendedor",
    )
    cliente = models.ForeignKey(
        Cliente,
        on_delete=models.PROTECT,
        related_name="interacoes",
        verbose_name="cliente",
    )
    tipo = models.CharField("tipo", max_length=12, choices=Tipo.choices)
    observacao = models.TextField("observação", blank=True)
    pedido = models.ForeignKey(
        "sales.Pedido",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="interacoes",
        verbose_name="pedido relacionado",
    )
    criado_em = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        verbose_name = "interação do vendedor"
        verbose_name_plural = "interações dos vendedores"
        ordering = ["-criado_em"]

    def __str__(self):
        return (
            f"{self.get_tipo_display()} — {self.cliente.nome} "
            f"por {self.vendedor.username}"
        )
