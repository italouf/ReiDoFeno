"""STO-01: delta assinado, reconciliação do legado e trigger PostgreSQL."""

from decimal import Decimal, InvalidOperation

from django.db import migrations, models

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
MOTIVO_RECONCILIACAO = "[STO-01] Reconciliação automática do saldo legado"


def _decimal(valor):
    try:
        return Decimal(str(valor))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _delta_do_movimento(Movimento, LogAuditoria, movimento):
    tipo = movimento.tipo
    quantidade = abs(Decimal(movimento.quantidade))
    if tipo in TIPOS_POSITIVOS:
        return quantidade
    if tipo in TIPOS_NEGATIVOS:
        return -quantidade
    if tipo == "ajuste":
        # O sinal original foi perdido. A auditoria da Fase 1 registrou o
        # saldo antes/depois; quando disponível, é a única prova do sinal.
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
        # Sem prova, assume saída (caso mais comum de ajuste manual) e deixa
        # a reconciliação abaixo corrigir o saldo agregado.
        return -quantidade
    # "transferencia" legado podia ser entrada ou saída.
    return _decimal(movimento.quantidade) or quantidade


def preparar_ledger(apps, schema_editor):
    Movimento = apps.get_model("stock", "MovimentoEstoque")
    Estoque = apps.get_model("stock", "Estoque")
    LogAuditoria = apps.get_model("core", "LogAuditoria")

    for estoque in Estoque.objects.all().iterator():
        movimentos = list(
            Movimento.objects.filter(
                produto_id=estoque.produto_id,
                unidade_id=estoque.unidade_id,
            ).order_by("criado_em", "pk")
        )
        total = Decimal("0.00")
        for movimento in movimentos:
            delta = _delta_do_movimento(Movimento, LogAuditoria, movimento)
            if delta == 0:
                delta = Decimal("0.01")
            movimento.delta = delta
            movimento.quantidade = abs(delta)
            movimento.save(update_fields=["delta", "quantidade"])
            total += delta

        residual = Decimal(estoque.quantidade) - total
        if residual != 0:
            Movimento.objects.create(
                produto_id=estoque.produto_id,
                unidade_id=estoque.unidade_id,
                tipo=(
                    "entrada_inicial"
                    if residual > 0
                    else "ajuste_negativo"
                ),
                delta=residual,
                quantidade=abs(residual),
                motivo=MOTIVO_RECONCILIACAO,
            )


def reverter_ledger(apps, schema_editor):
    Movimento = apps.get_model("stock", "MovimentoEstoque")
    Movimento.objects.filter(motivo=MOTIVO_RECONCILIACAO).delete()
    Movimento.objects.update(delta=None)


def criar_trigger_postgres(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            """
            CREATE OR REPLACE FUNCTION stock_movimentoestoque_imutavel()
            RETURNS trigger AS $$
            BEGIN
                IF TG_OP = 'UPDATE' THEN
                    IF NEW.id IS NOT DISTINCT FROM OLD.id
                       AND NEW.produto_id IS NOT DISTINCT FROM OLD.produto_id
                       AND NEW.unidade_id IS NOT DISTINCT FROM OLD.unidade_id
                       AND NEW.tipo IS NOT DISTINCT FROM OLD.tipo
                       AND NEW.delta IS NOT DISTINCT FROM OLD.delta
                       AND NEW.quantidade IS NOT DISTINCT FROM OLD.quantidade
                       AND NEW.motivo IS NOT DISTINCT FROM OLD.motivo
                       AND NEW.criado_em IS NOT DISTINCT FROM OLD.criado_em
                       AND (
                            (
                                OLD.movimento_par_id IS NULL
                                AND NEW.movimento_par_id IS NOT NULL
                            )
                            OR NEW.movimento_par_id IS NOT DISTINCT FROM
                               OLD.movimento_par_id
                       )
                       AND (
                            NEW.usuario_id IS NOT DISTINCT FROM OLD.usuario_id
                            OR (
                                NEW.usuario_id IS NULL
                                AND OLD.usuario_id IS NOT NULL
                            )
                       )
                    THEN
                        RETURN NEW;
                    END IF;
                END IF;
                RAISE EXCEPTION
                    'MovimentoEstoque % é imutável; crie compensação', OLD.id;
            END;
            $$ LANGUAGE plpgsql;
            """
        )
        cursor.execute(
            """
            DROP TRIGGER IF EXISTS stock_movimentoestoque_imutavel
            ON stock_movimentoestoque;
            """
        )
        cursor.execute(
            """
            CREATE TRIGGER stock_movimentoestoque_imutavel
            BEFORE UPDATE OR DELETE ON stock_movimentoestoque
            FOR EACH ROW EXECUTE FUNCTION stock_movimentoestoque_imutavel();
            """
        )


def remover_trigger_postgres(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            "DROP TRIGGER IF EXISTS stock_movimentoestoque_imutavel "
            "ON stock_movimentoestoque;"
        )
        cursor.execute(
            "DROP FUNCTION IF EXISTS stock_movimentoestoque_imutavel();"
        )


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0001_initial"),
        ("stock", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="movimentoestoque",
            name="tipo",
            field=models.CharField(
                choices=[
                    ("entrada", "Entrada"),
                    ("entrada_inicial", "Entrada inicial (migração)"),
                    ("saida", "Saída"),
                    ("ajuste", "Ajuste (legado)"),
                    ("ajuste_positivo", "Ajuste positivo"),
                    ("ajuste_negativo", "Ajuste negativo"),
                    ("transferencia", "Transferência (legado)"),
                    ("transferencia_entrada", "Entrada por transferência"),
                    ("transferencia_saida", "Saída por transferência"),
                    ("baixa_definitiva", "Baixa definitiva"),
                ],
                max_length=30,
                verbose_name="tipo",
            ),
        ),
        migrations.AddField(
            model_name="movimentoestoque",
            name="delta",
            field=models.DecimalField(
                decimal_places=2,
                help_text="Sinal e magnitude: positivo entra, negativo sai.",
                max_digits=12,
                null=True,
                verbose_name="delta",
            ),
        ),
        migrations.AlterField(
            model_name="movimentoestoque",
            name="quantidade",
            field=models.DecimalField(
                decimal_places=2,
                help_text="Derivado de abs(delta); mantido para leitura.",
                max_digits=12,
                verbose_name="quantidade",
            ),
        ),
        migrations.RunPython(preparar_ledger, reverter_ledger),
        migrations.AlterField(
            model_name="movimentoestoque",
            name="delta",
            field=models.DecimalField(
                decimal_places=2,
                help_text="Sinal e magnitude: positivo entra, negativo sai.",
                max_digits=12,
                verbose_name="delta",
            ),
        ),
        migrations.AddConstraint(
            model_name="movimentoestoque",
            constraint=models.CheckConstraint(
                condition=models.Q(("delta", Decimal("0.00")), _negated=True),
                name="movimento_delta_nao_zero",
            ),
        ),
        migrations.AddConstraint(
            model_name="movimentoestoque",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(
                        ("delta__gt", Decimal("0.00")),
                        ("tipo__in", TIPOS_POSITIVOS),
                    )
                    | models.Q(
                        ("delta__lt", Decimal("0.00")),
                        ("tipo__in", TIPOS_NEGATIVOS),
                    )
                    | models.Q(
                        ("tipo__in", ("ajuste", "transferencia")),
                    )
                ),
                name="movimento_delta_coerente_com_tipo",
            ),
        ),
        migrations.RunPython(
            criar_trigger_postgres, remover_trigger_postgres
        ),
    ]
