from django.db import models


class Aviso(models.Model):
    """Aviso interno gerado automaticamente pelo sistema."""

    class Tipo(models.TextChoices):
        ESTOQUE_BAIXO = "estoque_baixo", "Estoque baixo"
        PAGO_SEM_NFE = "pago_sem_nfe", "Pedido pago sem NF-e"
        PAGAMENTO_PENDENTE = "pagamento_pendente", "Pagamento pendente há muito tempo"
        POSSIVEL_RECOMPRA = "possivel_recompra", "Possível recompra"
        FISCAL_ERRO = "fiscal_erro", "Erro na emissão fiscal"
        FISCAL_DOCUMENTO = "fiscal_documento", "Documento fiscal inválido"

    class Severidade(models.TextChoices):
        INFO = "info", "Informativo"
        ALERTA = "alerta", "Atenção"
        ERRO = "erro", "Crítico"

    tipo = models.CharField("tipo", max_length=30, choices=Tipo.choices, db_index=True)
    severidade = models.CharField(
        "severidade",
        max_length=10,
        choices=Severidade.choices,
        default=Severidade.ALERTA,
    )
    mensagem = models.CharField("mensagem", max_length=255)
    objeto_tipo = models.CharField(
        "tipo do objeto", max_length=60, blank=True,
        help_text="Label do modelo relacionado (ex.: app_label.ModelName).",
    )
    objeto_id = models.CharField("id do objeto", max_length=50, blank=True)
    lido = models.BooleanField("lido", default=False)
    criado_em = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        verbose_name = "aviso"
        verbose_name_plural = "avisos"
        ordering = ["-criado_em"]

    def __str__(self):
        return f"[{self.get_severidade_display()}] {self.mensagem}"

    @classmethod
    def registrar(
        cls, *, tipo: str, mensagem: str, objeto=None,
        severidade: str = Severidade.ALERTA,
    ) -> "Aviso":
        """Cria (ou reutiliza) um aviso para o objeto; idempotente enquanto não lido."""
        objeto_tipo = objeto_id = ""
        if objeto is not None:
            objeto_tipo = f"{objeto._meta.app_label}.{objeto.__class__.__name__}"
            objeto_id = str(objeto.pk)

        aviso, criado = cls.objects.get_or_create(
            tipo=tipo,
            objeto_tipo=objeto_tipo,
            objeto_id=objeto_id,
            lido=False,
            defaults={
                "mensagem": mensagem,
                "severidade": severidade,
            },
        )
        return aviso
