import uuid
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models

from accounts.models import Usuario
from catalog.models import Produto
from core.models import Unidade
from customers.models import Cliente


class Pedido(models.Model):
    """Pedido de venda com ciclo de vida explícito."""

    class Status(models.TextChoices):
        RASCUNHO = "rascunho", "Rascunho"
        AGUARDANDO_PAGAMENTO = "aguardando_pagamento", "Aguardando pagamento"
        PAGAMENTO_PENDENTE = "pagamento_pendente", "Pagamento pendente"
        PAGO = "pago", "Pago"
        EM_SEPARACAO = "em_separacao", "Em separação"
        PRONTO_PARA_ENTREGA = "pronto_para_entrega", "Pronto para entrega"
        ENVIADO = "enviado", "Enviado"
        CONCLUIDO = "concluido", "Concluído"
        CANCELADO = "cancelado", "Cancelado"
        FALHOU = "falhou", "Falhou"

    class StatusFinanceiro(models.TextChoices):
        PENDENTE = "pendente", "Pendente"
        PAGO = "pago", "Pago"
        ESTORNADO = "estornado", "Estornado"
        CANCELADO = "cancelado", "Cancelado"

    # Estados legados que ainda existem em Pedido.Status para leitura de dados
    # antigos. Novas transições operacionais não podem gravá-los (ADR-002).
    STATUS_FINANCEIROS_LEGADOS = frozenset(
        {Status.PAGO, Status.PAGAMENTO_PENDENTE, Status.FALHOU}
    )

    TRANSICOES_VALIDAS: dict[str, set[str]] = {
        Status.RASCUNHO: {Status.AGUARDANDO_PAGAMENTO, Status.CANCELADO},
        # Em separação exige status_financeiro=PAGO (validado em transicionar).
        Status.AGUARDANDO_PAGAMENTO: {Status.EM_SEPARACAO, Status.CANCELADO},
        Status.PAGAMENTO_PENDENTE: {Status.CANCELADO},
        Status.PAGO: {Status.EM_SEPARACAO, Status.CANCELADO},
        Status.EM_SEPARACAO: {Status.PRONTO_PARA_ENTREGA},
        Status.PRONTO_PARA_ENTREGA: {Status.ENVIADO, Status.CONCLUIDO},
        Status.ENVIADO: {Status.CONCLUIDO},
        Status.CONCLUIDO: set(),
        Status.CANCELADO: set(),
        Status.FALHOU: {Status.AGUARDANDO_PAGAMENTO, Status.CANCELADO},
    }

    class Modalidade(models.TextChoices):
        ENTREGA = "entrega", "Entrega"
        RETIRADA = "retirada", "Retirada na unidade"

    class Canal(models.TextChoices):
        LOJA = "loja", "Loja online"
        VENDEDOR = "vendedor", "Vendedor"

    numero = models.CharField("número", max_length=20, unique=True, blank=True)
    token_acesso = models.UUIDField(
        "token de acesso",
        default=uuid.uuid4,
        unique=True,
        editable=False,
        help_text="Permite acompanhar o pedido sem expor IDs sequenciais.",
    )
    cliente = models.ForeignKey(
        Cliente, on_delete=models.PROTECT, related_name="pedidos",
        verbose_name="cliente",
    )
    usuario_criador = models.ForeignKey(
        Usuario, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="pedidos_criados", verbose_name="criado por",
    )
    canal = models.CharField(
        "canal", max_length=10, choices=Canal.choices, default=Canal.LOJA
    )
    unidade = models.ForeignKey(
        Unidade, on_delete=models.PROTECT, related_name="pedidos",
        verbose_name="unidade de atendimento",
    )
    modalidade = models.CharField(
        "modalidade", max_length=10, choices=Modalidade.choices
    )
    logradouro = models.CharField("logradouro", max_length=120, blank=True)
    numero_endereco = models.CharField("número", max_length=10, blank=True)
    bairro = models.CharField("bairro", max_length=60, blank=True)
    cidade = models.CharField("cidade", max_length=60, blank=True)
    uf = models.CharField("UF", max_length=2, blank=True)
    cep = models.CharField("CEP", max_length=9, blank=True)
    contato_email = models.EmailField("e-mail de contato", blank=True)
    contato_telefone = models.CharField("telefone de contato", max_length=20, blank=True)
    subtotal = models.DecimalField(
        "subtotal", max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    frete = models.DecimalField(
        "frete", max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    total = models.DecimalField(
        "total", max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    status = models.CharField(
        "status",
        max_length=25,
        choices=Status.choices,
        default=Status.AGUARDANDO_PAGAMENTO,
        db_index=True,
    )
    status_financeiro = models.CharField(
        "status financeiro",
        max_length=20,
        choices=StatusFinanceiro.choices,
        default=StatusFinanceiro.PENDENTE,
        db_index=True,
        help_text="Condição financeira do pedido; independente do andamento.",
    )
    criado_em = models.DateTimeField("criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        verbose_name = "pedido"
        verbose_name_plural = "pedidos"
        ordering = ["-criado_em"]

    def __str__(self):
        return f"{self.numero or '(sem número)'} — {self.cliente.nome} [{self.status}]"

    # ------------------------------------------------------------------ #
    def save(self, *args, **kwargs):
        criando = self.pk is None
        super().save(*args, **kwargs)
        if criando and not self.numero:
            self.numero = f"PF{self.pk:06d}"
            super().save(update_fields=["numero"])

    def transicionar(self, novo_status: str, *, request=None, usuario=None) -> None:
        """Aplica uma transição operacional válida ou levanta ValidationError.

        ADR-002: estados financeiros não são gravados por esta via. A
        aprovação/recusa do provedor usa os serviços de pagamento e
        ``definir_status_financeiro``.
        """
        if novo_status in self.STATUS_FINANCEIROS_LEGADOS:
            raise ValidationError(
                "Estado financeiro não pode ser alterado por transição "
                "operacional; use o resultado do provedor de pagamento."
            )
        permitidos = self.TRANSICOES_VALIDAS.get(self.status, set())
        if novo_status not in permitidos:
            raise ValidationError(
                f"Transição inválida: '{self.status}' → '{novo_status}'. "
                f"Permitidas: {sorted(permitidos)}."
            )
        if (
            novo_status == self.Status.EM_SEPARACAO
            and self.status == self.Status.AGUARDANDO_PAGAMENTO
            and self.status_financeiro != self.StatusFinanceiro.PAGO
        ):
            raise ValidationError(
                "O pedido só pode ir para separação após confirmação "
                "financeira do pagamento."
            )
        status_anterior = self.status
        self.status = novo_status

        from core.auditoria import auditar_atomicamente

        auditar_atomicamente(
            acao="pedido.status_alterado",
            instancia=self,
            request=request,
            usuario=usuario,
            antes={
                "status": status_anterior,
                "status_financeiro": self.status_financeiro,
            },
            depois={
                "status": novo_status,
                "status_financeiro": self.status_financeiro,
            },
            salvar=lambda: self.save(
                update_fields=["status", "atualizado_em"]
            ),
        )

    def definir_status_financeiro(
        self, novo_status: str, *, request=None, usuario=None, motivo: str = ""
    ) -> None:
        """Altera o status financeiro sem tocar no andamento operacional."""
        if novo_status not in self.StatusFinanceiro.values:
            raise ValidationError(
                f"Status financeiro inválido: '{novo_status}'."
            )
        if novo_status == self.status_financeiro:
            return
        status_anterior = self.status_financeiro
        self.status_financeiro = novo_status

        from core.auditoria import auditar_atomicamente

        auditar_atomicamente(
            acao="pedido.status_financeiro_alterado",
            instancia=self,
            request=request,
            usuario=usuario,
            antes={"status_financeiro": status_anterior},
            depois={"status_financeiro": novo_status, "motivo": motivo},
            salvar=lambda: self.save(
                update_fields=["status_financeiro", "atualizado_em"]
            ),
        )

    def recalcular_totais(self) -> None:
        self.subtotal = sum(
            (item.subtotal for item in self.itens.all()), Decimal("0.00")
        )
        self.total = self.subtotal + Decimal(self.frete)
        self.save(update_fields=["subtotal", "total", "atualizado_em"])


class ItemPedido(models.Model):
    pedido = models.ForeignKey(
        Pedido, on_delete=models.CASCADE, related_name="itens",
        verbose_name="pedido",
    )
    produto = models.ForeignKey(
        Produto, on_delete=models.PROTECT, related_name="itens_pedido",
        verbose_name="produto",
    )
    produto_nome = models.CharField("nome do produto", max_length=120)
    quantidade = models.DecimalField(
        "quantidade", max_digits=12, decimal_places=2
    )
    preco_unitario = models.DecimalField(
        "preço unitário", max_digits=12, decimal_places=2,
        help_text="Preço online capturado no momento do checkout.",
    )

    class Meta:
        verbose_name = "item do pedido"
        verbose_name_plural = "itens do pedido"

    def __str__(self):
        return f"{self.quantidade}× {self.produto_nome}"

    @property
    def subtotal(self) -> Decimal:
        return self.preco_unitario * self.quantidade


class Pagamento(models.Model):
    """Pagamento processado por provedor externo (Mercado Pago)."""

    class Status(models.TextChoices):
        PENDENTE = "pendente", "Pendente"
        APROVADO = "aprovado", "Aprovado"
        RECUSADO = "recusado", "Recusado"
        CANCELADO = "cancelado", "Cancelado"

    pedido = models.OneToOneField(
        Pedido, on_delete=models.PROTECT, related_name="pagamento",
        verbose_name="pedido",
    )
    provedor = models.CharField("provedor", max_length=30, default="mercadopago")
    preferencia_id = models.CharField("ID da preferência", max_length=60, blank=True)
    id_externo = models.CharField(
        "ID externo do pagamento", max_length=60, blank=True, db_index=True
    )
    status = models.CharField(
        "status", max_length=10, choices=Status.choices, default=Status.PENDENTE
    )
    valor = models.DecimalField("valor", max_digits=12, decimal_places=2)
    aprovado_em = models.DateTimeField("aprovado em", null=True, blank=True)

    class Meta:
        verbose_name = "pagamento"
        verbose_name_plural = "pagamentos"

    def __str__(self):
        return f"Pagamento {self.pedido.numero} [{self.status}] R$ {self.valor}"


class PagamentoWebhookEvento(models.Model):
    """Evento bruto recebido do provedor, para auditoria e idempotência."""

    provedor = models.CharField("provedor", max_length=30, default="mercadopago")
    referencia_externa = models.CharField(
        "referência externa", max_length=120, db_index=True,
        help_text="Identificador do recurso notificado (ex.: payment_id).",
    )
    payload = models.JSONField("payload bruto")
    processado = models.BooleanField("processado", default=False)
    resultado = models.CharField("resultado", max_length=255, blank=True)
    erro = models.TextField("erro", blank=True)
    recebido_em = models.DateTimeField("recebido em", auto_now_add=True)

    class Meta:
        verbose_name = "evento de webhook"
        verbose_name_plural = "eventos de webhook"
        ordering = ["-recebido_em"]

    def __str__(self):
        return (
            f"{self.provedor}:{self.referencia_externa} "
            f"({'ok' if self.processado else 'pendente'})"
        )
