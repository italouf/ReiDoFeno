"""Reconstrução de obrigações de estoque a partir de evidência histórica.

A função recebe as classes de modelo (históricas em migrations, atuais no
comando) e não importa modelos de runtime. Ela não cria movimentos nem altera
ledger: apenas calcula a baixa atribuível e devolve o estado para persistência.
"""

import re
from decimal import Decimal

TIPOS_BAIXA = ("baixa_definitiva", "saida")
PADRAO_PEDIDO = re.compile(r"\bPF\d+\b")


def _decisoes_existentes(obrigacao):
    detalhe = dict(getattr(obrigacao, "evidencia_detalhe", {}) or {})
    conciliacoes = list(detalhe.get("conciliacoes", []))
    atribuidos = {}
    descartados = set()
    aceito_excesso = False
    for item in conciliacoes:
        if not isinstance(item, dict):
            continue
        decisao = item.get("decisao")
        movimento_id = item.get("movimento_id")
        try:
            movimento_id = int(movimento_id)
        except (TypeError, ValueError):
            movimento_id = None
        if decisao == "atribuir" and movimento_id is not None:
            atribuidos[movimento_id] = Decimal(
                str(item.get("quantidade") or "0.00")
            )
        elif decisao == "descartar" and movimento_id is not None:
            descartados.add(movimento_id)
        elif decisao == "aceitar_excesso":
            aceito_excesso = True
    return detalhe, conciliacoes, atribuidos, descartados, aceito_excesso


def reconstruir_obrigacao_evidencia(obrigacao, *, Pedido, Movimento) -> dict:
    """Calcula a baixa histórica atribuível a uma obrigação.

    Evidência preferencial: FK ``movimento.obrigacao``. Para o legado sem FK,
    aceita movimento de baixa cujo ``motivo`` contenha **exatamente um** número
    de pedido igual ao da obrigação. Motivo com o pedido atual e outro pedido é
    ambíguo e não é contado; motivo com apenas pedidos alheios não bloqueia este
    pedido.
    """
    pedido = Pedido.objects.get(pk=obrigacao.pedido_id)
    (
        detalhe_existente,
        conciliacoes,
        atribuidos,
        descartados,
        aceito_excesso,
    ) = _decisoes_existentes(obrigacao)
    movimentos = Movimento.objects.filter(
        produto_id=obrigacao.produto_id,
        unidade_id=obrigacao.unidade_id,
        tipo__in=TIPOS_BAIXA,
        delta__lt=0,
    ).order_by("pk")

    total = Decimal("0.00")
    evidencias = []
    ambiguos = []
    vistos = set()

    for movimento in movimentos:
        if movimento.pk in descartados and movimento.obrigacao_id is None:
            continue

        if movimento.pk in atribuidos:
            if (
                movimento.obrigacao_id is not None
                and movimento.obrigacao_id != obrigacao.pk
            ):
                continue
            quantidade = min(
                atribuidos[movimento.pk],
                abs(Decimal(movimento.delta)),
            )
            if quantidade <= 0 or movimento.pk in vistos:
                continue
            vistos.add(movimento.pk)
            total += quantidade
            evidencias.append(
                {
                    "movimento_id": movimento.pk,
                    "delta": str(movimento.delta),
                    "quantidade_atribuida": str(quantidade),
                    "origem": "manual",
                }
            )
            continue

        if movimento.obrigacao_id is not None:
            if movimento.obrigacao_id != obrigacao.pk:
                continue
            origem = "fk"
        else:
            numeros = set(PADRAO_PEDIDO.findall(movimento.motivo or ""))
            if len(numeros) != 1:
                if len(numeros) > 1 and pedido.numero in numeros:
                    ambiguos.append(movimento.pk)
                continue
            if numeros.pop() != pedido.numero:
                continue
            origem = "texto"

        if movimento.pk in vistos:
            continue
        vistos.add(movimento.pk)
        valor = abs(Decimal(movimento.delta))
        total += valor
        evidencias.append(
            {
                "movimento_id": movimento.pk,
                "delta": str(movimento.delta),
                "origem": origem,
            }
        )

    devida = Decimal(obrigacao.quantidade_devida)
    cancelado = (
        pedido.status == "cancelado"
        or pedido.status_financeiro in ("cancelado", "estornado")
    )
    if cancelado:
        baixada = min(total, devida)
        status = "cancelada"
        motivo = "pedido cancelado/estornado"
        tipo = ""
    elif aceito_excesso and total > devida and not ambiguos:
        baixada = devida
        status = "resolvida"
        motivo = ""
        tipo = ""
    elif total > devida:
        baixada = devida
        status = "pendente"
        motivo = "evidência histórica excede a obrigação; revisar"
        tipo = "excesso"
    elif ambiguos:
        baixada = min(total, devida)
        status = "pendente"
        motivo = "evidência histórica ambígua; conciliar"
        tipo = "ambigua"
    elif total == devida:
        baixada = total
        status = "resolvida"
        motivo = ""
        tipo = ""
    else:
        baixada = total
        status = "pendente"
        motivo = (
            "baixa histórica não comprovada"
            if total == 0
            else f"baixa histórica parcial ({total} de {devida})"
        )
        tipo = "falta"

    resultado = {
        "quantidade_baixada": baixada,
        "evidencia_baixada": total,
        "status": status,
        "motivo_pendencia": motivo,
        "evidencia_detalhe": {
            **detalhe_existente,
            "movimentos": evidencias,
            "ambiguos": ambiguos,
            "conciliacoes": conciliacoes,
            "origem": "reconstrucao_historica",
        },
    }
    if hasattr(obrigacao, "tipo_pendencia"):
        resultado["tipo_pendencia"] = tipo
    return resultado
