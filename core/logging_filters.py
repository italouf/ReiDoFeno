"""Filtro de logging que mascara possíveis CPFs/CNPJs em mensagens."""
import re

_PADRAO_DOCUMENTOS = re.compile(
    r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b"
    r"|\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b"
    r"|\b[A-Za-z0-9]{2}\.[A-Za-z0-9]{3}\."
    r"[A-Za-z0-9]{3}/[A-Za-z0-9]{4}-\d{2}\b"
    r"|(?<!\d)\d{11}(?!\d)"
    r"|(?<!\d)\d{14}(?!\d)"
    r"|(?<![A-Za-z0-9])"
    r"(?=[A-Za-z0-9]{0,13}[A-Za-z])(?=[A-Za-z0-9]{0,13}\d)"
    r"[A-Za-z0-9]{14}(?![A-Za-z0-9])"
)


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
