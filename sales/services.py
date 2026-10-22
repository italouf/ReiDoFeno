"""Serviços de pedido: criação no checkout, aprovação e cancelamento."""
import logging
import re
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone

from customers.models import Cliente
from stock.models import Estoque, MovimentoEstoque, ReservaEstoque
from stock.services import (
    baixar_saldo_livre,
    consumir_reserva,
    liberar_reserva,
    registrar_movimento,
    reservar,
)

from .cart import Carrinho
from .models import ObrigacaoEstoquePedido, Pagamento, Pedido
from .pricing import (  # noqa: F401 - reexportado para compatibilidade
    LIMIAR_ATACADO,
    calcular_item_pedido,
    calcular_preco_unitario,
)

logger = logging.getLogger(__name__)

GRUPOS_INTERNOS = ("Administrador", "Gestor", "Vendedor")


def _pedido_bloqueado(pedido: Pedido) -> Pedido:
    """Re-lê o pedido sob row lock para evitar decisões com instância stale."""
    return Pedido.objects.select_for_update().get(pk=pedido.pk)


def _travar_reservas(queryset):
    """Trava só a tabela de reservas; não trava produto/pedido via join."""
    from django.db import connection

    if connection.features.has_select_for_update_of:
        return queryset.select_for_update(of=("self",))
    return queryset.select_for_update()


def _validar_ator_estoque(usuario):
    """Ator humano persistido, ativo e autorizado para baixa/evidência."""
    if (
        usuario is None
        or getattr(usuario, "pk", None) is None
        or not getattr(usuario, "is_active", False)
    ):
        raise PermissionDenied("Usuário ativo é obrigatório para resolver.")
    if not (
        usuario.is_superuser
        or usuario.groups.filter(
            name__in=("Administrador", "Gestor")
        ).exists()
    ):
        raise PermissionDenied(
            "Somente Administrador/Gestor pode resolver pendência de estoque."
        )


def _requer_conciliacao_historica(obrigacao) -> bool:
    """Bloqueia nova baixa quando falta atribuição ou há excesso pendente."""
    tipo = getattr(obrigacao, "tipo_pendencia", "")
    if tipo in (
        ObrigacaoEstoquePedido.TipoPendencia.AMBIGUA,
        ObrigacaoEstoquePedido.TipoPendencia.EXCESSO,
    ):
        return True
    detalhe = getattr(obrigacao, "evidencia_detalhe", {}) or {}
    if detalhe.get("ambiguos"):
        return True
    return Decimal(obrigacao.evidencia_baixada or "0.00") > Decimal(
        obrigacao.quantidade_devida
    )


def _quantidade_devida_pedido(pedido, produto, unidade) -> Decimal:
    from .models import ItemPedido

    total = ItemPedido.objects.filter(
        pedido=pedido, produto=produto
    ).aggregate(total=Sum("quantidade"))["total"]
    return Decimal(total or "0.00")


def _obter_obrigacao(pedido, produto, unidade):
    return ObrigacaoEstoquePedido.objects.select_for_update().get_or_create(
        pedido=pedido,
        produto=produto,
        unidade=unidade,
        defaults={
            "quantidade_devida": _quantidade_devida_pedido(
                pedido, produto, unidade
            ),
            "quantidade_baixada": Decimal("0.00"),
            "status": ObrigacaoEstoquePedido.Status.PENDENTE,
            "tipo_pendencia": ObrigacaoEstoquePedido.TipoPendencia.FALTA,
        },
    )[0]


def obter_obrigacao(pedido, produto, unidade):
    """Obtém/cria a obrigação para um pedido/produto/unidade válidos."""
    return _obter_obrigacao(pedido, produto, unidade)


def registrar_baixa_obrigacao(
    pedido: Pedido,
    *,
    produto,
    unidade,
    quantidade,
    usuario=None,
    movimento=None,
) -> ObrigacaoEstoquePedido | None:
    """Atualiza a obrigação na mesma transação do movimento de baixa."""
    if pedido is None or not hasattr(pedido, "pk"):
        return None
    quantidade = Decimal(str(quantidade))
    obrigacao = _obter_obrigacao(pedido, produto, unidade)
    if obrigacao.status == ObrigacaoEstoquePedido.Status.CANCELADA:
        raise ValidationError(
            "Obrigação de estoque cancelada não pode receber baixa."
        )
    if _requer_conciliacao_historica(obrigacao):
        raise ValidationError(
            "Obrigação exige conciliação histórica antes de nova baixa."
        )
    nova = obrigacao.quantidade_baixada + quantidade
    if nova > obrigacao.quantidade_devida:
        raise ValidationError(
            "Baixa acumulada excede a obrigação de estoque do pedido."
        )
    obrigacao.quantidade_baixada = nova
    obrigacao.evidencia_baixada = (
        obrigacao.evidencia_baixada + quantidade
    )
    detalhe = dict(obrigacao.evidencia_detalhe or {})
    movimentos = list(detalhe.get("movimentos", []))
    if movimento is not None:
        movimentos.append(
            {
                "movimento_id": movimento.pk,
                "delta": str(movimento.delta),
                "origem": "servico",
            }
        )
    detalhe["movimentos"] = movimentos
    obrigacao.evidencia_detalhe = detalhe
    campos = [
        "quantidade_baixada",
        "evidencia_baixada",
        "evidencia_detalhe",
        "atualizado_em",
    ]
    if nova == obrigacao.quantidade_devida:
        obrigacao.status = ObrigacaoEstoquePedido.Status.RESOLVIDA
        obrigacao.resolvido_em = timezone.now()
        obrigacao.resolvido_por = usuario
        obrigacao.motivo_pendencia = ""
        obrigacao.tipo_pendencia = (
            ObrigacaoEstoquePedido.TipoPendencia.NENHUMA
        )
        campos += [
            "status",
            "resolvido_em",
            "resolvido_por",
            "motivo_pendencia",
            "tipo_pendencia",
        ]
    obrigacao.save(update_fields=campos)
    return obrigacao


@transaction.atomic
def resolver_pendencia_estoque(
    obrigacao: ObrigacaoEstoquePedido,
    *,
    usuario,
    justificativa: str,
    request=None,
) -> ObrigacaoEstoquePedido:
    """Resolve uma obrigação existente usando saldo livre e/ou reservas.

    Não cria obrigação, não aceita unidade divergente e exige ator autorizado.
    """
    if not justificativa.strip():
        raise ValidationError("Justificativa é obrigatória.")
    _validar_ator_estoque(usuario)

    pedido_id = (
        ObrigacaoEstoquePedido.objects.filter(pk=obrigacao.pk)
        .values_list("pedido_id", flat=True)
        .first()
    )
    if pedido_id is None:
        raise ValidationError("Obrigação de estoque inexistente.")
    pedido = Pedido.objects.select_for_update().get(pk=pedido_id)
    obrigacao = ObrigacaoEstoquePedido.objects.select_for_update().get(
        pk=obrigacao.pk
    )
    if obrigacao.pedido_id != pedido.pk:
        raise ValidationError("Obrigação não pertence ao pedido informado.")
    if obrigacao.unidade_id != pedido.unidade_id:
        raise ValidationError(
            "Obrigação em unidade diferente da unidade do pedido."
        )
    total_item = pedido.itens.filter(
        produto_id=obrigacao.produto_id
    ).aggregate(total=Sum("quantidade"))["total"]
    if total_item is None:
        raise ValidationError(
            "O produto da obrigação não pertence ao pedido."
        )
    if Decimal(total_item) != Decimal(obrigacao.quantidade_devida):
        raise ValidationError(
            "Obrigação não corresponde à quantidade devida do item do pedido."
        )
    if pedido.status == Pedido.Status.CANCELADO or pedido.status_financeiro in (
        Pedido.StatusFinanceiro.CANCELADO,
        Pedido.StatusFinanceiro.ESTORNADO,
    ):
        raise ValidationError(
            "Pedido cancelado/estornado não pode ter pendência resolvida "
            "por baixa manual."
        )
    if (
        pedido.status_financeiro != Pedido.StatusFinanceiro.PAGO
        or not pedido.tem_prova_financeira()
    ):
        raise ValidationError(
            "Só é possível resolver pendência de pedido pago e conciliado."
        )
    if (
        obrigacao.status == ObrigacaoEstoquePedido.Status.PENDENTE
        and _requer_conciliacao_historica(obrigacao)
    ):
        raise ValidationError(
            "Obrigação pendente de conciliação histórica; "
            "use conciliar_obrigacao_historica antes de nova baixa."
        )
    if obrigacao.status != ObrigacaoEstoquePedido.Status.PENDENTE:
        if pedido.reservas.filter(
            produto_id=obrigacao.produto_id,
            unidade_id=obrigacao.unidade_id,
            status=ReservaEstoque.Status.ATIVA,
        ).exists():
            raise ValidationError(
                "Obrigação já coberta, mas há reserva ativa do mesmo "
                "produto/unidade; libere a reserva antes de encerrar."
            )
        return obrigacao

    reservas = list(
        _travar_reservas(
            pedido.reservas.filter(
                produto_id=obrigacao.produto_id,
                unidade_id=obrigacao.unidade_id,
                status=ReservaEstoque.Status.ATIVA,
            ).order_by("pk")
        )
    )
    baixada_inicial = obrigacao.quantidade_baixada
    restante = obrigacao.quantidade_devida - baixada_inicial
    if restante <= 0:
        if reservas:
            raise ValidationError(
                "Obrigação já coberta, mas há reserva ativa do mesmo "
                "produto/unidade; libere a reserva antes de encerrar."
            )
        obrigacao.status = ObrigacaoEstoquePedido.Status.RESOLVIDA
        obrigacao.resolvido_em = timezone.now()
        obrigacao.resolvido_por = usuario
        obrigacao.motivo_pendencia = ""
        obrigacao.save(
            update_fields=[
                "status",
                "resolvido_em",
                "resolvido_por",
                "motivo_pendencia",
                "atualizado_em",
            ]
        )
        from core.auditoria import registrar_auditoria

        registrar_auditoria(
            acao="pedido.estoque_pendente_resolvido",
            instancia=pedido,
            request=request,
            usuario=usuario,
            depois={
                "produto_id": obrigacao.produto_id,
                "unidade_id": obrigacao.unidade_id,
                "quantidade": "0.00",
                "quantidade_baixada": str(obrigacao.quantidade_baixada),
                "justificativa": justificativa.strip()[:500],
            },
        )
        return obrigacao

    for reserva in reservas:
        if reserva.quantidade > restante:
            raise ValidationError(
                "Reserva ativa excede o restante da obrigação; "
                "não é possível resolver sem revisão."
            )
        consumir_reserva(reserva, usuario=usuario, request=request)
        restante -= reserva.quantidade

    if restante > 0:
        estoque = Estoque.objects.select_for_update().get(
            produto_id=obrigacao.produto_id,
            unidade_id=obrigacao.unidade_id,
        )
        livre = estoque.quantidade - estoque.quantidade_bloqueada
        if livre < restante:
            raise ValidationError(
                "Saldo livre insuficiente para resolver a pendência; "
                f"livre={livre}, necessário={restante}."
            )
        baixar_saldo_livre(
            produto=obrigacao.produto,
            unidade=obrigacao.unidade,
            quantidade=restante,
            pedido=pedido,
            usuario=usuario,
            request=request,
        )

    obrigacao.refresh_from_db()
    if obrigacao.status != ObrigacaoEstoquePedido.Status.RESOLVIDA:
        raise ValidationError(
            "A resolução não completou a obrigação; revise as reservas/lotes."
        )
    obrigacao.resolvido_por = usuario
    obrigacao.save(update_fields=["resolvido_por"])
    quantidade_resolvida = obrigacao.quantidade_devida - baixada_inicial
    from core.auditoria import registrar_auditoria

    registrar_auditoria(
        acao="pedido.estoque_pendente_resolvido",
        instancia=pedido,
        request=request,
        usuario=usuario,
        depois={
            "produto_id": obrigacao.produto_id,
            "unidade_id": obrigacao.unidade_id,
            "quantidade": str(quantidade_resolvida),
            "quantidade_baixada": str(obrigacao.quantidade_baixada),
            "justificativa": justificativa.strip()[:500],
        },
    )
    return obrigacao


