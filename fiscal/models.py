from django.db import models


class NotaFiscal(models.Model):
    """NF-e de um pedido, emitida via ERP (Bling) ou registrada manualmente."""

    class Status(models.TextChoices):
        PENDENTE = "pendente", "Pendente de envio"
        AUTORIZADA = "autorizada", "Autorizada"
        ERRO = "erro", "Erro"

    class Origem(models.TextChoices):
        API = "api", "Integração Bling"
        MANUAL = "manual", "Registro manual"

    pedido = models.OneToOneField(
        "sales.Pedido",
        on_delete=models.PROTECT,
        related_name="nota_fiscal",
        verbose_name="pedido",
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
    ultimo_erro = models.TextField("último erro", blank=True)
    criado_em = models.DateTimeField("criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        verbose_name = "nota fiscal"
        verbose_name_plural = "notas fiscais"

    def __str__(self):
        return f"NF-e {self.numero or '(pendente)'} — {self.pedido.numero}"
