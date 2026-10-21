"""STO-01: constraints e trigger, idempotentes para bancos já migrados."""

from decimal import Decimal

from django.db import migrations, models


def _constraint_delta():
    return models.CheckConstraint(
        condition=~models.Q(delta=Decimal("0.00")),
        name="movimento_delta_nao_zero",
    )


def _constraint_coerencia():
    return models.CheckConstraint(
        condition=(
            models.Q(
                tipo__in=(
                    "entrada",
                    "entrada_inicial",
                    "transferencia_entrada",
                    "ajuste_positivo",
                ),
                delta__gt=Decimal("0.00"),
            )
            | models.Q(
                tipo__in=(
                    "saida",
                    "transferencia_saida",
                    "ajuste_negativo",
                    "baixa_definitiva",
                ),
                delta__lt=Decimal("0.00"),
            )
            | models.Q(tipo__in=("ajuste", "transferencia"))
        ),
        name="movimento_delta_coerente_com_tipo",
    )


def criar_trigger_postgres(schema_editor):
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
                                AND NEW.movimento_par_id <> NEW.id
                                AND NEW.tipo IN (
                                    'transferencia_entrada',
                                    'transferencia_saida'
                                )
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
            "DROP TRIGGER IF EXISTS stock_movimentoestoque_imutavel "
            "ON stock_movimentoestoque;"
        )
        cursor.execute(
            """
            CREATE TRIGGER stock_movimentoestoque_imutavel
            BEFORE UPDATE OR DELETE ON stock_movimentoestoque
            FOR EACH ROW EXECUTE FUNCTION stock_movimentoestoque_imutavel();
            """
        )
        cursor.execute(
            """
            CREATE OR REPLACE FUNCTION stock_movimentoestoque_nao_truncar()
            RETURNS trigger AS $$
            BEGIN
                IF current_setting('stock.permitir_truncate', true) = 'on' THEN
                    RETURN NULL;
                END IF;
                RAISE EXCEPTION
                    'TRUNCATE em MovimentoEstoque é proibido; use compensação';
            END;
            $$ LANGUAGE plpgsql;
            """
        )
        cursor.execute(
            "DROP TRIGGER IF EXISTS stock_movimentoestoque_nao_truncar "
            "ON stock_movimentoestoque;"
        )
        cursor.execute(
            """
            CREATE TRIGGER stock_movimentoestoque_nao_truncar
            BEFORE TRUNCATE ON stock_movimentoestoque
            FOR EACH STATEMENT
            EXECUTE FUNCTION stock_movimentoestoque_nao_truncar();
            """
        )


def criar_constraints_e_trigger(apps, schema_editor):
    from django.apps import apps as global_apps

    Movimento = global_apps.get_model("stock", "MovimentoEstoque")
    with schema_editor.connection.cursor() as cursor:
        existentes = schema_editor.connection.introspection.get_constraints(
            cursor, Movimento._meta.db_table
        )
    faltantes = [
        constraint
        for constraint in (_constraint_delta(), _constraint_coerencia())
        if constraint.name not in existentes
    ]
    if schema_editor.connection.vendor == "sqlite":
        # O rebuild do SQLite usa todas as constraints do modelo atual.
        if faltantes:
            schema_editor.add_constraint(Movimento, faltantes[0])
    else:
        for constraint in faltantes:
            schema_editor.add_constraint(Movimento, constraint)
    criar_trigger_postgres(schema_editor)


def remover_constraints_e_trigger(apps, schema_editor):
    from django.apps import apps as global_apps

    Movimento = global_apps.get_model("stock", "MovimentoEstoque")
    with schema_editor.connection.cursor() as cursor:
        existentes = schema_editor.connection.introspection.get_constraints(
            cursor, Movimento._meta.db_table
        )
    for constraint in (_constraint_delta(), _constraint_coerencia()):
        if constraint.name in existentes:
            schema_editor.remove_constraint(Movimento, constraint)
    if schema_editor.connection.vendor == "postgresql":
        with schema_editor.connection.cursor() as cursor:
            cursor.execute(
                "DROP TRIGGER IF EXISTS stock_movimentoestoque_imutavel "
                "ON stock_movimentoestoque;"
            )
            cursor.execute(
                "DROP TRIGGER IF EXISTS stock_movimentoestoque_nao_truncar "
                "ON stock_movimentoestoque;"
            )
            cursor.execute(
                "DROP FUNCTION IF EXISTS "
                "stock_movimentoestoque_imutavel();"
            )
            cursor.execute(
                "DROP FUNCTION IF EXISTS "
                "stock_movimentoestoque_nao_truncar();"
            )


class Migration(migrations.Migration):

    dependencies = [
        ("stock", "0005_sto01_dados_legado"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddConstraint(
                    model_name="movimentoestoque",
                    constraint=_constraint_delta(),
                ),
                migrations.AddConstraint(
                    model_name="movimentoestoque",
                    constraint=_constraint_coerencia(),
                ),
            ],
            database_operations=[
                migrations.RunPython(
                    criar_constraints_e_trigger,
                    remover_constraints_e_trigger,
                ),
            ],
        ),
    ]
