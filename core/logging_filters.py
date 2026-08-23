"""Filtro de logging que mascara possíveis CPFs/CNPJs em mensagens."""
import re

_PADRAO_DOCUMENTOS = re.compile(r"(?<!\d)\d{11}(?!\d)|(?<!\d)\d{14}(?!\d)")


def _mascarar(texto: str) -> str:
    return _PADRAO_DOCUMENTOS.sub("[DOC-REMOVIDO]", texto)


class SanitizePIIFilter:
    """Máscara sequências com 11 ou 14 dígitos (CPF/CNPJ) em log records."""

    def filter(self, record) -> bool:
        if isinstance(record.msg, str):
            record.msg = _mascarar(record.msg)

        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    chave: _mascarar(valor) if isinstance(valor, str) else valor
                    for chave, valor in record.args.items()
                }
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    _mascarar(valor) if isinstance(valor, str) else valor
                    for valor in record.args
                )
            else:
                record.args = [
                    _mascarar(valor) if isinstance(valor, str) else valor
                    for valor in record.args
                ]
        return True
