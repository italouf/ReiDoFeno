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
    vinculo_verificado = models.BooleanField(
        "vínculo comprovado",
        default=False,
        db_index=True,
        help_text="Vínculo criado pelo fluxo de comprovação ou revisão administrativa.",
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


class VinculoClienteToken(models.Model):
    """Prova de vínculo de uso único; o token enviado é assinado e opaco."""

    cliente = models.ForeignKey(
        Cliente,
        on_delete=models.CASCADE,
        related_name="tokens_vinculo",
        verbose_name="cliente",
    )
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="tokens_vinculo",
        verbose_name="usuário",
    )
    nonce_hash = models.CharField(
        "hash do nonce", max_length=64, unique=True
    )
    email_hash = models.CharField("hash do e-mail", max_length=64)
    criado_em = models.DateTimeField("criado em", auto_now_add=True)
    expira_em = models.DateTimeField("expira em")
    usado_em = models.DateTimeField("usado em", null=True, blank=True)
    revogado_em = models.DateTimeField("revogado em", null=True, blank=True)

    class Meta:
        verbose_name = "prova de vínculo"
        verbose_name_plural = "provas de vínculo"
        ordering = ["-criado_em"]

    def __str__(self):
        return f"vínculo cliente={self.cliente_id} usuário={self.usuario_id}"

    @property
    def ativo(self) -> bool:
        from django.utils import timezone

        return (
            self.usado_em is None
            and self.revogado_em is None
            and self.expira_em > timezone.now()
        )