@transaction.atomic
def conciliar_obrigacao_historica(
    obrigacao: ObrigacaoEstoquePedido,
    *,
    decisao: str,
    usuario,
    justificativa: str,
    movimento_id=None,
    request=None,
) -> ObrigacaoEstoquePedido:
    """Concilia ambiguidade/excesso sem criar movimento compensatório."""
    from stock.models import (
        AlocacaoEvidenciaEstoque,
        MovimentoEstoque,
    )

    from .obrigacoes import reconstruir_obrigacao_evidencia

    if not justificativa.strip():
        raise ValidationError("Justificativa é obrigatória.")
    _validar_ator_estoque(usuario)
    decisoes_validas = {"atribuir", "descartar", "aceitar_excesso"}
    if decisao not in decisoes_validas:
        raise ValidationError("Decisão de conciliação inválida.")

    pedido_id = (
        ObrigacaoEstoquePedido.objects.filter(pk=obrigacao.pk)
        .values_list("pedido_id", flat=True)
        .first()
    )
    if pedido_id is None:
        raise ValidationError("Obrigação de estoque inexistente.")
    pedido = Pedido.objects.select_for_update().get(pk=pedido_id)
    obrigacao = ObrigacaoEstoquePedido.objects.select_for_update().get(
        pk=obrigacao.pk
    )
    if obrigacao.pedido_id != pedido.pk:
        raise ValidationError("Obrigação não pertence ao pedido informado.")
    if pedido.status == Pedido.Status.CANCELADO or pedido.status_financeiro in (
        Pedido.StatusFinanceiro.CANCELADO,
        Pedido.StatusFinanceiro.ESTORNADO,
    ):
        raise ValidationError(
            "Pedido cancelado/estornado não pode ter evidência conciliada."
        )
    if obrigacao.status != ObrigacaoEstoquePedido.Status.PENDENTE:
        raise ValidationError(
            "Somente obrigação pendente pode ser conciliada."
        )
    if (
        pedido.status_financeiro != Pedido.StatusFinanceiro.PAGO
        or not pedido.tem_prova_financeira()
    ):
        raise ValidationError(
            "Só é possível conciliar evidência de pedido pago e conciliado."
        )
    total_item = pedido.itens.filter(
        produto_id=obrigacao.produto_id
    ).aggregate(total=Sum("quantidade"))["total"]
    if total_item is None or Decimal(total_item) != Decimal(
        obrigacao.quantidade_devida
    ):
        raise ValidationError(
            "Obrigação não corresponde à quantidade devida do item do pedido."
        )
    if obrigacao.unidade_id != pedido.unidade_id:
        raise ValidationError(
            "Obrigação em unidade diferente da unidade do pedido."
        )

    dados_antes = reconstruir_obrigacao_evidencia(
        obrigacao,
        Pedido=Pedido,
        Movimento=MovimentoEstoque,
        Alocacao=AlocacaoEvidenciaEstoque,
    )
    detalhe = dict(obrigacao.evidencia_detalhe or {})
    conciliacoes = list(detalhe.get("conciliacoes", []))
    quantidade_conciliada = Decimal("0.00")
    movimento = None

    if decisao in ("atribuir", "descartar"):
        if movimento_id is None:
            raise ValidationError(
                "Movimento é obrigatório para decidir a ambiguidade."
            )
        movimento = MovimentoEstoque.objects.select_for_update().get(
            pk=movimento_id
        )
        if (
            movimento.produto_id != obrigacao.produto_id
            or movimento.unidade_id != obrigacao.unidade_id
            or movimento.tipo
            not in (
                MovimentoEstoque.Tipo.BAIXA_DEFINITIVA,
                MovimentoEstoque.Tipo.SAIDA,
            )
            or movimento.delta >= 0
        ):
            raise ValidationError(
                "Movimento não é uma baixa compatível com a obrigação."
            )
        if movimento.obrigacao_id not in (None, obrigacao.pk):
            raise ValidationError(
                "Movimento já pertence a outra obrigação; não pode ser "
                "reatribuído."
            )
        alocacao = (
            AlocacaoEvidenciaEstoque.objects.select_for_update()
            .filter(movimento_id=movimento.pk)
            .first()
        )
        if alocacao is not None and alocacao.obrigacao_id != obrigacao.pk:
            raise ValidationError(
                "Movimento já alocado como evidência de outro pedido; "
                "a mesma saída não pode cumprir duas obrigações."
            )
        if decisao == "descartar" and alocacao is not None:
            raise ValidationError(
                "Movimento alocado não pode ser descartado nesta obrigação."
            )
        if movimento.pk not in dados_antes["evidencia_detalhe"].get(
            "ambiguos", []
        ):
            raise ValidationError(
                "Movimento não está entre as ambiguidades pertinentes."
            )
        quantidade_conciliada = abs(Decimal(movimento.delta))
        if decisao == "atribuir" and alocacao is None:
            AlocacaoEvidenciaEstoque.objects.create(
                movimento_id=movimento.pk,
                obrigacao_id=obrigacao.pk,
                quantidade=quantidade_conciliada,
                usuario=usuario,
                justificativa=justificativa.strip()[:1000],
            )
        conciliacoes.append(
            {
                "decisao": decisao,
                "movimento_id": movimento.pk,
                "quantidade": str(quantidade_conciliada),
                "usuario_id": usuario.pk,
                "justificativa": justificativa.strip()[:1000],
                "criado_em": timezone.now().isoformat(),
            }
        )
    else:
        if dados_antes.get("tipo_pendencia") != "excesso":
            raise ValidationError(
                "Aceite de excesso exige uma pendência de excesso."
            )
        if dados_antes["evidencia_detalhe"].get("ambiguos"):
            raise ValidationError(
                "Resolva a ambiguidade de atribuição antes de aceitar excesso."
            )
        if Decimal(dados_antes["evidencia_baixada"]) <= Decimal(
            obrigacao.quantidade_devida
        ):
            raise ValidationError("Não há excesso de evidência para aceitar.")
        conciliacoes.append(
            {
                "decisao": "aceitar_excesso",
                "evidencia_baixada": str(
                    dados_antes["evidencia_baixada"]
                ),
                "quantidade_devida": str(obrigacao.quantidade_devida),
                "usuario_id": usuario.pk,
                "justificativa": justificativa.strip()[:1000],
                "criado_em": timezone.now().isoformat(),
            }
        )

    detalhe["conciliacoes"] = conciliacoes
    obrigacao.evidencia_detalhe = detalhe
    dados = reconstruir_obrigacao_evidencia(
        obrigacao,
        Pedido=Pedido,
        Movimento=MovimentoEstoque,
        Alocacao=AlocacaoEvidenciaEstoque,
    )
    campos = [
        "quantidade_baixada",
        "evidencia_baixada",
        "evidencia_detalhe",
        "status",
        "motivo_pendencia",
        "tipo_pendencia",
        "atualizado_em",
    ]
    for campo in ("quantidade_baixada", "evidencia_baixada", "evidencia_detalhe"):
        setattr(obrigacao, campo, dados[campo])
    obrigacao.status = dados["status"]
    obrigacao.motivo_pendencia = dados["motivo_pendencia"]
    obrigacao.tipo_pendencia = dados["tipo_pendencia"]
    if dados["status"] == ObrigacaoEstoquePedido.Status.RESOLVIDA:
        obrigacao.resolvido_em = timezone.now()
        obrigacao.resolvido_por = usuario
        campos += ["resolvido_em", "resolvido_por"]
    else:
        obrigacao.resolvido_em = None
        obrigacao.resolvido_por = None
        campos += ["resolvido_em", "resolvido_por"]
    obrigacao.save(update_fields=campos)

    from core.auditoria import registrar_auditoria

    registrar_auditoria(
        acao="pedido.estoque_evidencia_conciliada",
        instancia=pedido,
        request=request,
        usuario=usuario,
        antes={
            "status": dados_antes["status"],
            "quantidade_baixada": str(dados_antes["quantidade_baixada"]),
            "evidencia_baixada": str(dados_antes["evidencia_baixada"]),
            "tipo_pendencia": dados_antes.get("tipo_pendencia", ""),
            "motivo_pendencia": dados_antes["motivo_pendencia"],
        },
        depois={
            "decisao": decisao,
            "movimento_id": movimento.pk if movimento is not None else None,
            "quantidade_conciliada": str(quantidade_conciliada),
            "status": dados["status"],
            "quantidade_baixada": str(dados["quantidade_baixada"]),
            "evidencia_baixada": str(dados["evidencia_baixada"]),
            "tipo_pendencia": dados.get("tipo_pendencia", ""),
            "justificativa": justificativa.strip()[:500],
        },
    )
    return obrigacao


