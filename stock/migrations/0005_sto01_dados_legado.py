"""STO-01: cálculo do delta legado com evidência e baseline explícita."""

from decimal import Decimal, InvalidOperation

from django.db import migrations

TIPOS_POSITIVOS = (
    "entrada",
    "entrada_inicial",
    "transferencia_entrada",
    "ajuste_positivo",
)
TIPOS_NEGATIVOS = (
    "saida",
    "transferencia_saida",
    "ajuste_negativo",
    "baixa_definitiva",
)
MOTIVO_BASELINE = (
    "[STO-01] Baseline de abertura/reconciliação do saldo legado"
)


def _decimal(valor):
    try:
        numero = Decimal(str(valor))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return numero if numero.is_finite() else None


def _delta_do_movimento(Movimento, LogAuditoria, movimento, Reconciliacao):
    tipo = movimento.tipo
    quantidade = abs(Decimal(movimento.quantidade))
    if tipo in TIPOS_POSITIVOS:
        return quantidade
    if tipo in TIPOS_NEGATIVOS:
        return -quantidade
    if tipo == "ajuste":
        log = (
            LogAuditoria.objects.filter(
                acao="estoque.ajuste_manual", objeto_id=str(movimento.pk)
            )
            .order_by("-criado_em")
            .first()
        )
        if log and log.antes and log.depois:
            antes = _decimal(log.antes.get("saldo_anterior"))
            depois = _decimal(log.depois.get("saldo_novo"))
            if antes is not None and depois is not None:
                delta = depois - antes
                if delta != 0:
                    return delta
        Reconciliacao.objects.create(
            produto_id=movimento.produto_id,
            unidade_id=movimento.unidade_id,
            movimento_id=movimento.pk,
            tipo="ajuste_sem_prova",
            quantidade=quantidade,
            detalhe={
                "tipo_original": tipo,
                "quantidade_original": str(movimento.quantidade),
                "delta_atribuido": str(-quantidade),
                "prova": "ausente",
            },
        )
        return -quantidade
    if tipo == "transferencia":
        sinal = quantidade
        par = movimento.movimento_par_id
        if par:
            contraparte = Movimento.objects.filter(pk=par).first()
            if contraparte is not None:
                if contraparte.tipo in TIPOS_POSITIVOS:
                    sinal = -quantidade
                elif contraparte.tipo in TIPOS_NEGATIVOS:
                    sinal = quantidade
        Reconciliacao.objects.create(
            produto_id=movimento.produto_id,
            unidade_id=movimento.unidade_id,
            movimento_id=movimento.pk,
            tipo="transferencia_ambigua",
            quantidade=quantidade,
            detalhe={
                "tipo_original": tipo,
                "movimento_par": par,
                "delta_atribuido": str(sinal),
                "prova": "inferida",
            },
        )
        return sinal
    return quantidade


def preparar_ledger(apps, schema_editor):
    Movimento = apps.get_model("stock", "MovimentoEstoque")
    Estoque = apps.get_model("stock", "Estoque")
    LogAuditoria = apps.get_model("core", "LogAuditoria")
    Reconciliacao = apps.get_model("stock", "ReconciliacaoEstoqueLegado")

    zeros = list(
        Movimento.objects.filter(delta=0, quantidade=0).values_list(
            "pk", flat=True
        )
    )
    if zeros:
        raise RuntimeError(
            "STO-01: movimentos com quantidade zero exigem revisão manual; "
            f"ids={zeros[:20]}. Nenhum delta foi inventado."
        )

    estoques_pares = set(
        Estoque.objects.values_list("produto_id", "unidade_id")
    )
    orfaos = [
        (produto_id, unidade_id)
        for produto_id, unidade_id in Movimento.objects.values_list(
            "produto_id", "unidade_id"
        ).distinct()
        if (produto_id, unidade_id) not in estoques_pares
    ]
    if orfaos:
        raise RuntimeError(
            "STO-01: movimentos sem linha de Estoque para (produto, unidade): "
            + ", ".join(str(par) for par in orfaos[:10])
        )

    tem_sentinela = Movimento.objects.filter(delta=0).exists()

    for estoque in Estoque.objects.all().iterator():
        movimentos = list(
            Movimento.objects.filter(
                produto_id=estoque.produto_id,
                unidade_id=estoque.unidade_id,
            ).order_by("criado_em", "pk")
        )
        processou = False
        total = Decimal("0.00")
        for movimento in movimentos:
            if movimento.delta == 0:
                delta = _delta_do_movimento(
                    Movimento, LogAuditoria, movimento, Reconciliacao
                )
                movimento.delta = delta
                movimento.quantidade = abs(delta)
                movimento.save(update_fields=["delta", "quantidade"])
                processou = True
            total += Decimal(movimento.delta)

        residual = Decimal(estoque.quantidade) - total
        if residual == 0:
            continue
        if not processou and movimentos and not tem_sentinela:
            raise RuntimeError(
                "STO-01: banco já migrado com divergência de ledger; "
                f"produto={estoque.produto_id}, unidade={estoque.unidade_id}, "
                f"saldo={estoque.quantidade}, ledger={total}. "
                "Reconciliação manual necessária."
            )
        tipo = (
            "entrada_inicial" if residual > 0 else "ajuste_negativo"
        )
        movimento = Movimento.objects.create(
            produto_id=estoque.produto_id,
            unidade_id=estoque.unidade_id,
            tipo=tipo,
            delta=residual,
            quantidade=abs(residual),
            motivo=MOTIVO_BASELINE,
        )
        Reconciliacao.objects.create(
            produto_id=estoque.produto_id,
            unidade_id=estoque.unidade_id,
            movimento_id=movimento.pk,
            tipo="baseline",
            quantidade=abs(residual),
            saldo_original=estoque.quantidade,
            saldo_calculado=total,
            detalhe={
                "residual": str(residual),
                "movimentos_processados": processou,
                "motivo": MOTIVO_BASELINE,
            },
        )


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0002_logauditoria"),
        ("sales", "0006_pagamento_criacao_expira_em_and_more"),
        ("stock", "0004_remediacao_quarentena"),
    ]

    operations = [
        migrations.RunPython(preparar_ledger, migrations.RunPython.noop),
    ]
