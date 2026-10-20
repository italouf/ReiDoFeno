"""Validadores brasileiros de CPF e CNPJ (numérico e alfanumérico).

Aceitam valores formatados ou normalizados. O CNPJ alfanumérico segue a Nota
Técnica COCAD/SUARA/RFB nº 49/2024: cada caractere vale ``ord(c) - 48`` e o
módulo 11 usa os mesmos pesos do CNPJ numérico.
"""
import re

from django.core.exceptions import ValidationError

SO_DIGITOS = re.compile(r"\D")
NAO_ALFANUMERICO = re.compile(r"[^0-9A-Za-z]")
CNPJ_ALFANUMERICO = re.compile(r"^[A-Z0-9]{14}$")

PESOS_CNPJ_1 = (5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)
PESOS_CNPJ_2 = (6, *PESOS_CNPJ_1)


def normalizar_documento(valor: str) -> str:
    """Remove pontuação e preserva letras maiúsculas de CNPJ alfanumérico."""
    if not valor:
        return ""
    return NAO_ALFANUMERICO.sub("", str(valor)).upper()


def _apenas_digitos(valor: str) -> str:
    return SO_DIGITOS.sub("", str(valor))


def _calcula_digito(digitos: str, pesos: tuple[int, ...]) -> int:
    total = sum(int(d) * p for d, p in zip(digitos, pesos, strict=False))
    resto = total % 11
    return 0 if resto < 2 else 11 - resto


def _valor_caractere(caractere: str) -> int:
    """Valor oficial do CNPJ alfanumérico: código ASCII menos 48."""
    return ord(caractere) - 48


def _calcula_digito_cnpj(base: str, pesos: tuple[int, ...]) -> int:
    total = sum(
        _valor_caractere(caractere) * peso
        for caractere, peso in zip(base, pesos, strict=False)
    )
    resto = total % 11
    return 0 if resto < 2 else 11 - resto


def validar_cpf(valor: str) -> None:
    cpf = normalizar_documento(valor)
    if len(cpf) != 11 or not cpf.isdigit():
        raise ValidationError("CPF deve ter 11 dígitos.")
    if cpf == cpf[0] * 11:
        raise ValidationError("CPF inválido.")

    dv1 = _calcula_digito(cpf[:9], tuple(range(10, 1, -1)))
    dv2 = _calcula_digito(cpf[:10], tuple(range(11, 1, -1)))
    if not cpf.endswith(f"{dv1}{dv2}"):
        raise ValidationError("CPF inválido: dígito verificador não confere.")


def validar_cnpj(valor: str) -> None:
    cnpj = normalizar_documento(valor)
    if len(cnpj) != 14 or not CNPJ_ALFANUMERICO.match(cnpj):
        raise ValidationError(
            "CNPJ deve ter 14 caracteres alfanuméricos (A-Z, 0-9)."
        )
    if cnpj == cnpj[0] * 14:
        raise ValidationError("CNPJ inválido.")
    if not cnpj[-2:].isdigit():
        raise ValidationError("CNPJ inválido: dígito verificador deve ser numérico.")

    dv1 = _calcula_digito_cnpj(cnpj[:12], PESOS_CNPJ_1)
    dv2 = _calcula_digito_cnpj(cnpj[:13], PESOS_CNPJ_2)
    if not cnpj.endswith(f"{dv1}{dv2}"):
        raise ValidationError("CNPJ inválido: dígito verificador não confere.")


def validar_documento(valor: str) -> bool:
    """Retorna True/False para CPF, CNPJ numérico ou CNPJ alfanumérico."""
    try:
        DocumentoValidator()(valor)
    except ValidationError:
        return False
    return True


class DocumentoValidator:
    """Valida CPF ou CNPJ (numérico/alfanumérico) pelo tamanho normalizado."""

    def __call__(self, valor: str) -> None:
        documento = normalizar_documento(valor)
        if len(documento) == 11:
            validar_cpf(documento)
        elif len(documento) == 14:
            validar_cnpj(documento)
        else:
            raise ValidationError(
                "Informe um CPF (11 dígitos) ou CNPJ (14 caracteres)."
            )

    def __eq__(self, other):
        return isinstance(other, DocumentoValidator)

    def __hash__(self):
        return hash(self.__class__.__name__)

    def deconstruct(self):
        return ("customers.validators.DocumentoValidator", (), {})