def pedidos_visiveis_para(usuario):
    """Recorte de autorização: gestor/admin tudo; vendedor só o que criou."""
    if usuario.is_superuser or usuario.groups.filter(
        name__in=("Administrador", "Gestor")
    ).exists():
        return Pedido.objects.all()
    return Pedido.objects.filter(usuario_criador=usuario)


@transaction.atomic
def alterar_status_operacional(
    pedido_id: int, novo_status: str, *, usuario, request=None
) -> Pedido:
    """Centraliza decisão e gravação sob lock, com autorização por objeto."""
    pedido = get_object_or_404(
        pedidos_visiveis_para(usuario).select_for_update(), pk=pedido_id
    )
    if novo_status == Pedido.Status.CANCELADO:
        if pedido.status_financeiro == Pedido.StatusFinanceiro.PAGO:
            raise ValidationError(
                "Pedido pago deve ser cancelado pelo fluxo de cancelamento "
                "padrão ou devolução."
            )
        return cancelar_pedido(pedido, request=request, usuario=usuario)
    pedido.transicionar(novo_status, request=request, usuario=usuario)
    return pedido


def saldo_disponivel(produto, unidade) -> Decimal:
    """Saldo livre (descontada reserva) do produto na unidade."""
    agregado = Estoque.objects.filter(produto=produto, unidade=unidade).aggregate(
        saldo=Sum("quantidade"), bloqueada=Sum("quantidade_bloqueada")
    )
    return (agregado["saldo"] or Decimal("0")) - (
        agregado["bloqueada"] or Decimal("0")
    )


def _cliente_por_documento(
    *, nome: str, documento: str, email: str, telefone: str,
) -> tuple[Cliente, bool]:
    """Localiza ou cria o cliente pelo documento (armazenado em dígitos).

    SEC-02/R4: o checkout nunca vincula ``Cliente.usuario``. O retorno
    indica também se o cadastro foi criado agora, para que os dados do
    pedido não sejam confundidos com identidade comprovada.
    """
    from customers.models import normalizar_documento

    documento = normalizar_documento(documento)
    cliente = Cliente.objects.filter(documento=documento).first()
    if cliente:
        return cliente, False
    tipo_pessoa = (
        Cliente.TipoPessoa.FISICA
        if len(documento) == 11
        else Cliente.TipoPessoa.JURIDICA
    )
    cliente = Cliente.objects.create(
        nome=nome,
        documento=documento,
        tipo_pessoa=tipo_pessoa,
        categoria=Cliente.Categoria.VAREJO,
        telefone=telefone,
        email=email,
        usuario=None,
    )
    return cliente, True


@transaction.atomic
def criar_pedido_do_carrinho(request, formulario) -> Pedido:
    """Cria o pedido com itens e reserva o estoque — tudo ou nada."""
    carrinho = Carrinho(request)
    itens = carrinho.itens()
    if not itens:
        raise ValidationError("O carrinho está vazio.")

    unidade = formulario.cleaned_data["unidade"]
    _validar_disponibilidade(itens, unidade)
    # Ordem global de locks por produto evita deadlock entre checkouts.
    for item in sorted(itens, key=lambda entrada: entrada["produto"].pk):
        Estoque.objects.select_for_update().get_or_create(
            produto=item["produto"],
            unidade=unidade,
            defaults={"quantidade_minima": 0},
        )

    usuario = request.user if request.user.is_authenticated else None
    criado_por_interno = bool(
        usuario and usuario.groups.filter(name__in=GRUPOS_INTERNOS).exists()
    )
    cliente, _criado = _cliente_por_documento(
        nome=formulario.cleaned_data["nome"],
        documento=formulario.cleaned_data["documento"],
        email=formulario.cleaned_data["email"],
        telefone=formulario.cleaned_data.get("telefone", ""),
    )
    identidade_verificada = bool(
        not criado_por_interno
        and usuario is not None
        and cliente.usuario_id == usuario.pk
        and cliente.vinculo_verificado
    )
    aceita_marketing = bool(
        not criado_por_interno
        and formulario.cleaned_data.get("aceita_marketing")
    )

    canal = Pedido.Canal.VENDEDOR if criado_por_interno else Pedido.Canal.LOJA
    pedido = Pedido.objects.create(
        cliente=cliente,
        nome_contato=formulario.cleaned_data["nome"],
        identidade_verificada=identidade_verificada,
        consentimento_compras=not criado_por_interno,
        consentimento_marketing=aceita_marketing,
        usuario_criador=usuario,
        canal=canal,
        unidade=unidade,
        modalidade=formulario.cleaned_data["modalidade"],
        logradouro=formulario.cleaned_data.get("logradouro", ""),
        numero_endereco=formulario.cleaned_data.get("numero_endereco", ""),
        bairro=formulario.cleaned_data.get("bairro", ""),
        cidade=formulario.cleaned_data.get("cidade", ""),
        uf=formulario.cleaned_data.get("uf", ""),
        uf_entrega=formulario.cleaned_data.get("uf", ""),
        cep=formulario.cleaned_data.get("cep", ""),
        contato_email=formulario.cleaned_data["email"],
        contato_telefone=formulario.cleaned_data.get("telefone", ""),
    )

    for item in itens:
        produto = item["produto"]
        tabela_atacado = (
            cliente.categoria == Cliente.Categoria.ATACADO
            and (identidade_verificada or criado_por_interno)
        )
        preco_base = (
            produto.preco_balcao if tabela_atacado else produto.preco_online
        )
        item_pedido = calcular_item_pedido(
            produto=produto,
            cliente=cliente if tabela_atacado else None,
            quantidade=item["quantidade"],
            preco_base=preco_base,
        )
        item_pedido.pedido = pedido
        item_pedido.save()
        reservar(
            produto=produto,
            unidade=unidade,
            quantidade=item["quantidade"],
            pedido=pedido,
            item_pedido=item_pedido,
        )
        obrigacao, criada = ObrigacaoEstoquePedido.objects.get_or_create(
            pedido=pedido,
            produto=produto,
            unidade=unidade,
            defaults={
                "quantidade_devida": item["quantidade"],
                "status": ObrigacaoEstoquePedido.Status.PENDENTE,
                "tipo_pendencia": (
                    ObrigacaoEstoquePedido.TipoPendencia.FALTA
                ),
            },
        )
        if not criada:
            obrigacao.quantidade_devida += Decimal(item["quantidade"])
            obrigacao.save(update_fields=["quantidade_devida", "atualizado_em"])

    pedido.recalcular_totais()

    ip = request.META.get("REMOTE_ADDR")
    if identidade_verificada:
        # LGPD: somente o titular comprovado exerce consentimentos no cadastro.
        from privacy.services import registrar_consentimento

        registrar_consentimento(
            cliente=cliente,
            finalidade="compras",
            aceito=True,
            ip=ip,
        )
        if aceita_marketing:
            registrar_consentimento(
                cliente=cliente,
                finalidade="marketing",
                aceito=True,
                ip=ip,
            )

    from core.auditoria import registrar_auditoria

    registrar_auditoria(
        acao="pedido.criado",
        instancia=pedido,
        request=request,
        depois={
            "cliente_id": cliente.pk,
            "canal": pedido.canal,
            "identidade_verificada": identidade_verificada,
            "consentimento_compras": pedido.consentimento_compras,
            "consentimento_marketing": pedido.consentimento_marketing,
            "total": str(pedido.total),
            "itens": [
                {
                    "produto": item.produto_nome,
                    "quantidade": str(item.quantidade),
                }
                for item in pedido.itens.all()
            ],
        },
    )

    carrinho.limpar()
    return pedido


def _validar_disponibilidade(itens, unidade) -> None:
    faltas = []
    for item in itens:
        disponivel = saldo_disponivel(item["produto"], unidade)
        if disponivel < item["quantidade"]:
            faltas.append(
                f"{item['produto'].nome} (disponível: {disponivel})"
            )
    if faltas:
        raise ValidationError(
            "Quantidade indisponível em "
            f"{unidade.nome}: " + "; ".join(faltas)
        )


