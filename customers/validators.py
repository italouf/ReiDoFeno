"""Validadores brasileiros de CPF e CNPJ.

Aceitam valores formatados ou apenas dígitos; a validação usa os
dígitos verificadores (módulo 11).
"""
import re

from django.core.exceptions import ValidationError

SO_DIGITOS = re.compile(r"\D")


def _apenas_digitos(valor: str) -> str:
    return SO_DIGITOS.sub("", str(valor))


def _calcula_digito(digitos: str, pesos: tuple[int, ...]) -> int:
    total = sum(int(d) * p for d, p in zip(digitos, pesos, strict=False))
    resto = total % 11
    return 0 if resto < 2 else 11 - resto


def validar_cpf(valor: str) -> None:
    cpf = _apenas_digitos(valor)
    if len(cpf) != 11:
        raise ValidationError("CPF deve ter 11 dígitos.")
    if cpf == cpf[0] * 11:
        raise ValidationError("CPF inválido.")

    dv1 = _calcula_digito(cpf[:9], tuple(range(10, 1, -1)))
    dv2 = _calcula_digito(cpf[:10], tuple(range(11, 1, -1)))
    if not cpf.endswith(f"{dv1}{dv2}"):
        raise ValidationError("CPF inválido: dígito verificador não confere.")


def validar_cnpj(valor: str) -> None:
    cnpj = _apenas_digitos(valor)
    if len(cnpj) != 14:
        raise ValidationError("CNPJ deve ter 14 dígitos.")
    if cnpj == cnpj[0] * 14:
        raise ValidationError("CNPJ inválido.")

    pesos1 = (5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)
    pesos2 = (6, *pesos1)
    dv1 = _calcula_digito(cnpj[:12], pesos1)
    dv2 = _calcula_digito(cnpj[:13], pesos2)
    if not cnpj.endswith(f"{dv1}{dv2}"):
        raise ValidationError("CNPJ inválido: dígito verificador não confere.")


class DocumentoValidator:
    """Valida CPF ou CNPJ conforme o tamanho do valor informado."""

    def __call__(self, valor: str) -> None:
        documento = _apenas_digitos(valor)
        if len(documento) == 11:
            validar_cpf(documento)
        elif len(documento) == 14:
            validar_cnpj(documento)
        else:
            raise ValidationError("Informe um CPF (11 dígitos) ou CNPJ (14 dígitos).")

    def __eq__(self, other):
        return isinstance(other, DocumentoValidator)

    def __hash__(self):
        return hash(self.__class__.__name__)

    def deconstruct(self):
        return ("customers.validators.DocumentoValidator", (), {})
