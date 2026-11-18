"""Filtros de logging e eventos Sentry para mascaramento de PII (LGPD)."""
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
_PADRAO_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")


def _mascarar(texto: str) -> str:
    return _PADRAO_DOCUMENTOS.sub("[DOC-REMOVIDO]", texto)


def sanitizar_texto_pii(texto: str) -> str:
    """Mascara CPF, CNPJ (numérico/alfanumérico) e e-mail em texto livre."""
    mascarado = _mascarar(texto)
    return _PADRAO_EMAIL.sub("[EMAIL-REMOVIDO]", mascarado)


def _sanitizar_estrutura(valor, *, profundidade: int = 0):
    if profundidade >= 10:
        return valor
    if isinstance(valor, str):
        return sanitizar_texto_pii(valor)
    if isinstance(valor, dict):
        return {
            chave: _sanitizar_estrutura(item, profundidade=profundidade + 1)
            for chave, item in valor.items()
        }
    if isinstance(valor, list):
        return [
            _sanitizar_estrutura(item, profundidade=profundidade + 1)
            for item in valor
        ]
    if isinstance(valor, tuple):
        return tuple(
            _sanitizar_estrutura(item, profundidade=profundidade + 1)
            for item in valor
        )
    return valor


def filter_pii_event(event, hint):
    """Hook ``before_send`` do Sentry que remove PII antes do envio."""
    del hint
    if not isinstance(event, dict):
        return event

    for campo in (
        "message",
        "logentry",
        "exception",
        "breadcrumbs",
        "request",
        "extra",
        "contexts",
        "tags",
    ):
        if campo in event:
            event[campo] = _sanitizar_estrutura(event[campo])
    return event


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