def _registrar_pendencia_estoque(
    pedido: Pedido, *, produto, quantidade, motivo, request=None
) -> None:
    """Registra pendência auditada sem tocar em bloqueio de terceiros."""
    from analytics.models import Aviso
    from core.auditoria import registrar_auditoria

    mensagem = (
        f"Pedido {pedido.numero}: baixa pendente de {quantidade} "
        f"de {produto.nome} — {motivo}"
    )[:255]
    Aviso.registrar(
        tipo=Aviso.Tipo.ESTOQUE_PENDENTE,
        mensagem=mensagem,
        objeto=pedido,
        severidade=Aviso.Severidade.ERRO,
    )
    obrigacao = ObrigacaoEstoquePedido.objects.filter(
        pedido=pedido, produto=produto, unidade=pedido.unidade
    ).first()
    if (
        obrigacao is not None
        and obrigacao.status == ObrigacaoEstoquePedido.Status.PENDENTE
    ):
        obrigacao.motivo_pendencia = motivo[:1000]
        obrigacao.save(update_fields=["motivo_pendencia", "atualizado_em"])
    registrar_auditoria(
        acao="pedido.estoque_pendente",
        instancia=pedido,
        request=request,
        depois={
            "produto_id": produto.pk,
            "quantidade": str(quantidade),
            "motivo": motivo,
        },
    )


def _baixar_estoque_do_pedido(pedido: Pedido, *, request=None) -> None:
    """Baixa o devido usando obrigação persistente e saldo livre.

    Reservas ativas são consumidas; reservas já consumidas são reconciliadas
    com a obrigação. A diferença é baixada apenas se houver saldo livre. Caso
    contrário, a obrigação fica pendente e bloqueia o avanço operacional.
    """
    itens = {}
    for item in pedido.itens.select_related("produto"):
        dados = itens.setdefault(
            item.produto_id,
            {"produto": item.produto, "quantidade": Decimal("0.00")},
        )
        dados["quantidade"] += Decimal(item.quantidade)

    reservas = list(
        _travar_reservas(
            pedido.reservas.filter(
                status__in=(
                    ReservaEstoque.Status.ATIVA,
                    ReservaEstoque.Status.CONSUMIDA,
                )
            )
            .select_related("produto")
            .order_by("produto_id", "pk")
        )
    )
    por_produto = {}
    for reserva in reservas:
        por_produto.setdefault(reserva.produto_id, []).append(reserva)

    for produto_id in sorted(itens):
        dados = itens[produto_id]
        todas = por_produto.pop(produto_id, [])
        ativas = [
            reserva
            for reserva in todas
            if reserva.status == ReservaEstoque.Status.ATIVA
        ]
        consumidas = sum(
            (
                reserva.quantidade
                for reserva in todas
                if reserva.status == ReservaEstoque.Status.CONSUMIDA
            ),
            Decimal("0.00"),
        )
        obrigacao = _obter_obrigacao(
            pedido, dados["produto"], pedido.unidade
        )
        if obrigacao.status != ObrigacaoEstoquePedido.Status.PENDENTE:
            if (
                obrigacao.status
                == ObrigacaoEstoquePedido.Status.RESOLVIDA
            ):
                # A baixa física já foi comprovada; reservas ativas são
                # bloqueios órfãos e devem ser liberadas, não consumidas.
                for reserva in ativas:
                    liberar_reserva(reserva)
            continue
        if _requer_conciliacao_historica(obrigacao):
            _registrar_pendencia_estoque(
                pedido,
                produto=dados["produto"],
                quantidade=obrigacao.quantidade_devida,
                motivo=(
                    "obrigação exige conciliação histórica "
                    f"({obrigacao.tipo_pendencia})"
                ),
                request=request,
            )
            continue
        devido = obrigacao.quantidade_devida

        if consumidas > obrigacao.quantidade_baixada:
            # Legado: reserva consumida antes da obrigação existir.
            obrigacao.quantidade_baixada = min(devido, consumidas)
            obrigacao.evidencia_baixada = max(
                obrigacao.evidencia_baixada,
                obrigacao.quantidade_baixada,
            )
            detalhe = dict(obrigacao.evidencia_detalhe or {})
            detalhe["reservas_consumidas_legado"] = [
                {
                    "reserva_id": reserva.pk,
                    "quantidade": str(reserva.quantidade),
                }
                for reserva in todas
                if reserva.status == ReservaEstoque.Status.CONSUMIDA
            ]
            obrigacao.evidencia_detalhe = detalhe
            if obrigacao.quantidade_baixada >= devido:
                if consumidas > devido:
                    _registrar_pendencia_estoque(
                        pedido,
                        produto=dados["produto"],
                        quantidade=consumidas - devido,
                        motivo="reservas consumidas excedem a quantidade devida",
                        request=request,
                    )
                else:
                    obrigacao.status = (
                        ObrigacaoEstoquePedido.Status.RESOLVIDA
                    )
                    obrigacao.resolvido_em = timezone.now()
            obrigacao.save(
                update_fields=[
                    "quantidade_baixada",
                    "evidencia_baixada",
                    "evidencia_detalhe",
                    "status",
                    "resolvido_em",
                    "atualizado_em",
                ]
            )
            if obrigacao.status != ObrigacaoEstoquePedido.Status.PENDENTE:
                continue

        restante = devido - obrigacao.quantidade_baixada
        if restante <= 0:
            continue

        for reserva in ativas:
            if reserva.quantidade > restante:
                _registrar_pendencia_estoque(
                    pedido,
                    produto=dados["produto"],
                    quantidade=reserva.quantidade - restante,
                    motivo="reserva ativa excede a quantidade devida",
                    request=request,
                )
                restante = Decimal("-1.00")
                break
            consumir_reserva(reserva, request=request)
            restante -= reserva.quantidade

        if restante <= 0:
            continue

        estoque = (
            Estoque.objects.select_for_update()
            .filter(produto=dados["produto"], unidade=pedido.unidade)
            .first()
        )
        livre = (
            Decimal("0.00")
            if estoque is None
            else estoque.quantidade - estoque.quantidade_bloqueada
        )
        if estoque is None or livre < restante:
            _registrar_pendencia_estoque(
                pedido,
                produto=dados["produto"],
                quantidade=restante,
                motivo=(
                    f"saldo livre insuficiente (livre={livre}, "
                    f"necessário={restante})"
                ),
                request=request,
            )
            continue
        baixar_saldo_livre(
            produto=dados["produto"],
            unidade=pedido.unidade,
            quantidade=restante,
            pedido=pedido,
            request=request,
        )

    for reservas_sobrando in por_produto.values():
        for reserva in reservas_sobrando:
            if reserva.status != ReservaEstoque.Status.ATIVA:
                continue
            _registrar_pendencia_estoque(
                pedido,
                produto=reserva.produto,
                quantidade=reserva.quantidade,
                motivo="reserva ativa sem item correspondente no pedido",
                request=request,
            )


@transaction.atomic
def marcar_pagamento_aprovado(
    pedido: Pedido, *, id_externo: str = "", request=None
) -> None:
    """Idempotente: confirma o financeiro e efetiva a baixa do estoque.

    ADR-002: não altera ``Pedido.status`` (andamento operacional).
    """
    pedido = _pedido_bloqueado(pedido)
    if pedido.status_financeiro == Pedido.StatusFinanceiro.PAGO:
        pagamento = getattr(pedido, "pagamento", None)
        status_pagamento_anterior = (
            pagamento.status if pagamento is not None else None
        )
        id_externo_anterior = (
            pagamento.id_externo if pagamento is not None else None
        )
        data_aprovacao_anterior = (
            pagamento.aprovado_em if pagamento is not None else None
        )
        _atualizar_pagamento_aprovado(pedido, id_externo=id_externo)
        reservas_ativas = list(
            ReservaEstoque.objects.filter(
                pedido=pedido, status=ReservaEstoque.Status.ATIVA
            )
            .select_related("produto")
            .order_by("pk")
        )
        for reserva_ativa in reservas_ativas:
            obrigacao = ObrigacaoEstoquePedido.objects.filter(
                pedido=pedido,
                produto_id=reserva_ativa.produto_id,
                unidade_id=pedido.unidade_id,
            ).first()
            if (
                obrigacao is not None
                and obrigacao.status
                == ObrigacaoEstoquePedido.Status.RESOLVIDA
            ):
                # T02-B: baixa já comprovada; a reserva ativa é órfã.
                liberar_reserva(reserva_ativa)
                continue
            _registrar_pendencia_estoque(
                pedido,
                produto=reserva_ativa.produto,
                quantidade=reserva_ativa.quantidade,
                motivo="pedido já pago com reserva ativa",
                request=request,
            )
        if (
            pagamento is not None
            and status_pagamento_anterior != Pagamento.Status.APROVADO
        ):
            from core.auditoria import registrar_auditoria

            registrar_auditoria(
                acao="pedido.pagamento_aprovado",
                instancia=pedido,
                request=request,
                depois={
                    "status": pedido.status,
                    "status_financeiro": pedido.status_financeiro,
                    "id_externo": id_externo,
                    "pagamento_id": pagamento.pk,
                    "origem": "sincronizacao_legado",
                },
            )
        elif pagamento is not None and (
            id_externo_anterior != pagamento.id_externo
            or data_aprovacao_anterior is None
        ):
            from core.auditoria import registrar_auditoria

            registrar_auditoria(
                acao="pedido.pagamento_aprovado_metadados_corrigidos",
                instancia=pedido,
                request=request,
                antes={
                    "id_externo": id_externo_anterior,
                    "aprovado_em": (
                        data_aprovacao_anterior.isoformat()
                        if data_aprovacao_anterior
                        else None
                    ),
                },
                depois={
                    "id_externo": pagamento.id_externo,
                    "aprovado_em": (
                        pagamento.aprovado_em.isoformat()
                        if pagamento.aprovado_em
                        else None
                    ),
                },
            )
        if not pedido.tem_prova_financeira():
            pedido.financeiro_conciliado = True
            pedido.save(update_fields=["financeiro_conciliado", "atualizado_em"])
            from core.auditoria import registrar_auditoria

            registrar_auditoria(
                acao="pedido.financeiro_reconciliado",
                instancia=pedido,
                request=request,
                depois={
                    "origem": "provedor",
                    "id_externo": id_externo,
                    "financeiro_conciliado": True,
                },
            )
        logger.info("Pedido %s já estava pago; evento ignorado.", pedido.numero)
        return pedido

    if pedido.status == Pedido.Status.CANCELADO:
        _registrar_pagamento_apos_cancelamento(
            pedido, id_externo=id_externo, request=request
        )
        return pedido

    if pedido.status_financeiro in (
        Pedido.StatusFinanceiro.CANCELADO,
        Pedido.StatusFinanceiro.ESTORNADO,
    ):
        from core.auditoria import registrar_auditoria

        logger.error(
            "Pedido %s com financeiro %s recebeu aprovação; "
            "conciliação manual necessária.",
            pedido.numero,
            pedido.status_financeiro,
        )
        registrar_auditoria(
            acao="pedido.pagamento_inconsistente",
            instancia=pedido,
            request=request,
            depois={
                "status": pedido.status,
                "status_financeiro": pedido.status_financeiro,
                "id_externo": id_externo,
            },
        )
        _atualizar_pagamento_aprovado(pedido, id_externo=id_externo)
        return pedido

    if pedido.status in (
        Pedido.Status.RASCUNHO,
        Pedido.Status.FALHOU,
        Pedido.Status.EM_SEPARACAO,
        Pedido.Status.PRONTO_PARA_ENTREGA,
        Pedido.Status.ENVIADO,
        Pedido.Status.CONCLUIDO,
    ):
        from core.auditoria import registrar_auditoria

        logger.error(
            "Pedido %s está em %s sem status financeiro pago; "
            "aprovação exige conciliação manual.",
            pedido.numero,
            pedido.status,
        )
        registrar_auditoria(
            acao="pedido.pagamento_inconsistente",
            instancia=pedido,
            request=request,
            depois={
                "status": pedido.status,
                "status_financeiro": pedido.status_financeiro,
                "id_externo": id_externo,
            },
        )
        _atualizar_pagamento_aprovado(pedido, id_externo=id_externo)
        return pedido

    pedido.definir_status_financeiro(
        Pedido.StatusFinanceiro.PAGO,
        request=request,
        motivo="pagamento aprovado pelo provedor",
    )
    pedido.financeiro_conciliado = True
    pedido.save(update_fields=["financeiro_conciliado", "atualizado_em"])

    _baixar_estoque_do_pedido(pedido, request=request)

    _atualizar_pagamento_aprovado(pedido, id_externo=id_externo)

    from core.auditoria import registrar_auditoria

    registrar_auditoria(
        acao="pedido.pagamento_aprovado",
        instancia=pedido,
        request=request,
        depois={
            "status": pedido.status,
            "status_financeiro": pedido.status_financeiro,
            "financeiro_conciliado": pedido.financeiro_conciliado,
            "id_externo": id_externo,
            "pagamento_id": getattr(
                getattr(pedido, "pagamento", None), "pk", None
            ),
        },
    )
    return pedido


