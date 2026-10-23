"""Regra de ICMS interestadual por UF de origem/destino."""
from decimal import Decimal

ALIQUOTA_INTERESTADUAL_MG = Decimal("0.12")
ALIQUOTA_INTERESTADUAL_PADRAO = Decimal("0.12")


def calcular_interestadual(pedido) -> tuple[bool, Decimal]:
    """Retorna (interestadual, alíquota) para o pedido.

    BA→MG é 12% (Simples Nacional). Demais operações interestaduais usam
    a alíquota padrão desta fase; a tabela por UF será refinada na
    integração fiscal.
    """
    unidade = getattr(pedido, "unidade", None)
    uf_origem = (getattr(unidade, "uf", "") or "").strip().upper()
    uf_destino = (
        getattr(pedido, "uf_entrega", "")
        or getattr(pedido, "uf", "")
        or ""
    ).strip().upper()
    if not uf_origem or not uf_destino or uf_origem == uf_destino:
        return False, Decimal("0.0000")
    if uf_origem == "BA" and uf_destino == "MG":
        return True, ALIQUOTA_INTERESTADUAL_MG
    return True, ALIQUOTA_INTERESTADUAL_PADRAO
