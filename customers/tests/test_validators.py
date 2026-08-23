from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from customers.validators import (
    DocumentoValidator,
    validar_cnpj,
    validar_cpf,
)


class CpfValidatorTests(SimpleTestCase):
    def test_aceita_cpfs_validos(self):
        for cpf in ("529.982.247-25", "111.444.777-35", "52998224725"):
            with self.subTest(cpf=cpf):
                validar_cpf(cpf)

    def test_rejeita_digito_verificador_incorreto(self):
        with self.assertRaises(ValidationError):
            validar_cpf("111.444.777-34")

    def test_rejeita_digitos_repetidos(self):
        with self.assertRaises(ValidationError):
            validar_cpf("111.111.111-11")

    def test_rejeita_tamanho_incorreto(self):
        with self.assertRaises(ValidationError):
            validar_cpf("5299822472")

    def test_rejeita_nao_numericos(self):
        with self.assertRaises(ValidationError):
            validar_cpf("abcdefghijk")


class CnpjValidatorTests(SimpleTestCase):
    def test_aceita_cnpjs_validos(self):
        for cnpj in (
            "11.222.333/0001-81",
            "04.252.011/0001-10",
            "11222333000181",
        ):
            with self.subTest(cnpj=cnpj):
                validar_cnpj(cnpj)

    def test_rejeita_digito_verificador_incorreto(self):
        with self.assertRaises(ValidationError):
            validar_cnpj("11.222.333/0001-82")

    def test_rejeita_digitos_repetidos(self):
        with self.assertRaises(ValidationError):
            validar_cnpj("11.111.111/1111-11")

    def test_rejeita_tamanho_incorreto(self):
        with self.assertRaises(ValidationError):
            validar_cnpj("1122233300018")


class DocumentoValidatorTests(SimpleTestCase):
    def setUp(self):
        self.validador = DocumentoValidator()

    def test_despacha_para_cpf(self):
        self.validador("529.982.247-25")  # não levanta

    def test_despacha_para_cnpj(self):
        self.validador("04.252.011/0001-10")  # não levanta

    def test_rejeita_tamanhos_diversos(self):
        for documento in ("123", "12345678901234567890"):
            with self.subTest(documento=documento):
                with self.assertRaises(ValidationError):
                    self.validador(documento)