def _atualizar_pagamento_aprovado(pedido: Pedido, *, id_externo: str) -> None:
    pagamento = getattr(pedido, "pagamento", None)
    if pagamento is None:
        return
    from django.utils import timezone

    campos = []
    if pagamento.status != Pagamento.Status.APROVADO:
        pagamento.status = Pagamento.Status.APROVADO
        campos.append("status")
    if id_externo and pagamento.id_externo != id_externo:
        pagamento.id_externo = id_externo
        campos.append("id_externo")
    if pagamento.aprovado_em is None:
        pagamento.aprovado_em = timezone.now()
        campos.append("aprovado_em")
    if campos:
        pagamento.save(update_fields=campos)


def _registrar_pagamento_apos_cancelamento(
    pedido: Pedido, *, id_externo: str, request
) -> None:
    """Mantém o pedido cancelado e sinaliza conciliação manual."""
    from core.auditoria import registrar_auditoria

    logger.error(
        "Pagamento aprovado para pedido cancelado %s; conciliação manual "
        "necessária (id externo=%s).",
        pedido.numero,
        id_externo,
    )
    _atualizar_pagamento_aprovado(pedido, id_externo=id_externo)
    registrar_auditoria(
        acao="pedido.pagamento_apos_cancelamento",
        instancia=pedido,
        request=request,
        depois={
            "status": pedido.status,
            "status_financeiro": pedido.status_financeiro,
            "id_externo": id_externo,
        },
    )


@transaction.atomic
def reconciliar_pedido_financeiro(
    pedido: Pedido, *, justificativa: str, request=None, origem="manual"
) -> Pedido:
    """Marca prova financeira legada após conciliação humana explícita."""
    if not justificativa.strip():
        raise ValidationError("Justificativa é obrigatória.")
    pedido = _pedido_bloqueado(pedido)
    if pedido.status_financeiro != Pedido.StatusFinanceiro.PAGO:
        raise ValidationError(
            "Só é possível reconciliar pedido com financeiro pago."
        )
    antes = {"financeiro_conciliado": pedido.financeiro_conciliado}
    pedido.financeiro_conciliado = True
    pedido.save(update_fields=["financeiro_conciliado", "atualizado_em"])
    from core.auditoria import registrar_auditoria

    registrar_auditoria(
        acao="pedido.financeiro_reconciliado",
        instancia=pedido,
        request=request,
        antes=antes,
        depois={
            "financeiro_conciliado": True,
            "justificativa": justificativa.strip()[:500],
            "origem": origem,
        },
    )
    return pedido


def _liberar_reservas_do_pedido(
    pedido: Pedido, *, request=None, usuario=None, motivo: str = "cancelamento"
) -> int:
    """Libera somente reservas ativas do próprio pedido."""
    reservas = list(
        _travar_reservas(
            pedido.reservas.filter(
                status=ReservaEstoque.Status.ATIVA
            )
            .select_related("produto")
            .order_by("produto_id", "pk")
        )
    )
    itens_liberados = []
    for reserva in reservas:
        liberar_reserva(reserva)
        itens_liberados.append(
            {
                "produto": reserva.produto.nome,
                "quantidade": str(reserva.quantidade),
            }
        )
    if itens_liberados:
        from core.auditoria import registrar_auditoria

        registrar_auditoria(
            acao="pedido.reservas_liberadas",
            instancia=pedido,
            request=request,
            usuario=usuario,
            depois={
                "status": pedido.status,
                "motivo": motivo,
                "itens": itens_liberados,
            },
        )
    return len(itens_liberados)


def _cancelar_obrigacoes_estoque(pedido: Pedido) -> None:
    pedido.obrigacoes_estoque.filter(
        status=ObrigacaoEstoquePedido.Status.PENDENTE
    ).update(
        status=ObrigacaoEstoquePedido.Status.CANCELADA,
        tipo_pendencia=ObrigacaoEstoquePedido.TipoPendencia.NENHUMA,
        motivo_pendencia="pedido cancelado antes da baixa",
    )


def _obrigacao_por_movimento(movimento):
    """Resolve obrigação de movimento legado criado antes do vínculo FK."""
    if movimento.obrigacao_id:
        return movimento.obrigacao
    match = re.search(r"\b(PF\d+)\b", movimento.motivo or "")
    if not match:
        return None
    pedido = Pedido.objects.filter(numero=match.group(1)).first()
    if pedido is None:
        return None
    return ObrigacaoEstoquePedido.objects.filter(
        pedido=pedido,
        produto_id=movimento.produto_id,
        unidade_id=movimento.unidade_id,
    ).first()


def _devolver_estoque_do_pedido(
    pedido: Pedido, *, usuario=None, motivo: str, request=None
) -> int:
    """Compensa somente quantidades com baixa/evidência comprovada.

    Sem obrigação ou sem evidência, registra pendência e não altera saldo.
    O saldo é alterado exclusivamente por movimento de ledger.
    """
    por_produto = {}
    for item in pedido.itens.select_related("produto"):
        dados = por_produto.setdefault(
            item.produto_id,
            {"produto": item.produto, "quantidade": Decimal("0.00")},
        )
        dados["quantidade"] += Decimal(item.quantidade)

    devolvidos = 0
    for produto_id in sorted(por_produto):
        dados = por_produto[produto_id]
        obrigacao = ObrigacaoEstoquePedido.objects.filter(
            pedido=pedido,
            produto_id=produto_id,
            unidade_id=pedido.unidade_id,
        ).first()
        if obrigacao is None:
            _registrar_pendencia_estoque(
                pedido,
                produto=dados["produto"],
                quantidade=dados["quantidade"],
                motivo=(
                    "devolução sem obrigação/evidência de baixa; "
                    "estoque mantido para conciliação"
                ),
                request=request,
            )
            continue
        vinculados = (
            MovimentoEstoque.objects.filter(
                obrigacao=obrigacao,
                tipo=MovimentoEstoque.Tipo.ENTRADA_DEVOLUCAO,
            ).aggregate(total=Sum("delta"))["total"]
            or Decimal("0.00")
        )
        legados = list(
            MovimentoEstoque.objects.filter(
                obrigacao__isnull=True,
                tipo=MovimentoEstoque.Tipo.ENTRADA_DEVOLUCAO,
                produto_id=obrigacao.produto_id,
                unidade_id=obrigacao.unidade_id,
            )
        )
        nao_atribuidos = [
            movimento
            for movimento in legados
            if _obrigacao_por_movimento(movimento) is None
        ]
        if nao_atribuidos:
            _registrar_pendencia_estoque(
                pedido,
                produto=dados["produto"],
                quantidade=sum(
                    (movimento.delta for movimento in nao_atribuidos),
                    Decimal("0.00"),
                ),
                motivo=(
                    "movimento legado de devolução sem atribuição de pedido; "
                    "conciliação obrigatória antes de novo crédito"
                ),
                request=request,
            )
            continue
        compensado = vinculados + sum(
            (
                movimento.delta
                for movimento in legados
                if _obrigacao_por_movimento(movimento) == obrigacao
            ),
            Decimal("0.00"),
        )
        comprovado = min(
            obrigacao.quantidade_baixada,
            obrigacao.evidencia_baixada,
        )
        quantidade = comprovado - compensado
        if quantidade <= 0:
            if comprovado <= 0:
                _registrar_pendencia_estoque(
                    pedido,
                    produto=dados["produto"],
                    quantidade=dados["quantidade"],
                    motivo=(
                        "devolução sem baixa/evidência comprovada; "
                        "estoque mantido para conciliação"
                    ),
                    request=request,
                )
            continue
        registrar_movimento(
            produto=dados["produto"],
            unidade=pedido.unidade,
            tipo=MovimentoEstoque.Tipo.ENTRADA_DEVOLUCAO,
            delta=quantidade,
            motivo=motivo,
            usuario=usuario,
            request=request,
            obrigacao=obrigacao,
        )
        devolvidos += 1
    return devolvidos


