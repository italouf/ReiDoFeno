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
        ESTOQUE_PENDENTE = "estoque_pendente", "Baixa de estoque pendente"

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
    evento_chave = models.CharField(
        "chave do evento",
        max_length=150,
        blank=True,
        db_index=True,
        help_text=(
            "Vazio para aviso agregado; identifica um evento fiscal durável."
        ),
    )
    lido = models.BooleanField("lido", default=False)
    criado_em = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        verbose_name = "aviso"
        verbose_name_plural = "avisos"
        ordering = ["-criado_em"]
        constraints = [
            models.UniqueConstraint(
                fields=("evento_chave",),
                condition=~models.Q(evento_chave=""),
                name="aviso_evento_chave_unica",
            )
        ]

    def __str__(self):
        return f"[{self.get_severidade_display()}] {self.mensagem}"

    @classmethod
    def registrar(
        cls, *, tipo: str, mensagem: str, objeto=None,
        severidade: str = Severidade.ALERTA,
    ) -> "Aviso":
        """Cria ou reutiliza o aviso agregado do objeto enquanto não lido."""
        objeto_tipo = objeto_id = ""
        if objeto is not None:
            objeto_tipo = f"{objeto._meta.app_label}.{objeto.__class__.__name__}"
            objeto_id = str(objeto.pk)

        aviso = (
            cls.objects.filter(
                tipo=tipo,
                objeto_tipo=objeto_tipo,
                objeto_id=objeto_id,
                lido=False,
                evento_chave="",
            )
            .exclude(mensagem__startswith="Resposta externa ")
            .order_by("pk")
            .first()
        )
        if aviso is not None:
            return aviso
        return cls.objects.create(
            tipo=tipo,
            objeto_tipo=objeto_tipo,
            objeto_id=objeto_id,
            lido=False,
            evento_chave="",
            mensagem=mensagem,
            severidade=severidade,
        )
