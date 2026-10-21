"""STO-01: schema do delta assinado.

A carga de dados, as evidências e a reconciliação ficam em 0005; constraints e
trigger em 0006. Essa separação evita `ALTER TABLE` após DML na mesma transação
no PostgreSQL (pending trigger events).
"""

from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0002_logauditoria"),
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
                default=Decimal("0.00"),
                help_text="Sinal e magnitude: positivo entra, negativo sai.",
                max_digits=12,
                verbose_name="delta",
            ),
            preserve_default=False,
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
    ]