@transaction.atomic
def estornar_pagamento(
    pagamento: Pagamento,
    *,
    status_pedido: str = Pedido.StatusFinanceiro.ESTORNADO,
    motivo: str = "",
    usuario=None,
    request=None,
) -> Pedido:
    """Estorna o pagamento e registra a data do evento financeiro."""
    # Ordem global: pedido -> pagamento (evita deadlock com cancelamentos).
    pedido = Pedido.objects.select_for_update().get(pk=pagamento.pedido_id)
    pagamento = Pagamento.objects.select_for_update().get(pk=pagamento.pk)
    if pagamento.status not in (
        Pagamento.Status.APROVADO,
        Pagamento.Status.CANCELADO,
    ):
        raise ValidationError("Somente pagamento aprovado pode ser estornado.")
    if pagamento.status == Pagamento.Status.APROVADO:
        pagamento.status = Pagamento.Status.CANCELADO
        pagamento.estornado_em = timezone.now()
        pagamento.save(update_fields=["status", "estornado_em"])
    elif (
        pagamento.status == Pagamento.Status.CANCELADO
        and pagamento.estornado_em is None
    ):
        pagamento.estornado_em = timezone.now()
        pagamento.save(update_fields=["estornado_em"])
    if pedido.status_financeiro != status_pedido:
        pedido.definir_status_financeiro(
            status_pedido,
            request=request,
            usuario=usuario,
            motivo=motivo or "estorno do pagamento",
        )
    from core.auditoria import registrar_auditoria

    registrar_auditoria(
        acao="pedido.pagamento_estornado",
        instancia=pedido,
        request=request,
        usuario=usuario,
        depois={
            "pagamento_id": pagamento.pk,
            "status_pagamento": pagamento.status,
            "estornado_em": (
                pagamento.estornado_em.isoformat()
                if pagamento.estornado_em
                else None
            ),
            "status_financeiro": pedido.status_financeiro,
            "motivo": (motivo or "")[:500],
        },
    )
    return pedido


@transaction.atomic
def cancelar_pedido_padrao(
    *, pedido: Pedido, justificativa: str, usuario, request=None
) -> Pedido:
    """Cancelamento em até 24h, sem mercadoria enviada."""
    if not (justificativa or "").strip():
        raise ValidationError("Justificativa é obrigatória.")
    if usuario is None or getattr(usuario, "pk", None) is None:
        raise ValidationError("Usuário responsável é obrigatório.")
    pedido = _pedido_bloqueado(pedido)
    if pedido.tipo_cancelamento == Pedido.TipoCancelamento.PADRAO:
        # Permite conciliar evidência que tenha chegado depois do cancelamento,
        # sem segundo estorno nem novo cancelamento.
        _devolver_estoque_do_pedido(
            pedido,
            usuario=usuario,
            motivo=f"Conciliação de cancelamento {pedido.numero}",
            request=request,
        )
        return pedido
    if pedido.tipo_cancelamento == Pedido.TipoCancelamento.DEVOLUCAO:
        raise ValidationError("Pedido já possui devolução registrada.")
    if pedido.status in (Pedido.Status.ENVIADO, Pedido.Status.CONCLUIDO):
        raise ValidationError(
            f"Pedido {pedido.status} não pode usar o cancelamento padrão."
        )

    pagamento = getattr(pedido, "pagamento", None)
    if (
        pedido.status_financeiro != Pedido.StatusFinanceiro.PAGO
        or pagamento is None
        or pagamento.status != Pagamento.Status.APROVADO
        or pagamento.aprovado_em is None
    ):
        raise ValidationError(
            "Cancelamento padrão exige pagamento aprovado e financeiro pago."
        )
    horas = (timezone.now() - pagamento.aprovado_em).total_seconds() / 3600
    if horas > 24:
        raise ValidationError(
            "Cancelamento padrão só é permitido em até 24 horas da aprovação."
        )

    nota = pedido.nota_fiscal
    if nota is not None and nota.status == "autorizada":
        from fiscal.services import cancelar_nota_fiscal

        cancelar_nota_fiscal(
            nota,
            motivo=f"Cancelamento padrão do pedido {pedido.numero}: "
            f"{justificativa.strip()[:300]}",
            usuario=usuario,
            request=request,
        )

    _devolver_estoque_do_pedido(
        pedido,
        usuario=usuario,
        motivo=f"Cancelamento padrão do pedido {pedido.numero}",
        request=request,
    )
    _liberar_reservas_do_pedido(
        pedido,
        request=request,
        usuario=usuario,
        motivo="cancelamento padrão",
    )
    _cancelar_obrigacoes_estoque(pedido)
    estornar_pagamento(
        pagamento,
        status_pedido=Pedido.StatusFinanceiro.CANCELADO,
        motivo=f"cancelamento padrão: {justificativa.strip()[:300]}",
        usuario=usuario,
        request=request,
    )

    pedido.tipo_cancelamento = Pedido.TipoCancelamento.PADRAO
    pedido.justificativa_cancelamento = justificativa.strip()
    pedido.cancelado_em = timezone.now()
    pedido.cancelado_por = usuario
    pedido.save(
        update_fields=[
            "tipo_cancelamento",
            "justificativa_cancelamento",
            "cancelado_em",
            "cancelado_por",
            "atualizado_em",
        ]
    )
    if pedido.status != Pedido.Status.CANCELADO:
        permitidos = pedido.TRANSICOES_VALIDAS.get(pedido.status, set())
        if Pedido.Status.CANCELADO in permitidos:
            pedido.transicionar(
                Pedido.Status.CANCELADO, request=request, usuario=usuario
            )
        else:
            from core.auditoria import auditar_atomicamente

            status_anterior = pedido.status
            pedido.status = Pedido.Status.CANCELADO
            auditar_atomicamente(
                acao="pedido.status_alterado",
                instancia=pedido,
                request=request,
                usuario=usuario,
                antes={"status": status_anterior},
                depois={"status": Pedido.Status.CANCELADO},
                salvar=lambda: pedido.save(
                    update_fields=["status", "atualizado_em"]
                ),
            )

    from core.auditoria import registrar_auditoria

    registrar_auditoria(
        acao="pedido.cancelado_padrao",
        instancia=pedido,
        request=request,
        usuario=usuario,
        depois={
            "status": pedido.status,
            "status_financeiro": pedido.status_financeiro,
            "tipo_cancelamento": pedido.tipo_cancelamento,
            "justificativa": justificativa.strip()[:500],
        },
    )
    return pedido


