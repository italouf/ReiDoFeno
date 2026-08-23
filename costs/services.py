"""Cálculo de despesas por período (base do lucro estimado do painel)."""
from calendar import monthrange
from datetime import date
from decimal import Decimal

from .models import Despesa


def _primeiro_dia(ano: int, mes: int) -> date:
    return date(ano, mes, 1)


def _meses_entre(inicio: date, fim: date) -> list[date]:
    """Primeiro dia de cada mês no intervalo [inicio, fim]."""
    meses = []
    ano, mes = inicio.year, inicio.month
    while _primeiro_dia(ano, mes) <= fim:
        meses.append(_primeiro_dia(ano, mes))
        mes += 1
        if mes > 12:
            ano, mes = ano + 1, 1
    return meses


def despesas_no_periodo(inicio: date, fim: date) -> Decimal:
    """Soma as despesas apropriadas ao período [inicio, fim].

    - Única: conta se a data cai no período.
    - Mensal: conta em cada mês iniciado a partir do mês da despesa.
    - Anual: conta em cada ano iniciado a partir do ano da despesa.
    """
    if inicio > fim:
        return Decimal("0.00")

    total = Decimal("0.00")
    meses = _meses_entre(inicio, fim)
    anos = sorted({mes.year for mes in meses})

    for despesa in Despesa.objects.all():
        if despesa.recorrencia == Despesa.Recorrencia.UNICA:
            if inicio <= despesa.data <= fim:
                total += despesa.valor
        elif despesa.recorrencia == Despesa.Recorrencia.MENSAL:
            primeiro_mes = _primeiro_dia(despesa.data.year, despesa.data.month)
            ocorrencias = sum(
                1 for mes in meses if mes >= primeiro_mes and mes <= fim
            )
            total += despesa.valor * ocorrencias
        else:  # ANUAL
            primeiro_ano = date(despesa.data.year, 1, 1)
            ocorrencias = sum(
                1 for ano in anos if _primeiro_dia(ano, 1) >= primeiro_ano
            )
            total += despesa.valor * ocorrencias

    return total


def dias_no_mes(ref: date) -> int:
    return monthrange(ref.year, ref.month)[1]
