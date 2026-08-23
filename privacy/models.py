from django.db import models

from customers.models import Cliente


class ConsentimentoLGPD(models.Model):
    """Consentimento por finalidade, versionado, com revogação."""

    class Finalidade(models.TextChoices):
        CADASTRO = "cadastro", "Cadastro e operação da conta"
        COMPRAS = "compras", "Execução de pedidos e entregas"
        MARKETING = "marketing", "Comunicações de marketing"

    cliente = models.ForeignKey(
        Cliente,
        on_delete=models.CASCADE,
        related_name="consentimentos",
        verbose_name="cliente/titular",
    )
    finalidade = models.CharField("finalidade", max_length=20,
                                  choices=Finalidade.choices)
    versao_politica = models.CharField("versão da política", max_length=12,
                                       default="1.0")
    aceito = models.BooleanField("aceito", default=True)
    ip = models.GenericIPAddressField("IP", null=True, blank=True)
    criado_em = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        verbose_name = "consentimento LGPD"
        verbose_name_plural = "consentimentos LGPD"
        ordering = ["-criado_em"]

    def __str__(self):
        estado = "aceito" if self.aceito else "revogado"
        return f"{self.cliente.nome} · {self.get_finalidade_display()} ({estado})"


class SolicitacaoTitular(models.Model):
    """Pedido de exercício de direitos do titular (LGPD art. 18)."""

    class Tipo(models.TextChoices):
        ACESSO = "acesso", "Acesso aos dados"
        CORRECAO = "correcao", "Correção de dados"
        EXPORTACAO = "exportacao", "Exportação dos dados"
        EXCLUSAO = "exclusao", "Exclusão dos dados"

    class Status(models.TextChoices):
        ABERTA = "aberta", "Aberta"
        CONCLUIDA = "concluida", "Concluída"
        RECUSADA = "recusada", "Recusada"

    tipo = models.CharField("tipo", max_length=12, choices=Tipo.choices)
    status = models.CharField(
        "status", max_length=10, choices=Status.choices, default=Status.ABERTA
    )
    cliente = models.ForeignKey(
        Cliente, on_delete=models.PROTECT, related_name="solicitacoes_lgpd",
        verbose_name="titular",
    )
    responsavel = models.ForeignKey(
        "accounts.Usuario", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="solicitacoes_lgpd_respondidas", verbose_name="responsável",
    )
    observacao = models.TextField("observação", blank=True)
    aberta_em = models.DateTimeField("aberta em", auto_now_add=True)
    prazo_limite = models.DateField("prazo limite")
    concluida_em = models.DateTimeField("concluída em", null=True, blank=True)

    class Meta:
        verbose_name = "solicitação do titular"
        verbose_name_plural = "solicitações dos titulares"
        ordering = ["-aberta_em"]

    def __str__(self):
        return (
            f"{self.get_tipo_display()} — {self.cliente.nome} "
            f"[{self.get_status_display()}]"
        )