@transaction.atomic
def registrar_devolucao(
    *, pedido: Pedido, justificativa: str, usuario, request=None
):
    """Devolução após entrega/24h, com NF-e de entrada e retorno físico."""
    from fiscal.models import NotaFiscal
    from fiscal.services import calcular_cfop_inverso

    if not (justificativa or "").strip():
        raise ValidationError("Justificativa é obrigatória.")
    if usuario is None or getattr(usuario, "pk", None) is None:
        raise ValidationError("Usuário responsável é obrigatório.")
    pedido = _pedido_bloqueado(pedido)
    existente = pedido.notas_fiscais.filter(
        tipo=NotaFiscal.Tipo.ENTRADA
    ).first()
    if pedido.tipo_cancelamento == Pedido.TipoCancelamento.DEVOLUCAO:
        # Segunda chamada reconcilia apenas evidência física faltante.
        _devolver_estoque_do_pedido(
            pedido,
            usuario=usuario,
            motivo=f"Conciliação de devolução {pedido.numero}",
            request=request,
        )
        return existente
    pagamento = getattr(pedido, "pagamento", None)
    if pagamento is None or pagamento.aprovado_em is None:
        raise ValidationError(
            "Devolução exige histórico de pagamento aprovado."
        )
    if pedido.status_financeiro == Pedido.StatusFinanceiro.PAGO:
        if pagamento.status != Pagamento.Status.APROVADO:
            raise ValidationError(
                "Devolução exige pagamento aprovado e conciliado."
            )
    elif pedido.status_financeiro in (
        Pedido.StatusFinanceiro.ESTORNADO,
        Pedido.StatusFinanceiro.CANCELADO,
    ):
        if (
            pagamento.status != Pagamento.Status.CANCELADO
            or pagamento.estornado_em is None
        ):
            raise ValidationError(
                "Devolução após estorno exige estorno confirmado."
            )
    else:
        raise ValidationError(
            "Devolução exige pagamento aprovado ou estorno confirmado."
        )
    nota_saida = pedido.nota_fiscal
    if nota_saida is None or nota_saida.status != "autorizada":
        raise ValidationError(
            "NF-e de saída autorizada é obrigatória para registrar devolução."
        )
    chave_saida = (nota_saida.chave_acesso or "").strip()
    if len(chave_saida) != 44 or not chave_saida.isdigit():
        raise ValidationError(
            "A NF-e de saída deve ter chave de acesso de 44 dígitos."
        )
    cfop_inverso = calcular_cfop_inverso(nota_saida.cfop)
    nota_entrada = existente
    if nota_entrada is None:
        nota_entrada = NotaFiscal(
            pedido=pedido,
            tipo=NotaFiscal.Tipo.ENTRADA,
            cfop=cfop_inverso,
            chave_referenciada=chave_saida,
            status=NotaFiscal.Status.PENDENTE,
        )
        nota_entrada.full_clean()
        nota_entrada.save()

    _devolver_estoque_do_pedido(
        pedido,
        usuario=usuario,
        motivo=f"Devolução do pedido {pedido.numero}: "
        f"{justificativa.strip()[:300]}",
        request=request,
    )
    _liberar_reservas_do_pedido(
        pedido,
        request=request,
        usuario=usuario,
        motivo="devolução",
    )
    _cancelar_obrigacoes_estoque(pedido)
    if (
        pedido.status_financeiro == Pedido.StatusFinanceiro.PAGO
        and pagamento.status == Pagamento.Status.APROVADO
    ):
        estornar_pagamento(
            pagamento,
            status_pedido=Pedido.StatusFinanceiro.ESTORNADO,
            motivo=f"devolução: {justificativa.strip()[:300]}",
            usuario=usuario,
            request=request,
        )

    pedido.tipo_cancelamento = Pedido.TipoCancelamento.DEVOLUCAO
    pedido.justificativa_cancelamento = justificativa.strip()
    pedido.cancelado_em = timezone.now()
    pedido.cancelado_por = usuario
    pedido.save(
        update_fields=[
            "tipo_cancelamento",
            "justificativa_cancelamento",
            "cancelado_em",
            "cancelado_por",
            "atualizado_em",
        ]
    )

    from core.auditoria import registrar_auditoria

    registrar_auditoria(
        acao="pedido.devolucao_registrada",
        instancia=pedido,
        request=request,
        usuario=usuario,
        depois={
            "tipo_cancelamento": pedido.tipo_cancelamento,
            "justificativa": justificativa.strip()[:500],
            "nota_entrada_id": nota_entrada.pk,
            "cfop": nota_entrada.cfop,
            "chave_referenciada": nota_entrada.chave_referenciada,
        },
    )
    return nota_entrada


@transaction.atomic
def cancelar_pedido(
    pedido: Pedido, *, request=None, usuario=None, permitir_pago: bool = True
) -> Pedido:
    """Cancela liberando reservas quando aplicável (idempotente).

    Re-lê o pedido sob lock; ``permitir_pago=False`` é usado pela expiração
    para nunca cancelar um pedido que foi pago concorrentemente.
    Pedido com financeiro PAGO permanece com esse status: o cancelamento
    operacional não presume estorno. O caso é auditado para conciliação.
    """
    pedido = _pedido_bloqueado(pedido)
    if not permitir_pago and pedido.status_financeiro == (
        Pedido.StatusFinanceiro.PAGO
    ):
        logger.info(
            "Pedido %s está pago; expiração/cancelamento automático ignorado.",
            pedido.numero,
        )
        return pedido
    if pedido.status in (Pedido.Status.CANCELADO, Pedido.Status.CONCLUIDO):
        if (
            pedido.status == Pedido.Status.CANCELADO
            and pedido.status_financeiro == Pedido.StatusFinanceiro.PENDENTE
        ):
            _liberar_reservas_do_pedido(
                pedido,
                request=request,
                usuario=usuario,
                motivo="reparo de pedido já cancelado",
            )
            _cancelar_obrigacoes_estoque(pedido)
        logger.info(
            "Pedido %s não pode ser cancelado a partir de %s.",
            pedido.numero,
            pedido.status,
        )
        return pedido

    financeiro_anterior = pedido.status_financeiro
    pedido.transicionar(Pedido.Status.CANCELADO, request=request, usuario=usuario)

    if financeiro_anterior == Pedido.StatusFinanceiro.PENDENTE:
        pedido.definir_status_financeiro(
            Pedido.StatusFinanceiro.CANCELADO,
            request=request,
            usuario=usuario,
            motivo="pedido cancelado antes do pagamento",
        )
        pagamento = getattr(pedido, "pagamento", None)
        if pagamento and pagamento.status == Pagamento.Status.PENDENTE:
            pagamento.status = Pagamento.Status.CANCELADO
            pagamento.save(update_fields=["status"])
            from core.auditoria import registrar_auditoria

            registrar_auditoria(
                acao="pedido.pagamento_cancelado",
                instancia=pedido,
                request=request,
                usuario=usuario,
                depois={"pagamento_id": pagamento.pk, "status": pagamento.status},
            )
    elif financeiro_anterior == Pedido.StatusFinanceiro.PAGO:
        from core.auditoria import registrar_auditoria

        registrar_auditoria(
            acao="pedido.cancelado_com_pagamento",
            instancia=pedido,
            request=request,
            usuario=usuario,
            depois={
                "status": pedido.status,
                "status_financeiro": pedido.status_financeiro,
                "motivo": "cancelamento após pagamento exige conciliação",
            },
        )
        reserva_ativa = (
            pedido.reservas.filter(status=ReservaEstoque.Status.ATIVA)
            .select_related("produto")
            .first()
        )
        if reserva_ativa is not None:
            _registrar_pendencia_estoque(
                pedido,
                produto=reserva_ativa.produto,
                quantidade=reserva_ativa.quantidade,
                motivo="cancelamento após pagamento com reserva ativa",
                request=request,
            )

    if financeiro_anterior == Pedido.StatusFinanceiro.PENDENTE:
        _liberar_reservas_do_pedido(
            pedido,
            request=request,
            usuario=usuario,
            motivo="cancelamento antes do pagamento",
        )
        _cancelar_obrigacoes_estoque(pedido)

    if pedido.cancelado_em is None:
        pedido.cancelado_em = timezone.now()
        pedido.save(update_fields=["cancelado_em", "atualizado_em"])

    from .emails import email_pedido_cancelado

    email_pedido_cancelado(pedido)
    return pedido


STATUS_PROVEDOR_PARA_PAGAMENTO = {
    "approved": Pagamento.Status.APROVADO,
    "refused": Pagamento.Status.RECUSADO,
    "rejected": Pagamento.Status.RECUSADO,
    "cancelled": Pagamento.Status.CANCELADO,
    "charged_back": Pagamento.Status.CANCELADO,
    "refunded": Pagamento.Status.CANCELADO,
    "pending": Pagamento.Status.PENDENTE,
    "in_process": Pagamento.Status.PENDENTE,
}


class ResultadoPagamentoInvalido(Exception):
    """Resposta do provedor não corresponde ao contrato local da tentativa."""

    def __init__(self, motivo: str):
        self.motivo = motivo
        super().__init__(motivo)


def _validar_contrato_pagamento(
    pedido: Pedido, dados_consulta: dict, *, id_consultado=None
) -> Pagamento:
    """Valida tentativa local, ID, valor, moeda, recebedor e ambiente."""
    pagamento = getattr(pedido, "pagamento", None)
    if pagamento is None:
        raise ResultadoPagamentoInvalido(
            "pedido não possui tentativa de pagamento local"
        )
    if pagamento.valor != pedido.total:
        raise ResultadoPagamentoInvalido(
            "tentativa local com valor divergente do pedido"
        )

    id_retornado = str(dados_consulta.get("id") or "").strip()
    if not id_retornado:
        raise ResultadoPagamentoInvalido("resposta sem id de pagamento")
    if id_consultado not in (None, "") and id_retornado != str(id_consultado):
        raise ResultadoPagamentoInvalido(
            "id retornado difere do recurso consultado"
        )
    if pagamento.id_externo and pagamento.id_externo != id_retornado:
        raise ResultadoPagamentoInvalido(
            "tentativa local pertence a outro id externo"
        )

    external_reference = str(
        dados_consulta.get("external_reference") or ""
    ).strip()
    if external_reference != pedido.numero:
        raise ResultadoPagamentoInvalido(
            "external_reference não corresponde ao pedido"
        )

    valor_bruto = dados_consulta.get("transaction_amount")
    if valor_bruto is None:
        raise ResultadoPagamentoInvalido("resposta sem valor")
    try:
        valor = Decimal(str(valor_bruto))
    except (InvalidOperation, TypeError, ValueError) as erro:
        raise ResultadoPagamentoInvalido("valor inválido") from erro
    if valor != pedido.total:
        raise ResultadoPagamentoInvalido(
            f"valor divergente: provedor={valor}, pedido={pedido.total}"
        )

    moeda = str(dados_consulta.get("currency_id") or "").strip().upper()
    if moeda != "BRL":
        raise ResultadoPagamentoInvalido(f"moeda divergente: {moeda or 'ausente'}")

    collector = str(dados_consulta.get("collector_id") or "").strip()
    collector_configurado = str(
        getattr(settings, "MERCADO_PAGO_COLLECTOR_ID", "") or ""
    ).strip()
    if collector_configurado:
        if collector != collector_configurado:
            raise ResultadoPagamentoInvalido("recebedor divergente")
    elif not getattr(settings, "MERCADO_PAGO_FAKE", False):
        raise ResultadoPagamentoInvalido("recebedor não configurado")

    if "live_mode" in dados_consulta:
        live_mode = dados_consulta.get("live_mode")
        if isinstance(live_mode, str):
            live_mode = live_mode.strip().lower() == "true"
        if bool(live_mode) != bool(
            getattr(settings, "MERCADO_PAGO_LIVE_MODE", False)
        ):
            raise ResultadoPagamentoInvalido("ambiente (live_mode) divergente")
    elif not getattr(settings, "MERCADO_PAGO_FAKE", False):
        raise ResultadoPagamentoInvalido("resposta sem live_mode")

    return pagamento


