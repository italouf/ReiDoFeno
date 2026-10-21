"""Reconstrução de obrigações de estoque a partir de evidência histórica.

A função recebe as classes de modelo (históricas em migrations, atuais no
comando) e não importa modelos de runtime. Ela não cria movimentos nem altera
ledger: apenas calcula a baixa atribuível e devolve o estado para persistência.
"""

import re
from decimal import Decimal

TIPOS_BAIXA = ("baixa_definitiva", "saida")
PADRAO_PEDIDO = re.compile(r"\bPF\d+\b")


def reconstruir_obrigacao_evidencia(obrigacao, *, Pedido, Movimento) -> dict:
    """Calcula a baixa histórica atribuível a uma obrigação.

    Evidência preferencial: FK ``movimento.obrigacao``. Para o legado sem FK,
    aceita movimento de baixa cujo ``motivo`` contenha **exatamente um** número
    de pedido igual ao da obrigação. Motivo com múltiplos pedidos é ambíguo e
    não é contado.
    """
    pedido = Pedido.objects.get(pk=obrigacao.pedido_id)
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
        if movimento.obrigacao_id is not None:
            if movimento.obrigacao_id != obrigacao.pk:
                continue
            origem = "fk"
        else:
            numeros = set(PADRAO_PEDIDO.findall(movimento.motivo or ""))
            if len(numeros) != 1:
                if numeros:
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
    elif total > devida:
        baixada = devida
        status = "pendente"
        motivo = "evidência histórica excede a obrigação; revisar"
    elif total == devida:
        baixada = total
        status = "resolvida"
        motivo = ""
    else:
        baixada = total
        status = "pendente"
        motivo = (
            "baixa histórica não comprovada"
            if total == 0
            else f"baixa histórica parcial ({total} de {devida})"
        )

    return {
        "quantidade_baixada": baixada,
        "evidencia_baixada": total,
        "status": status,
        "motivo_pendencia": motivo,
        "evidencia_detalhe": {
            "movimentos": evidencias,
            "ambiguos": ambiguos,
            "origem": "reconstrucao_historica",
        },
    }
