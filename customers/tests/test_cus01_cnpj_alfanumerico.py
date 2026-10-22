"""CUS-01: CNPJ alfanumérico da Receita Federal (2026)."""

from django.test import SimpleTestCase, TestCase

from customers.factories import ClienteFactory
from customers.models import Cliente, normalizar_documento
from customers.validators import (
    DocumentoValidator,
    validar_cnpj,
    validar_documento,
)
from sales.factories import PedidoFactory
from sales.models import Pedido

CNPJ_ALFA = "00.000.000/E08G-12"
CNPJ_ALFA_NORMALIZADO = "00000000E08G12"


class CNPJAlfanumericoTests(SimpleTestCase):
    def test_cnpj_alfanumerico_primeiro_emitido(self):
        assert normalizar_documento(CNPJ_ALFA) == CNPJ_ALFA_NORMALIZADO
        assert validar_documento(CNPJ_ALFA) is True
        validar_cnpj(CNPJ_ALFA)  # não levanta

    def test_cnpj_alfanumerico_sem_formatacao(self):
        assert validar_documento(CNPJ_ALFA_NORMALIZADO) is True

    def test_cnpj_alfanumerico_dv_invalido(self):
        assert validar_documento("00.000.000/E08G-99") is False

    def test_cnpj_alfanumerico_dv_nao_numerico_rejeitado(self):
        assert validar_documento("00000000E08G1A") is False

    def test_cnpj_legado_continua_valido(self):
        assert validar_documento("11.222.333/0001-81") is True
        assert validar_documento("11222333000181") is True

    def test_cpf_nao_afetado(self):
        assert validar_documento("123.456.789-09") is True
        assert validar_documento("111.444.777-35") is True

    def test_cnpj_minusculas_normalizadas_para_maiusculas(self):
        assert normalizar_documento("00.000.000/e08g-12") == CNPJ_ALFA_NORMALIZADO
        assert validar_documento("00.000.000/e08g-12") is True

    def test_documento_validator_aceita_alfanumerico(self):
        DocumentoValidator()(CNPJ_ALFA)

    def test_cpf_com_letra_e_rejeitado(self):
        assert validar_documento("1234567890A") is False

    def test_cnpj_com_caractere_fora_do_alfabeto_e_rejeitado(self):
        assert validar_documento("00000000E08G-1$") is False


class ClienteCNPJAlfanumericoTests(TestCase):
    def test_cliente_persiste_cnpj_alfanumerico_normalizado(self):
        cliente = ClienteFactory(documento="00.000.000/e08g-12")
        cliente.refresh_from_db()
        assert cliente.documento == CNPJ_ALFA_NORMALIZADO
        assert Cliente.objects.filter(documento=CNPJ_ALFA_NORMALIZADO).exists()

    def test_pedido_de_cliente_alfanumerico_e_elegivel_para_fiscal(self):
        from fiscal.services import pedido_elegivel

        cliente = ClienteFactory(documento=CNPJ_ALFA)
        pedido = PedidoFactory(
            cliente=cliente,
            status_financeiro=Pedido.StatusFinanceiro.PAGO,
            financeiro_conciliado=True,
        )
        assert pedido_elegivel(pedido) is True

    def test_log_mascara_cnpj_alfanumerico(self):
        from core.logging_filters import _mascarar

        texto = f"documento={CNPJ_ALFA_NORMALIZADO} fim"
        assert CNPJ_ALFA_NORMALIZADO not in _mascarar(texto)
        assert "[DOC-REMOVIDO]" in _mascarar(texto)