def _registrar_contrato_invalido(
    pedido: Pedido, dados_consulta: dict, erro: ResultadoPagamentoInvalido, request
) -> None:
    from core.auditoria import registrar_auditoria

    registrar_auditoria(
        acao="pedido.pagamento_contrato_invalido",
        instancia=pedido,
        request=request,
        depois={
            "motivo": erro.motivo[:300],
            "id_retornado": str(dados_consulta.get("id") or "")[:80],
            "external_reference": str(
                dados_consulta.get("external_reference") or ""
            )[:30],
            "status_provedor": str(
                dados_consulta.get("status") or ""
            )[:30],
        },
    )


def _atualizar_pagamento_resultado(
    pedido: Pedido, *, status_provedor: str, id_externo: str
) -> None:
    pagamento = getattr(pedido, "pagamento", None)
    novo_status = STATUS_PROVEDOR_PARA_PAGAMENTO.get(status_provedor)
    if pagamento is None or novo_status is None:
        return
    if (
        pagamento.status == Pagamento.Status.APROVADO
        and status_provedor not in ("charged_back", "refunded")
    ):
        return
    if novo_status == Pagamento.Status.PENDENTE and pagamento.status in (
        Pagamento.Status.APROVADO,
        Pagamento.Status.RECUSADO,
        Pagamento.Status.CANCELADO,
    ):
        return
    estava_aprovado = pagamento.status == Pagamento.Status.APROVADO
    pagamento.status = novo_status
    pagamento.id_externo = id_externo or pagamento.id_externo
    campos = ["status", "id_externo"]
    if (
        novo_status == Pagamento.Status.CANCELADO
        and estava_aprovado
        and pagamento.estornado_em is None
    ):
        pagamento.estornado_em = timezone.now()
        campos.append("estornado_em")
    pagamento.save(update_fields=campos)


def _registrar_resultado_financeiro(
    pedido: Pedido, *, acao: str, status_provedor: str,
    id_externo: str, request,
) -> None:
    from core.auditoria import registrar_auditoria

    registrar_auditoria(
        acao=acao,
        instancia=pedido,
        request=request,
        depois={
            "status_provedor": status_provedor,
            "status": pedido.status,
            "status_financeiro": pedido.status_financeiro,
            "id_externo": id_externo,
        },
    )


def _aplicar_resultado_valido(
    pedido: Pedido,
    dados_consulta: dict,
    *,
    request,
    status_provedor: str,
    id_externo: str,
) -> Pedido:
    """Aplica um resultado já validado, com o pedido bloqueado pelo chamador."""
    if status_provedor == "approved":
        ja_estava_pago = (
            pedido.status_financeiro == Pedido.StatusFinanceiro.PAGO
        )
        pedido = marcar_pagamento_aprovado(
            pedido, id_externo=id_externo, request=request
        )
        if (
            not ja_estava_pago
            and pedido.status_financeiro == Pedido.StatusFinanceiro.PAGO
        ):
            from .emails import email_pagamento_aprovado

            email_pagamento_aprovado(pedido)
        return pedido

    _atualizar_pagamento_resultado(
        pedido, status_provedor=status_provedor, id_externo=id_externo
    )

    if status_provedor in ("charged_back", "refunded"):
        if pedido.status_financeiro != Pedido.StatusFinanceiro.PAGO:
            logger.warning(
                "Chargeback sem pagamento aprovado no pedido %s.",
                pedido.numero,
            )
            _registrar_resultado_financeiro(
                pedido,
                acao="pedido.pagamento_estorno_inconsistente",
                status_provedor=status_provedor,
                id_externo=id_externo,
                request=request,
            )
            return pedido
        pedido.definir_status_financeiro(
            Pedido.StatusFinanceiro.ESTORNADO,
            request=request,
            motivo="chargeback do provedor",
        )
        if pedido.status in (
            Pedido.Status.RASCUNHO,
            Pedido.Status.AGUARDANDO_PAGAMENTO,
            Pedido.Status.PAGAMENTO_PENDENTE,
            Pedido.Status.PAGO,
            Pedido.Status.FALHOU,
        ):
            try:
                pedido.transicionar(Pedido.Status.CANCELADO, request=request)
            except ValidationError:
                logger.error(
                    "Chargeback no pedido %s em %s; cancelamento operacional "
                    "exige revisão manual.",
                    pedido.numero,
                    pedido.status,
                )
                _registrar_resultado_financeiro(
                    pedido,
                    acao="pedido.estorno_com_andamento",
                    status_provedor=status_provedor,
                    id_externo=id_externo,
                    request=request,
                )
        else:
            _registrar_resultado_financeiro(
                pedido,
                acao="pedido.estorno_com_andamento",
                status_provedor=status_provedor,
                id_externo=id_externo,
                request=request,
            )
        _registrar_resultado_financeiro(
            pedido,
            acao="pedido.pagamento_estornado",
            status_provedor=status_provedor,
            id_externo=id_externo,
            request=request,
        )
        return pedido

    if status_provedor in ("refused", "rejected", "cancelled"):
        if pedido.status_financeiro == Pedido.StatusFinanceiro.PAGO:
            logger.warning(
                "Evento %s ignorado: pedido %s já está pago.",
                status_provedor,
                pedido.numero,
            )
            _registrar_resultado_financeiro(
                pedido,
                acao="pedido.pagamento_evento_ignorado",
                status_provedor=status_provedor,
                id_externo=id_externo,
                request=request,
            )
            return pedido
        if pedido.status in (
            Pedido.Status.EM_SEPARACAO,
            Pedido.Status.PRONTO_PARA_ENTREGA,
            Pedido.Status.ENVIADO,
            Pedido.Status.CONCLUIDO,
        ):
            logger.warning(
                "Evento %s ignorado: pedido %s já está em andamento (%s).",
                status_provedor,
                pedido.numero,
                pedido.status,
            )
            _registrar_resultado_financeiro(
                pedido,
                acao="pedido.pagamento_evento_ignorado",
                status_provedor=status_provedor,
                id_externo=id_externo,
                request=request,
            )
            return pedido
        pedido = cancelar_pedido(pedido, request=request)
        _registrar_resultado_financeiro(
            pedido,
            acao=(
                "pedido.pagamento_recusado"
                if status_provedor in ("refused", "rejected")
                else "pedido.pagamento_cancelado"
            ),
            status_provedor=status_provedor,
            id_externo=id_externo,
            request=request,
        )
        return pedido

    if status_provedor in ("pending", "in_process"):
        if (
            pedido.status_financeiro != Pedido.StatusFinanceiro.PENDENTE
            or pedido.status
            in (
                Pedido.Status.CANCELADO,
                Pedido.Status.CONCLUIDO,
            )
        ):
            logger.warning(
                "Evento %s ignorado: pedido %s está em %s/%s.",
                status_provedor,
                pedido.numero,
                pedido.status,
                pedido.status_financeiro,
            )
            _registrar_resultado_financeiro(
                pedido,
                acao="pedido.pagamento_evento_ignorado",
                status_provedor=status_provedor,
                id_externo=id_externo,
                request=request,
            )
            return pedido
        pedido.definir_status_financeiro(
            Pedido.StatusFinanceiro.PENDENTE,
            request=request,
            motivo=f"provedor informou {status_provedor}",
        )
        _registrar_resultado_financeiro(
            pedido,
            acao="pedido.pagamento_pendente",
            status_provedor=status_provedor,
            id_externo=id_externo,
            request=request,
        )
        return pedido

    if status_provedor == "in_mediation":
        _registrar_resultado_financeiro(
            pedido,
            acao="pedido.pagamento_em_mediacao",
            status_provedor=status_provedor,
            id_externo=id_externo,
            request=request,
        )
        return pedido

    _registrar_resultado_financeiro(
        pedido,
        acao="pedido.pagamento_status_desconhecido",
        status_provedor=status_provedor,
        id_externo=id_externo,
        request=request,
    )
    return pedido


def aplicar_resultado_pagamento(
    dados_consulta: dict, *, request=None, id_consultado=None
) -> Pedido | None:
    """Valida o contrato e aplica o resultado sob lock.

    R1/PAY-02: divergência de tentativa/ID/valor/moeda/recebedor/ambiente
    não altera pedido, pagamento ou estoque; gera LogAuditoria e levanta
    ``ResultadoPagamentoInvalido`` após commitar a ocorrência.
    """
    numero = str(dados_consulta.get("external_reference") or "")
    status_provedor = str(dados_consulta.get("status") or "")
    id_externo = str(dados_consulta.get("id") or "")

    pedido_inicial = Pedido.objects.filter(numero=numero).first()
    if pedido_inicial is None:
        logger.warning("Notificação sem pedido correspondente: %s", numero)
        return None

    erro_contrato = None
    resultado = None
    with transaction.atomic():
        pedido = Pedido.objects.select_for_update().get(pk=pedido_inicial.pk)
        try:
            _validar_contrato_pagamento(
                pedido, dados_consulta, id_consultado=id_consultado
            )
        except ResultadoPagamentoInvalido as erro:
            logger.error(
                "Resultado de pagamento inválido para %s: %s",
                pedido.numero,
                erro.motivo,
            )
            _registrar_contrato_invalido(
                pedido, dados_consulta, erro, request
            )
            erro_contrato = erro
        else:
            resultado = _aplicar_resultado_valido(
                pedido,
                dados_consulta,
                request=request,
                status_provedor=status_provedor,
                id_externo=id_externo,
            )

    if erro_contrato is not None:
        raise erro_contrato
    return resultado
