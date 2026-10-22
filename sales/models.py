import uuid
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.functions import Round

from accounts.models import Usuario
from catalog.models import Produto
from core.models import Unidade
from customers.models import Cliente
from stock.exceptions import ImutabilidadeViolation


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

    # Estados que só podem ser atingidos com cobertura financeira paga.
    EXIGE_FINANCEIRO_PAGO = frozenset(
        {
            Status.EM_SEPARACAO,
            Status.PRONTO_PARA_ENTREGA,
            Status.ENVIADO,
            Status.CONCLUIDO,
        }
    )

    TRANSICOES_VALIDAS: dict[str, set[str]] = {
        Status.RASCUNHO: {Status.AGUARDANDO_PAGAMENTO, Status.CANCELADO},
        # Em separação exige status_financeiro=PAGO (validado em transicionar).
        Status.AGUARDANDO_PAGAMENTO: {Status.EM_SEPARACAO, Status.CANCELADO},
        Status.PAGAMENTO_PENDENTE: {Status.EM_SEPARACAO, Status.CANCELADO},
        Status.PAGO: {Status.EM_SEPARACAO, Status.CANCELADO},
        Status.EM_SEPARACAO: {Status.PRONTO_PARA_ENTREGA},
        Status.PRONTO_PARA_ENTREGA: {Status.ENVIADO, Status.CONCLUIDO},
        Status.ENVIADO: {Status.CONCLUIDO},
        Status.CONCLUIDO: set(),
        Status.CANCELADO: set(),
        Status.FALHOU: {Status.CANCELADO},
    }

    class TipoCancelamento(models.TextChoices):
        PADRAO = "padrao", "Cancelamento Padrão (24h)"
        DEVOLUCAO = "devolucao", "Devolução (NF-e de entrada)"

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
    nome_contato = models.CharField(
        "nome de contato", max_length=120, blank=True,
        help_text="Nome informado no pedido; não é identidade verificada.",
    )
    identidade_verificada = models.BooleanField(
        "identidade verificada",
        default=False,
        db_index=True,
        help_text="Pedido criado pelo usuário já vinculado e comprovado.",
    )
    consentimento_compras = models.BooleanField(
        "consentimento de compras", default=False
    )
    consentimento_marketing = models.BooleanField(
        "consentimento de marketing", default=False
    )
    financeiro_conciliado = models.BooleanField(
        "financeiro conciliado",
        default=False,
        db_index=True,
        help_text=(
            "Prova/reconciliação explícita; status histórico inferido não "
            "libera operação."
        ),
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
    uf_entrega = models.CharField(
        "UF de entrega", max_length=2, blank=True
    )
    interestadual = models.BooleanField(
        "interestadual", default=False, db_index=True
    )
    aliquota_icms = models.DecimalField(
        "alíquota de ICMS",
        max_digits=5,
        decimal_places=4,
        default=Decimal("0.0000"),
    )
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
    tipo_cancelamento = models.CharField(  # noqa: DJ001 - nulo = não cancelado
        "tipo de cancelamento",
        max_length=20,
        choices=TipoCancelamento.choices,
        null=True,
        blank=True,
    )
    justificativa_cancelamento = models.TextField(
        "justificativa do cancelamento", blank=True
    )
    cancelado_em = models.DateTimeField(
        "cancelado em", null=True, blank=True
    )
    cancelado_por = models.ForeignKey(
        Usuario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pedidos_cancelados",
        verbose_name="cancelado por",
    )
    criado_em = models.DateTimeField("criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        verbose_name = "pedido"
        verbose_name_plural = "pedidos"
        ordering = ["-criado_em"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(subtotal__gte=Decimal("0.00")),
                name="pedido_subtotal_nao_negativo",
            ),
            models.CheckConstraint(
                condition=models.Q(frete__gte=Decimal("0.00")),
                name="pedido_frete_nao_negativo",
            ),
            models.CheckConstraint(
                condition=models.Q(total__gte=Decimal("0.00")),
                name="pedido_total_nao_negativo",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    total=Round(
                        models.F("subtotal") + models.F("frete"), 2
                    )
                ),
                name="pedido_total_igual_subtotal_mais_frete",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    subtotal__lt=Decimal("10000000000.00")
                ),
                name="pedido_subtotal_dentro_do_limite",
            ),
            models.CheckConstraint(
                condition=models.Q(frete__lt=Decimal("10000000000.00")),
                name="pedido_frete_dentro_do_limite",
            ),
            models.CheckConstraint(
                condition=models.Q(total__lt=Decimal("10000000000.00")),
                name="pedido_total_dentro_do_limite",
            ),
        ]

    def __str__(self):
        return f"{self.numero or '(sem número)'} — {self.cliente.nome} [{self.status}]"

    # ------------------------------------------------------------------ #
    def save(self, *args, **kwargs):
        criando = self.pk is None
        if not self.uf_entrega and self.uf:
            self.uf_entrega = self.uf
            if kwargs.get("update_fields") is not None:
                kwargs["update_fields"] = list(
                    set(kwargs["update_fields"]) | {"uf_entrega"}
                )
        if self.unidade_id:
            from .interestadual import calcular_interestadual

            self.interestadual, self.aliquota_icms = calcular_interestadual(
                self
            )
            if kwargs.get("update_fields") is not None:
                kwargs["update_fields"] = list(
                    set(kwargs["update_fields"])
                    | {"interestadual", "aliquota_icms"}
                )
        super().save(*args, **kwargs)
        if criando and not self.numero:
            self.numero = f"PF{self.pk:06d}"
            super().save(update_fields=["numero"])

    def clean(self):
        super().clean()
        erros = {}
        valores = {}
        for campo in ("subtotal", "frete", "total"):
            valor = getattr(self, campo)
            if valor is None:
                continue
            try:
                numero = Decimal(valor)
            except (ArithmeticError, TypeError, ValueError):
                erros[campo] = "Valor inválido."
                continue
            if not numero.is_finite():
                erros[campo] = "Valor deve ser finito."
                continue
            valores[campo] = numero
            if numero < 0:
                erros[campo] = "Valor não pode ser negativo."
        if len(valores) == 3 and valores["total"] != (
            valores["subtotal"] + valores["frete"]
        ):
            erros["total"] = "Total deve ser igual a subtotal + frete."
        if erros:
            raise ValidationError(erros)

    @property
    def nota_fiscal(self):
        """Nota de saída do pedido (compatibilidade com o vínculo antigo)."""
        if self.pk is None:
            return None
        for nota in sorted(
            self.notas_fiscais.all(), key=lambda item: item.pk, reverse=True
        ):
            if nota.tipo == "saida":
                return nota
        return None

    def tem_prova_financeira(self) -> bool:
        """Prova explícita (provedor validado ou reconciliação autorizada)."""
        return bool(self.financeiro_conciliado)

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
            novo_status in self.EXIGE_FINANCEIRO_PAGO
            and (
                self.status_financeiro != self.StatusFinanceiro.PAGO
                or not self.tem_prova_financeira()
            )
        ):
            raise ValidationError(
                "O andamento só pode avançar com pagamento confirmado e "
                "prova financeira conciliada."
            )
        if (
            novo_status in self.EXIGE_FINANCEIRO_PAGO
            and self.obrigacoes_estoque.filter(
                status=ObrigacaoEstoquePedido.Status.PENDENTE
            ).exists()
        ):
            raise ValidationError(
                "O andamento só pode avançar após a baixa de estoque; "
                "existem obrigações pendentes para este pedido."
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
        if not Decimal(self.frete).is_finite():
            raise ValidationError("Frete deve ser finito.")
        if Decimal(self.frete) < 0:
            raise ValidationError("Frete não pode ser negativo.")
        self.subtotal = sum(
            (item.subtotal for item in self.itens.all()), Decimal("0.00")
        )
        self.total = self.subtotal + Decimal(self.frete)
        self.save(
            update_fields=["subtotal", "frete", "total", "atualizado_em"]
        )

    @property
    def cmv(self) -> Decimal:
        """Custo de mercadoria vendida, pelo snapshot de cada item."""
        return sum(
            (
                item.custo_unitario * item.quantidade
                for item in self.itens.all()
            ),
            Decimal("0.00"),
        )

    @property
    def lucro_bruto(self) -> Decimal:
        """Margem de mercadoria; frete não é receita de produto."""
        return self.subtotal - self.cmv


class ItemPedidoQuerySet(models.QuerySet):
    """Protege o snapshot de custo contra mutações em massa."""

    def update(self, **kwargs):
        if "custo_unitario" in kwargs:
            raise ImutabilidadeViolation(
                "custo_unitario é imutável; registre uma correção auditada."
            )
        return super().update(**kwargs)

    def bulk_update(self, objs, fields, *args, **kwargs):
        if "custo_unitario" in fields:
            raise ImutabilidadeViolation(
                "custo_unitario é imutável; registre uma correção auditada."
            )
        return super().bulk_update(objs, fields, *args, **kwargs)


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
    custo_unitario = models.DecimalField(
        "custo unitário (snapshot)",
        max_digits=12,
        decimal_places=2,
        help_text="Custo do produto no momento da venda (imutável).",
    )

    objects = ItemPedidoQuerySet.as_manager()

    class Meta:
        verbose_name = "item do pedido"
        verbose_name_plural = "itens do pedido"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantidade__gt=Decimal("0.00")),
                name="item_quantidade_positiva",
            ),
            models.CheckConstraint(
                condition=models.Q(preco_unitario__gte=Decimal("0.00")),
                name="item_preco_nao_negativo",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    quantidade__lt=Decimal("10000000000.00")
                ),
                name="item_quantidade_dentro_do_limite",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    preco_unitario__lt=Decimal("10000000000.00")
                ),
                name="item_preco_dentro_do_limite",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    custo_unitario__gte=Decimal("0.00")
                ),
                name="item_custo_nao_negativo",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    custo_unitario__lt=Decimal("10000000000.00")
                ),
                name="item_custo_dentro_do_limite",
            ),
        ]

    def __str__(self):
        return f"{self.quantidade}× {self.produto_nome}"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            original = (
                type(self)
                .objects.filter(pk=self.pk)
                .values_list("custo_unitario", flat=True)
                .first()
            )
            if (
                original is not None
                and self.custo_unitario is not None
                and Decimal(original) != Decimal(self.custo_unitario)
            ):
                raise ImutabilidadeViolation(
                    "custo_unitario é imutável; registre uma correção auditada."
                )
        super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        erros = {}
        for campo in ("quantidade", "preco_unitario", "custo_unitario"):
            valor = getattr(self, campo)
            if valor is None:
                continue
            try:
                numero = Decimal(valor)
            except (ArithmeticError, TypeError, ValueError):
                erros[campo] = "Valor inválido."
                continue
            if not numero.is_finite():
                erros[campo] = "Valor deve ser finito."
                continue
            if campo == "quantidade" and numero <= 0:
                erros[campo] = "Quantidade deve ser maior que zero."
            if campo in ("preco_unitario", "custo_unitario") and numero < 0:
                erros[campo] = "Valor não pode ser negativo."
        if erros:
            raise ValidationError(erros)

    @property
    def subtotal(self) -> Decimal:
        return self.preco_unitario * self.quantidade

    @property
    def lucro_bruto(self) -> Decimal:
        return (self.preco_unitario - self.custo_unitario) * self.quantidade


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
    init_point = models.CharField(
        "URL de checkout", max_length=500, blank=True,
        help_text="Reutilizada para idempotência enquanto a tentativa pendente.",
    )
    idempotency_key = models.CharField(
        "chave de idempotência", max_length=64, blank=True, db_index=True
    )
    criacao_expira_em = models.DateTimeField(
        "expiração da criação", null=True, blank=True,
        help_text="Janela de recuperação de criação externa de preferência.",
    )
    id_externo = models.CharField(
        "ID externo do pagamento", max_length=60, blank=True, db_index=True
    )
    status = models.CharField(
        "status", max_length=10, choices=Status.choices, default=Status.PENDENTE
    )
    valor = models.DecimalField("valor", max_digits=12, decimal_places=2)
    aprovado_em = models.DateTimeField("aprovado em", null=True, blank=True)
    estornado_em = models.DateTimeField(
        "estornado em",
        null=True,
        blank=True,
        help_text="Data do estorno/chargeback; base negativa da receita.",
    )

    class Meta:
        verbose_name = "pagamento"
        verbose_name_plural = "pagamentos"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(valor__gte=Decimal("0.00")),
                name="pagamento_valor_nao_negativo",
            ),
            models.CheckConstraint(
                condition=models.Q(valor__lt=Decimal("10000000000.00")),
                name="pagamento_valor_dentro_do_limite",
            ),
        ]

    def __str__(self):
        return f"Pagamento {self.pedido.numero} [{self.status}] R$ {self.valor}"

    def clean(self):
        super().clean()
        if self.valor is None:
            return
        try:
            valor = Decimal(self.valor)
        except (ArithmeticError, TypeError, ValueError) as erro:
            raise ValidationError({"valor": "Valor inválido."}) from erro
        if not valor.is_finite():
            raise ValidationError({"valor": "Valor deve ser finito."})
        if valor < 0:
            raise ValidationError(
                {"valor": "Valor do pagamento não pode ser negativo."}
            )


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


