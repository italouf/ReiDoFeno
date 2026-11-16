from datetime import date

from django.core.exceptions import ValidationError
from django.db import models


def _cinco_anos_depois(data: date) -> date:
    """Soma cinco anos de calendário, ajustando 29/02 para 28/02."""
    try:
        return data.replace(year=data.year + 5)
    except ValueError:
        return data.replace(year=data.year + 5, day=28)


class NotaFiscal(models.Model):
    """NF-e de um pedido, emitida via ERP (Bling) ou registrada manualmente."""

    class Status(models.TextChoices):
        PENDENTE = "pendente", "Pendente de envio"
        ANEXADA = "anexada", "Anexada (PDF)"
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
    serie = models.CharField("série", max_length=10, blank=True)
    chave_acesso = models.CharField("chave de acesso", max_length=44, blank=True)
    data_emissao = models.DateTimeField(
        "data de emissão", null=True, blank=True
    )

    # Snapshot do pedido no momento da emissão; nunca é recalculado.
    cliente_nome = models.CharField("nome do cliente", max_length=120, blank=True)
    cliente_documento = models.CharField(
        "documento do cliente", max_length=18, blank=True
    )
    cliente_tipo_pessoa = models.CharField(
        "tipo de pessoa", max_length=10, blank=True
    )
    cliente_endereco = models.TextField("endereço do cliente", blank=True)
    valor_total = models.DecimalField(
        "valor total", max_digits=12, decimal_places=2, default=0
    )
    itens_json = models.JSONField(
        "itens do pedido", default=list, blank=True,
        help_text="Snapshot dos itens no momento da emissão.",
    )
    pdf = models.FileField(
        "PDF da NF-e",
        upload_to="notas_fiscais/%Y/%m/",
        blank=True,
        null=True,
    )
    retido_ate = models.DateField(
        "retido até",
        null=True,
        blank=True,
        db_index=True,
        help_text="Data de retenção legal (5 anos após a emissão).",
    )
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
    tentativa_atual = models.UUIDField(
        "tentativa atual",
        null=True,
        blank=True,
        editable=False,
        help_text="Identidade da tentativa dona do lease de emissão.",
    )
    resultado_externo = models.JSONField(
        "resultado externo",
        default=dict,
        blank=True,
        help_text="Evidência durável de respostas externas tardias/conflitantes.",
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
            models.CheckConstraint(
                condition=models.Q(valor_total__gte=0),
                name="nota_fiscal_valor_total_nao_negativo",
            ),
            models.CheckConstraint(
                condition=models.Q(valor_total__lt=10000000000),
                name="nota_fiscal_valor_total_dentro_do_limite",
            ),
        ]

    def __str__(self):
        return f"NF-e {self.numero or '(pendente)'} — {self.pedido.numero}"

    def save(self, *args, **kwargs):
        if self.data_emissao and not self.retido_ate:
            self.retido_ate = _cinco_anos_depois(self.data_emissao.date())
            update_fields = kwargs.get("update_fields")
            if update_fields is not None:
                kwargs["update_fields"] = list(
                    set(update_fields) | {"retido_ate"}
                )
        super().save(*args, **kwargs)

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
