from django.core.exceptions import ValidationError
from django.db import models


class NotaFiscal(models.Model):
    """NF-e de um pedido, emitida via ERP (Bling) ou registrada manualmente."""

    class Status(models.TextChoices):
        PENDENTE = "pendente", "Pendente de envio"
        AUTORIZADA = "autorizada", "Autorizada"
        ERRO = "erro", "Erro"
        CANCELADA = "cancelada", "Cancelada"

    class Origem(models.TextChoices):
        API = "api", "Integração Bling"
        MANUAL = "manual", "Registro manual"

    class Tipo(models.TextChoices):
        SAIDA = "saida", "NF-e de Saída"
        ENTRADA = "entrada", "NF-e de Entrada/Devolução"

    pedido = models.ForeignKey(
        "sales.Pedido",
        on_delete=models.PROTECT,
        related_name="notas_fiscais",
        verbose_name="pedido",
    )
    tipo = models.CharField(
        "tipo", max_length=10, choices=Tipo.choices, default=Tipo.SAIDA
    )
    cfop = models.CharField("CFOP", max_length=10, blank=True)
    chave_referenciada = models.CharField(
        "chave da NF-e referenciada",
        max_length=44,
        blank=True,
        help_text="Para NF-e de devolução: chave da NF-e de saída original.",
    )
    status = models.CharField(
        "status", max_length=12, choices=Status.choices, default=Status.PENDENTE
    )
    origem = models.CharField(
        "origem", max_length=10, choices=Origem.choices, default=Origem.API
    )
    numero = models.CharField("número", max_length=20, blank=True)
    chave_acesso = models.CharField("chave de acesso", max_length=44, blank=True)
    link_documento = models.URLField(
        "link do documento/XML-DANFE", max_length=300, blank=True
    )
    tentativas = models.PositiveIntegerField("tentativas", default=0)
    processando_desde = models.DateTimeField(
        "processando desde",
        null=True,
        blank=True,
        help_text="Lease curto para impedir chamadas fiscais duplicadas.",
    )
    ultimo_erro = models.TextField("último erro", blank=True)
    criado_em = models.DateTimeField("criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        verbose_name = "nota fiscal"
        verbose_name_plural = "notas fiscais"
        constraints = [
            models.UniqueConstraint(
                fields=("pedido", "tipo"),
                name="nota_fiscal_unica_por_pedido_tipo",
            ),
            models.UniqueConstraint(
                fields=("chave_acesso",),
                condition=~models.Q(chave_acesso=""),
                name="nota_fiscal_chave_acesso_unica",
            ),
        ]

    def __str__(self):
        return f"NF-e {self.numero or '(pendente)'} — {self.pedido.numero}"

    def clean(self):
        super().clean()
        if self.chave_acesso and (
            len(self.chave_acesso) != 44
            or not self.chave_acesso.isdigit()
        ):
            raise ValidationError(
                {"chave_acesso": "A chave de acesso deve ter 44 dígitos."}
            )
        if self.chave_acesso and type(self).objects.filter(
            chave_acesso=self.chave_acesso
        ).exclude(pk=self.pk).exists():
            raise ValidationError(
                {"chave_acesso": "Já existe uma nota com esta chave de acesso."}
            )
        if self.tipo == self.Tipo.ENTRADA:
            chave = (self.chave_referenciada or "").strip()
            if not chave:
                raise ValidationError(
                    {
                        "chave_referenciada": (
                            "NF-e de entrada/devolução exige a chave da NF-e "
                            "de saída referenciada."
                        )
                    }
                )
            if len(chave) != 44 or not chave.isdigit():
                raise ValidationError(
                    {
                        "chave_referenciada": (
                            "A chave referenciada deve ter 44 dígitos."
                        )
                    }
                )