class ObrigacaoEstoquePedido(models.Model):
    """Obrigação persistente de baixa de estoque por pedido/produto.

    Protege a transição operacional quando o pagamento foi reconhecido, mas a
    baixa não pôde ser concluída. A baixa complementar atualiza
    ``quantidade_baixada`` na mesma transação do movimento.
    """

    class Status(models.TextChoices):
        PENDENTE = "pendente", "Pendente"
        RESOLVIDA = "resolvida", "Resolvida"
        CANCELADA = "cancelada", "Cancelada"

    class TipoPendencia(models.TextChoices):
        NENHUMA = "", "Nenhuma"
        FALTA = "falta", "Falta comprovada"
        AMBIGUA = "ambigua", "Atribuição ambígua"
        EXCESSO = "excesso", "Excesso histórico"

    pedido = models.ForeignKey(
        Pedido,
        on_delete=models.PROTECT,
        related_name="obrigacoes_estoque",
        verbose_name="pedido",
    )
    produto = models.ForeignKey(
        Produto,
        on_delete=models.PROTECT,
        related_name="obrigacoes_estoque",
        verbose_name="produto",
    )
    unidade = models.ForeignKey(
        Unidade,
        on_delete=models.PROTECT,
        related_name="obrigacoes_estoque",
        verbose_name="unidade",
    )
    quantidade_devida = models.DecimalField(
        "quantidade devida", max_digits=12, decimal_places=2
    )
    quantidade_baixada = models.DecimalField(
        "quantidade baixada",
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    evidencia_baixada = models.DecimalField(
        "quantidade com evidência",
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Soma das saídas atribuíveis ao pedido/produto/unidade.",
    )
    evidencia_detalhe = models.JSONField(
        "detalhe da evidência", default=dict, blank=True
    )
    status = models.CharField(
        "status",
        max_length=12,
        choices=Status.choices,
        default=Status.PENDENTE,
        db_index=True,
    )
    tipo_pendencia = models.CharField(
        "tipo de pendência",
        max_length=10,
        choices=TipoPendencia.choices,
        default=TipoPendencia.NENHUMA,
        blank=True,
        db_index=True,
    )
    motivo_pendencia = models.TextField("motivo da pendência", blank=True)
    criado_em = models.DateTimeField("criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("atualizado em", auto_now=True)
    resolvido_em = models.DateTimeField("resolvido em", null=True, blank=True)
    resolvido_por = models.ForeignKey(
        Usuario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="obrigacoes_estoque_resolvidas",
        verbose_name="resolvido por",
    )

    class Meta:
        verbose_name = "obrigação de estoque do pedido"
        verbose_name_plural = "obrigações de estoque do pedido"
        constraints = [
            models.UniqueConstraint(
                fields=("pedido", "produto", "unidade"),
                name="obrigacao_estoque_unica_por_pedido_produto_unidade",
            ),
            models.CheckConstraint(
                condition=models.Q(quantidade_devida__gt=Decimal("0.00")),
                name="obrigacao_estoque_devida_positiva",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    quantidade_baixada__gte=Decimal("0.00")
                ),
                name="obrigacao_estoque_baixada_nao_negativa",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    quantidade_baixada__lte=models.F("quantidade_devida")
                ),
                name="obrigacao_estoque_baixada_dentro_da_devida",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    quantidade_devida__lt=Decimal("10000000000.00")
                ),
                name="obrigacao_estoque_devida_dentro_do_limite",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    evidencia_baixada__gte=Decimal("0.00")
                ),
                name="obrigacao_estoque_evidencia_nao_negativa",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    evidencia_baixada__lt=Decimal("10000000000.00")
                ),
                name="obrigacao_estoque_evidencia_dentro_do_limite",
            ),
        ]

    def __str__(self):
        return (
            f"Obrigação {self.pedido.numero}/{self.produto.nome}@"
            f"{self.unidade.nome}: {self.quantidade_baixada}/"
            f"{self.quantidade_devida} [{self.status}]"
        )

    @property
    def pendente(self) -> bool:
        return self.status == self.Status.PENDENTE

    def clean(self):
        super().clean()
        erros = {}
        for campo in ("quantidade_devida", "quantidade_baixada", "evidencia_baixada"):
            valor = getattr(self, campo)
            if valor is None:
                continue
            try:
                numero = Decimal(valor)
            except (ArithmeticError, TypeError, ValueError):
                erros[campo] = "Valor inválido."
                continue
            if not numero.is_finite():
                erros[campo] = "Valor deve ser finito."
        if erros:
            raise ValidationError(erros)
