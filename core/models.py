from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class LogAuditoria(models.Model):
    """Trilha de auditoria append-only para alterações críticas."""

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="auditorias",
        verbose_name="usuário",
    )
    acao = models.CharField("ação", max_length=60, db_index=True)
    objeto_tipo = models.CharField("tipo do objeto", max_length=80)
    objeto_id = models.CharField("id do objeto", max_length=50)
    antes = models.JSONField("antes", null=True, blank=True)
    depois = models.JSONField("depois", null=True, blank=True)
    ip = models.GenericIPAddressField("IP", null=True, blank=True)
    criado_em = models.DateTimeField("criado em", auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "registro de auditoria"
        verbose_name_plural = "registros de auditoria"
        ordering = ["-criado_em"]

    def __str__(self):
        return f"{self.acao} em {self.objeto_tipo}#{self.objeto_id}"

    def save(self, *args, **kwargs):
        if self.pk and not kwargs.pop("_permitir_edicao", False):
            raise ValidationError("Registros de auditoria são imutáveis.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Registros de auditoria não podem ser excluídos.")


class Unidade(models.Model):
    """Loja ou depósito onde o estoque é mantido."""

    class Tipo(models.TextChoices):
        LOJA = "loja", "Loja"
        DEPOSITO = "deposito", "Depósito"

    nome = models.CharField("nome", max_length=80, unique=True)
    cidade = models.CharField("cidade", max_length=80)
    tipo = models.CharField(
        "tipo", max_length=20, choices=Tipo.choices, default=Tipo.LOJA
    )
    ativa = models.BooleanField("ativa", default=True)

    class Meta:
        verbose_name = "unidade"
        verbose_name_plural = "unidades"
        ordering = ["nome"]

    def __str__(self):
        return self.nome
